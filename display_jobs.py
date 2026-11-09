"""
Coordination between the parent application, the loaded SVG, the plotter, and
the Plot Runner panel.

There are two ways a plot starts:

  Armed (operator presses Start)
    1. The parent uploads an SVG tagged with a job_id (POST /api/svg).
    2. The parent arms one layer (POST /arm). We check the job_id (and optional
       sha256) against the loaded SVG, the layer, and that the plotter is idle,
       then send ARMED to the panel.
    3. The operator presses Start; the panel sends START_PLOT. We check again
       and start the plot here on the Pi.

  Remote (POST /plot/<layer>)
    The plot starts at once, and we send PLOTTING so the panel shows the
    countdown without anyone pressing Start.

Either way, while a plot is running we keep the panel's Progress screen in step
with the plotter: IDLE when it ends or pauses, PLOTTING (with elapsed_time)
when it resumes, and PLOTTING again if the panel resets mid-plot.

The panel's timers are local: it disarms after 10 minutes (DISARMED event) and
its countdown knows nothing about the plotter. A periodic STATUS check
reconciles the panel with what it should be showing.
"""

import logging
import math
import re
import threading
import time
from datetime import datetime
from typing import Any, Callable, Dict, Optional, Tuple

from serial_communication import (
    EVENT_CONNECTED,
    EVENT_DISCONNECTED,
    MAX_LINE_BYTES,
    DisplayError,
    DisplayRejected,
    DisplayTimeout,
    DisplayUnavailable,
    PlotRunnerDisplay,
    build_panel_message,
    encode_message,
)

logger = logging.getLogger(__name__)

INK_COLOR_RE = re.compile(r"^#?([0-9A-Fa-f]{6})$")
DEFAULT_INK_COLOR = "#FFFFFF"

# Don't re-show a countdown that has (almost) run out.
RESYNC_MIN_REMAINING = 2.0

# start_plot(...) -> (started, error). on_finished(outcome) is called once the
# plot thread ends, with outcome "completed", "paused" or "failed".
StartPlotFn = Callable[..., Tuple[bool, Optional[str]]]


class JobRequestError(Exception):
    """A request was refused. status_code is the HTTP status to return."""

    def __init__(self, message: str, status_code: int = 400, **details):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.details = details

    def to_dict(self) -> Dict[str, Any]:
        return {"error": self.message, **self.details}


def _now() -> str:
    return datetime.now().isoformat()


def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _lenient_number(value) -> Optional[float]:
    """Best-effort number from legacy fields (time_data), or None."""
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number >= 0 else None


def _normalise_color(value) -> Optional[str]:
    match = INK_COLOR_RE.match(value) if isinstance(value, str) else None
    return "#" + match.group(1).upper() if match else None


def _validate_homing(p: Dict[str, Any]) -> Optional[bool]:
    """Optional homing flag: True/False overrides config_content's homing; absent/null leaves it."""
    homing = p.get("homing")
    if homing is not None and not isinstance(homing, bool):
        raise JobRequestError("homing must be true or false")
    return homing


def _valid_job_id(job_id) -> bool:
    if isinstance(job_id, bool):
        return False
    return (isinstance(job_id, str) and bool(job_id.strip())) or isinstance(job_id, int)


class DisplayJobController:
    STATUS_SYNC_INTERVAL = 15.0

    def __init__(
        self,
        display: PlotRunnerDisplay,
        svg_manager,
        start_plot: StartPlotFn,
        is_plotter_idle: Callable[[], bool],
        start_bullseye: Optional[Callable[[], Tuple[bool, Optional[str]]]] = None,
    ):
        self.display = display
        self.svg_manager = svg_manager
        self._start_plot = start_plot
        self._is_plotter_idle = is_plotter_idle
        self._start_bullseye = start_bullseye

        # Held across serial requests so that arming, plot starts, events and
        # STATUS reconciliation never interleave. Lock order: this lock, then the
        # app's status_lock (start_plot / is_plotter_idle take it).
        self._lock = threading.RLock()
        self.armed: Optional[Dict[str, Any]] = None        # Waiting for Start.
        self.active_plot: Optional[Dict[str, Any]] = None  # Running or paused plot.
        self.device_state: Optional[str] = None
        self.device_status_at: Optional[str] = None
        self.idle_gif: Optional[bool] = None
        self.last_event: Optional[Dict[str, Any]] = None
        self.last_disarm: Optional[Dict[str, Any]] = None
        self.last_error: Optional[Dict[str, Any]] = None
        self._plot_seq = 0

        self._sync_thread: Optional[threading.Thread] = None
        self._stop = threading.Event()

    # ------------------------------------------------------------------ lifecycle

    def start(self):
        self.display.set_event_handler(self.handle_event)
        self.display.start()
        if not self._sync_thread or not self._sync_thread.is_alive():
            self._sync_thread = threading.Thread(target=self._sync_loop, name="display-sync", daemon=True)
            self._sync_thread.start()

    def stop(self):
        self._stop.set()
        self.display.stop()

    # ------------------------------------------------------------------ parent API: arm

    def arm(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Validate an arm request and show it on the panel. Raises JobRequestError."""
        if not isinstance(payload, dict):
            raise JobRequestError("Request body must be a JSON object")

        job = self._validate_arm_payload(payload)

        with self._lock:
            identity = self.svg_manager.get_svg_identity()
            self._check_svg_for_arm(job, identity)

            if not self.svg_manager.is_valid_layer(job["layer_name"]):
                raise JobRequestError(
                    f"Layer '{job['layer_name']}' not found in the loaded SVG",
                    404,
                    available_layers=self.svg_manager.get_available_layers(),
                )

            if not self._is_plotter_idle():
                raise JobRequestError("Plotter is busy", 409)

            if not self.display.connected:
                raise JobRequestError("Plot Runner display is not connected", 503)

            message = build_panel_message("ARMED", job)
            if len(encode_message(message)) > MAX_LINE_BYTES:
                raise JobRequestError(
                    f"ARMED message would exceed {MAX_LINE_BYTES} bytes; shorten job_id, layer_name or ink_name"
                )

            try:
                self.display.request(message)
            except DisplayRejected as e:
                raise JobRequestError(f"Display rejected ARMED: {e.reason}", 502)
            except DisplayTimeout:
                raise JobRequestError("Display did not reply to ARMED", 504)
            except DisplayUnavailable as e:
                raise JobRequestError(str(e), 503)

            job["svg"] = identity
            job["armed_at"] = _now()
            previous = self.armed
            self.armed = job
            # The plotter is idle, so any active_plot is stale; ARMED has replaced
            # its screen anyway.
            self.active_plot = None
            self.device_state = "ARMED"
            if previous:
                logger.info(f"Re-armed: replaced job {previous['job_id']!r} layer {previous['layer_name']!r}")
            logger.info(
                f"Armed job {job['job_id']!r} layer {job['layer_name']!r} "
                f"({job['estimated_time']}s, ink {job['ink_color']})"
            )
            return self._public_job(job)

    def disarm(self, reason: str = "host") -> bool:
        """Clear the armed job and return the panel to IDLE. Returns True if something was armed."""
        with self._lock:
            had_job = self.armed is not None
            if had_job:
                self._record_disarm(self.armed, reason)
                self.armed = None
            if had_job or self.device_state == "ARMED":
                self._send_idle()
            return had_job

    def on_svg_changed(self):
        """The loaded SVG is being replaced or cleared: an armed job no longer applies."""
        with self._lock:
            if self.armed:
                logger.info("SVG changed; disarming")
                self.disarm("svg_changed")

    # ------------------------------------------------------------------ parent API: remote plot

    def start_remote_plot(self, layer_name: str, body: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """
        Start a plot requested through POST /plot/<layer> and show it on the panel.

        Raises JobRequestError for a bad request; returns (started, error) otherwise.
        """
        if not isinstance(body, dict):
            body = {}
        identity = self.svg_manager.get_svg_identity()
        screen = self._remote_plot_screen(layer_name, body, identity)
        homing = _validate_homing(body)

        with self._lock:
            token = self._next_token()
            started, error = self._start_plot(
                layer_name=layer_name,
                config_overrides=body.get("config_content") or {},
                time_data=body.get("time_data"),
                progress_in_mm=body.get("progress_in_mm"),
                homing=homing,
                job_id=body.get("job_id") if body.get("job_id") is not None else (identity or {}).get("job_id"),
                source="api",
                on_finished=lambda outcome, t=token: self.plot_finished(t, outcome),
            )
            if not started:
                return False, error

            if self.armed:
                # PLOTTING replaces the Armed screen; the armed job is void.
                self._record_disarm(self.armed, "remote_plot")
                self.armed = None

            self.active_plot = self._new_active_plot(screen, token, "api", identity)
            if self.active_plot["show_on_panel"]:
                self._send_plotting()
            else:
                logger.info("Remote plot has no estimated_time; panel stays idle")
                if self.device_state in ("ARMED", "PLOTTING"):
                    self._send_idle()
            return True, None

    # ------------------------------------------------------------------ plot lifecycle

    def plot_finished(self, token: int, outcome: str):
        """Called by the plot thread when a plot's run ends."""
        with self._lock:
            plot = self.active_plot
            if not plot or plot["token"] != token:
                return  # The screen has moved on since this plot started.
            if outcome == "paused":
                self._pause_active_plot()
                return
            logger.info(f"Plot for job {plot['job_id']!r} ended: {outcome}")
            self._end_active_plot()

    def plot_paused(self):
        """POST /plot/pause succeeded."""
        with self._lock:
            if self.active_plot:
                self._pause_active_plot()

    def plot_resumed(self):
        """POST /plot/resume succeeded: show the countdown again from where it paused."""
        with self._lock:
            plot = self.active_plot
            if not plot or not plot["paused"]:
                return
            plot["paused"] = False
            plot["resumed"] = True
            plot["run_started"] = time.monotonic()
            if plot["show_on_panel"] and self.armed is None:
                self._send_plotting()

    def plot_stopped(self):
        """POST /plot/stop succeeded."""
        with self._lock:
            if self.active_plot:
                logger.info(f"Plot for job {self.active_plot['job_id']!r} stopped")
                self._end_active_plot()

    def controller_finished(self):
        """
        The plot controller went idle or errored. A resumed plot runs on the
        controller's own thread with no completion callback, so this is how
        its end is noticed.
        """
        with self._lock:
            plot = self.active_plot
            if plot and plot.get("resumed") and not plot["paused"]:
                logger.info(f"Resumed plot for job {plot['job_id']!r} ended")
                self._end_active_plot()

    def _pause_active_plot(self):
        plot = self.active_plot
        if plot["paused"]:
            return
        plot["elapsed_before"] = self._elapsed(plot)
        plot["run_started"] = None
        plot["paused"] = True
        logger.info(f"Plot for job {plot['job_id']!r} paused at {plot['elapsed_before']:.0f}s")
        if self.armed is None:
            self._send_idle()

    def _end_active_plot(self):
        self.active_plot = None
        if self.armed is None:
            self._send_idle()

    # ------------------------------------------------------------------ device events

    def handle_event(self, event: Dict[str, Any]):
        command = event.get("command")
        if command not in (EVENT_CONNECTED, EVENT_DISCONNECTED):
            self.last_event = {**event, "received_at": _now()}

        if command == "START_PLOT":
            self._on_start_plot(event)
        elif command == "DISARMED":
            self._on_disarmed(event)
        elif command == "DRAW_BULLSEYE":
            self._on_draw_bullseye()
        elif command == "DOUBLE_BUTTON_PRESS":
            logger.info("Display button pressed (no action)")
        elif command == EVENT_CONNECTED:
            self.sync_status()
        elif command == EVENT_DISCONNECTED:
            with self._lock:
                self.device_state = None
        else:
            logger.info(f"Ignoring unknown display event: {event}")

    def _on_start_plot(self, event: Dict[str, Any]):
        job_id = event.get("job_id")
        layer_name = event.get("layer_name")
        with self._lock:
            self.device_state = "PLOTTING"
            armed = self.armed
            identity = self.svg_manager.get_svg_identity()

            refusal = None
            if armed is None:
                refusal = "No job is armed"
            elif armed["job_id"] != job_id or armed["layer_name"] != layer_name:
                refusal = (
                    f"START_PLOT for job {job_id!r} layer {layer_name!r} does not match "
                    f"armed job {armed['job_id']!r} layer {armed['layer_name']!r}"
                )
            elif not identity or identity.get("id") != armed["svg"]["id"] \
                    or identity.get("sha256") != armed["svg"]["sha256"]:
                refusal = "Loaded SVG changed since the job was armed"
            elif not self.svg_manager.is_valid_layer(layer_name):
                refusal = f"Layer {layer_name!r} no longer exists in the loaded SVG"
            elif not self._is_plotter_idle():
                refusal = "Plotter is busy"

            if refusal:
                self._refuse_start(job_id, layer_name, refusal)
                return

            token = self._next_token()
            started, error = self._start_plot(
                layer_name=armed["layer_name"],
                config_overrides=armed["config_content"],
                time_data=armed["time_data"],
                progress_in_mm=armed["progress_in_mm"],
                homing=armed["homing"],
                job_id=armed["job_id"],
                source="display",
                on_finished=lambda outcome, t=token: self.plot_finished(t, outcome),
            )
            if not started:
                self._refuse_start(job_id, layer_name, error or "Plot failed to start")
                return

            self.armed = None
            # The panel started its own countdown when Start was pressed.
            self.active_plot = self._new_active_plot(armed, token, "display", identity)
            logger.info(f"Started plot from panel: job {job_id!r} layer {layer_name!r}")

    def _refuse_start(self, job_id, layer_name, reason: str):
        logger.warning(f"Refusing START_PLOT: {reason}")
        self.last_error = {
            "error": reason,
            "event": "START_PLOT",
            "job_id": job_id,
            "layer_name": layer_name,
            "at": _now(),
        }
        if self.armed:
            self._record_disarm(self.armed, "start_refused")
            self.armed = None
        # The panel is counting down for a plot that isn't happening. If a
        # different plot is running, show that instead.
        self._show_desired_screen()

    def _on_disarmed(self, event: Dict[str, Any]):
        with self._lock:
            self.device_state = "IDLE"
            if self.armed and self.armed["job_id"] == event.get("job_id"):
                logger.info(f"Panel disarmed job {event.get('job_id')!r} ({event.get('reason')})")
                self._record_disarm(self.armed, event.get("reason") or "timeout")
                self.armed = None

    def _on_draw_bullseye(self):
        with self._lock:
            self.device_state = "IDLE"
            if self.armed or self.active_plot:
                logger.warning("Ignoring DRAW_BULLSEYE: a job is armed or plotting")
                return
            if self._start_bullseye is None:
                return
            started, error = self._start_bullseye()
            if not started:
                logger.warning(f"Could not draw bullseye: {error}")
                self.last_error = {"error": error, "event": "DRAW_BULLSEYE", "at": _now()}

    # ------------------------------------------------------------------ STATUS sync

    def _sync_loop(self):
        while not self._stop.wait(self.STATUS_SYNC_INTERVAL):
            if self.display.connected:
                self.sync_status()

    def sync_status(self):
        """Ask the panel for its state and reconcile it with what it should show."""
        with self._lock:
            try:
                status = self.display.status()
            except DisplayError as e:
                logger.debug(f"STATUS failed: {e}")
                return
            self._reconcile(status)

    def _reconcile(self, status: Dict[str, Any]):
        state = status.get("state")
        job_id = status.get("job_id")
        layer_name = status.get("layer_name")
        self.device_state = state
        self.device_status_at = _now()
        if "idle_gif" in status:
            self.idle_gif = bool(status.get("idle_gif"))

        def shows(job):
            return job is not None and job["job_id"] == job_id and job["layer_name"] == layer_name

        if self.armed:
            if state == "IDLE":
                # Most likely the panel reset (it keeps no state) or a DISARMED was missed.
                logger.warning(f"Panel is IDLE but job {self.armed['job_id']!r} was armed; clearing")
                self._record_disarm(self.armed, "device_idle")
                self.armed = None
                self._show_desired_screen()
            elif not shows(self.armed):
                logger.warning(f"Panel shows {state} {job_id!r}/{layer_name!r}, expected armed job; re-sending")
                self._show_desired_screen()
            elif state == "PLOTTING":
                # Start was pressed; START_PLOT is either queued or was lost.
                logger.warning(f"Panel is PLOTTING armed job {job_id!r} but no START_PLOT handled yet")
            return

        if self._countdown_wanted():
            if state == "PLOTTING" and shows(self.active_plot):
                return
            # Panel reset mid-plot, or shows something else: resume the countdown.
            logger.info(f"Panel shows {state}; restoring countdown for job {self.active_plot['job_id']!r}")
            self._send_plotting()
            return

        if state == "IDLE":
            return
        if state == "PLOTTING" and shows(self.active_plot) and not self.active_plot["paused"]:
            return  # Countdown nearly done; the panel will go idle by itself.
        logger.warning(f"Panel shows {state} {job_id!r}/{layer_name!r} with nothing to show; sending IDLE")
        self._send_idle()

    # ------------------------------------------------------------------ screen helpers

    def _countdown_wanted(self) -> bool:
        plot = self.active_plot
        if not plot or plot["paused"] or not plot["show_on_panel"]:
            return False
        return plot["estimated_time"] - self._elapsed(plot) > RESYNC_MIN_REMAINING

    def _show_desired_screen(self):
        """Put the panel on whatever it should be showing right now."""
        if self.armed:
            try:
                self.display.request(build_panel_message("ARMED", self.armed))
                self.device_state = "ARMED"
            except DisplayError as e:
                logger.warning(f"Could not re-send ARMED: {e}")
        elif self._countdown_wanted():
            self._send_plotting()
        else:
            self._send_idle()

    def _send_plotting(self):
        plot = self.active_plot
        elapsed = round(self._elapsed(plot), 1)
        message = build_panel_message("PLOTTING", plot, elapsed_time=elapsed)
        try:
            self.display.request(message)
            self.device_state = "PLOTTING"
        except DisplayError as e:
            logger.warning(f"Could not send PLOTTING to display: {e}")
            self.last_error = {"error": f"PLOTTING not shown: {e}", "event": "PLOTTING",
                               "job_id": plot["job_id"], "layer_name": plot["layer_name"], "at": _now()}

    def _send_idle(self):
        try:
            self.display.idle()
            self.device_state = "IDLE"
        except DisplayError as e:
            logger.warning(f"Could not send IDLE to display: {e}")

    # ------------------------------------------------------------------ state helpers

    def _next_token(self) -> int:
        self._plot_seq += 1
        return self._plot_seq

    @staticmethod
    def _new_active_plot(job: Dict[str, Any], token: int, source: str,
                         identity: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        estimated = job.get("estimated_time")
        return {
            "job_id": job["job_id"],
            "layer_name": job["layer_name"],
            "ink_color": job.get("ink_color") or DEFAULT_INK_COLOR,
            "ink_name": job.get("ink_name"),
            "estimated_time": estimated,
            "progress_in_mm": job.get("progress_in_mm"),
            "homing": job.get("homing"),
            "armed_at": job.get("armed_at"),
            "started_at": _now(),
            "svg": identity,
            "source": source,
            "token": token,
            "show_on_panel": estimated is not None,
            "elapsed_before": float(job.get("elapsed_time") or 0),
            "run_started": time.monotonic(),
            "paused": False,
            "resumed": False,
        }

    @staticmethod
    def _elapsed(plot: Dict[str, Any]) -> float:
        elapsed = plot["elapsed_before"]
        if plot.get("run_started") is not None:
            elapsed += time.monotonic() - plot["run_started"]
        return elapsed

    def _record_disarm(self, job: Dict[str, Any], reason: str):
        self.last_disarm = {
            "job_id": job["job_id"],
            "layer_name": job["layer_name"],
            "reason": reason,
            "at": _now(),
        }

    def get_state(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "connected": self.display.connected,
                "port": self.display.device_path if self.display.connected else None,
                "device_state": self.device_state,
                "device_status_at": self.device_status_at,
                "idle_gif": self.idle_gif,
                "armed_job": self._public_job(self.armed) if self.armed else None,
                "active_plot": self._public_plot(self.active_plot) if self.active_plot else None,
                "last_event": self.last_event,
                "last_disarm": self.last_disarm,
                "last_error": self.last_error,
            }

    @staticmethod
    def _public_job(job: Dict[str, Any]) -> Dict[str, Any]:
        keys = ("job_id", "layer_name", "ink_color", "ink_name", "estimated_time",
                "progress_in_mm", "homing", "armed_at", "started_at")
        out = {k: job.get(k) for k in keys if k in job}
        if job.get("svg"):
            out["svg_sha256"] = job["svg"].get("sha256")
            out["svg_filename"] = job["svg"].get("original_filename")
        return out

    def _public_plot(self, plot: Dict[str, Any]) -> Dict[str, Any]:
        out = self._public_job(plot)
        out["source"] = plot["source"]
        out["paused"] = plot["paused"]
        out["shown_on_panel"] = plot["show_on_panel"]
        out["elapsed_time"] = round(self._elapsed(plot), 1)
        return out

    # ------------------------------------------------------------------ validation

    def _check_svg_for_arm(self, job: Dict[str, Any], identity: Optional[Dict[str, Any]]):
        if not identity:
            raise JobRequestError("No SVG loaded, or the upload is still in progress", 409)
        svg_job_id = identity.get("job_id")
        if not svg_job_id:
            raise JobRequestError(
                "The loaded SVG has no job_id; re-upload it with a job_id form field", 409,
                svg_filename=identity.get("original_filename"),
            )
        self._check_svg_job(job["job_id"], job.get("svg_sha256"), identity)

    @staticmethod
    def _check_svg_job(job_id, svg_sha256: Optional[str], identity: Dict[str, Any]):
        svg_job_id = identity.get("job_id")
        if job_id is not None and svg_job_id and str(svg_job_id) != str(job_id):
            raise JobRequestError(
                "Loaded SVG belongs to a different job", 409,
                svg_job_id=svg_job_id, requested_job_id=job_id,
            )
        if svg_sha256 and svg_sha256.lower() != (identity.get("sha256") or "").lower():
            raise JobRequestError(
                "Loaded SVG content does not match svg_sha256", 409,
                svg_sha256=identity.get("sha256"),
            )

    @staticmethod
    def _validate_panel_fields(p: Dict[str, Any], require: bool) -> Dict[str, Any]:
        """Validate the fields shown on the panel. With require=False, absent fields are None."""
        out: Dict[str, Any] = {}

        job_id = p.get("job_id")
        if job_id is not None or require:
            if not _valid_job_id(job_id):
                raise JobRequestError("job_id is required (non-empty string or integer)" if require
                                      else "job_id must be a non-empty string or integer")
        out["job_id"] = job_id

        ink_color = p.get("ink_color")
        out["ink_color"] = None
        if ink_color is not None or require:
            out["ink_color"] = _normalise_color(ink_color)
            if not out["ink_color"]:
                raise JobRequestError('ink_color is required as "#RRGGBB"' if require
                                      else 'ink_color must be "#RRGGBB"')

        ink_name = p.get("ink_name")
        if ink_name is not None and not isinstance(ink_name, str):
            raise JobRequestError("ink_name must be a string")
        out["ink_name"] = ink_name or None

        estimated_time = p.get("estimated_time")
        if estimated_time is not None or require:
            if not _is_number(estimated_time) or estimated_time < 0:
                raise JobRequestError("estimated_time is required (number of seconds, >= 0)" if require
                                      else "estimated_time must be a number of seconds, >= 0")
        out["estimated_time"] = estimated_time

        svg_sha256 = p.get("svg_sha256")
        if svg_sha256 is not None and not isinstance(svg_sha256, str):
            raise JobRequestError("svg_sha256 must be a hex string")
        out["svg_sha256"] = svg_sha256

        return out

    def _validate_arm_payload(self, p: Dict[str, Any]) -> Dict[str, Any]:
        layer_name = p.get("layer_name")
        if not isinstance(layer_name, str) or not layer_name.strip():
            raise JobRequestError("layer_name is required (string; a layer name or id from the loaded SVG, or \"all\")")

        fields = self._validate_panel_fields(p, require=True)

        config_content = p.get("config_content") or {}
        if not isinstance(config_content, (dict, str)):
            raise JobRequestError("config_content must be an object")

        progress_in_mm = p.get("progress_in_mm")
        if progress_in_mm is not None and (not _is_number(progress_in_mm) or progress_in_mm < 0):
            raise JobRequestError("progress_in_mm must be a number >= 0")

        time_data = p.get("time_data")
        if time_data is not None and not isinstance(time_data, dict):
            raise JobRequestError("time_data must be an object")

        return {
            **fields,
            "layer_name": layer_name,
            "config_content": config_content,
            "progress_in_mm": progress_in_mm,
            "time_data": time_data,
            "homing": _validate_homing(p),
        }

    def _remote_plot_screen(self, layer_name: str, body: Dict[str, Any],
                            identity: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Work out what the panel shows for a POST /plot. Explicit fields are
        validated strictly (400 on a bad value). Missing ones fall back to the
        legacy time_data fields, then to the SVG's job_id or filename.
        """
        fields = self._validate_panel_fields(body, require=False)

        elapsed_time = body.get("elapsed_time")
        if elapsed_time is not None and (not _is_number(elapsed_time) or elapsed_time < 0):
            raise JobRequestError("elapsed_time must be a number of seconds, >= 0")

        if identity:
            self._check_svg_job(fields["job_id"], fields["svg_sha256"], identity)

        time_data = body.get("time_data") if isinstance(body.get("time_data"), dict) else {}

        job_id = fields["job_id"]
        if job_id is None and identity:
            # Legacy callers send no job_id; the old firmware showed the filename.
            job_id = identity.get("job_id") or (identity.get("original_filename") or "")[:120]
        if not _valid_job_id(job_id):
            job_id = "plot"

        estimated_time = fields["estimated_time"]
        if estimated_time is None:
            estimated_time = _lenient_number(time_data.get("project_duration"))

        ink_color = fields["ink_color"]
        if ink_color is None and layer_name != "all":
            ink_color = _normalise_color(time_data.get("layer_color"))

        screen = {
            "job_id": job_id,
            "layer_name": layer_name,
            "ink_color": ink_color or DEFAULT_INK_COLOR,
            "ink_name": fields["ink_name"],
            "estimated_time": estimated_time,
            "elapsed_time": elapsed_time or 0,
            "progress_in_mm": body.get("progress_in_mm"),
        }

        if estimated_time is not None:
            message = build_panel_message("PLOTTING", screen, elapsed_time=screen["elapsed_time"])
            if len(encode_message(message)) > MAX_LINE_BYTES:
                raise JobRequestError(
                    f"PLOTTING message would exceed {MAX_LINE_BYTES} bytes; shorten job_id, layer_name or ink_name"
                )
        return screen
