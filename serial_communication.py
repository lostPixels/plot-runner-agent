"""
Serial link to the Plot Runner panel (LilyGo T-Display S3 AMOLED).

Protocol summary (see the firmware's "Plot Runner serial commands" doc):
  * One message per line, UTF-8, '\n' terminated, max 1023 bytes.
  * Host -> device requests: "AT", {"command":"ARMED",...},
    {"command":"PLOTTING",...}, {"command":"IDLE"}, {"command":"STATUS"}. Every request gets exactly one reply line:
    "OK", "ERROR: <reason>", or (for STATUS) a JSON STATUS object.
  * Device -> host events arrive at any time, even between a request and its
    reply: START_PLOT, DISARMED, DRAW_BULLSEYE (JSON) and DOUBLE_BUTTON_PRESS
    (plain text). Anything else is diagnostics and is ignored.

Design:
  * One I/O thread owns the port: it (re)connects, reads, and routes each line
    to the reply queue or the event queue.
  * Requests are serialised; each one waits up to REPLY_TIMEOUT for its reply.
  * Events are delivered to a single handler on a separate dispatcher thread,
    so the handler may itself send requests (e.g. IDLE) without deadlocking
    the reader.
  * Two synthetic events are also dispatched: {"command": "_CONNECTED"} after a
    (re)connect passes the AT check, and {"command": "_DISCONNECTED"}.
"""

import json
import logging
import os
import queue
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

import serial
import serial.tools.list_ports

logger = logging.getLogger(__name__)

MAX_LINE_BYTES = 1023

EVENT_CONNECTED = "_CONNECTED"
EVENT_DISCONNECTED = "_DISCONNECTED"


class DisplayError(Exception):
    """Base class for display communication failures."""


class DisplayUnavailable(DisplayError):
    """No display is connected."""


class DisplayTimeout(DisplayError):
    """The display did not reply in time."""


class DisplayRejected(DisplayError):
    """The display replied with 'ERROR: <reason>'."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def encode_message(msg: Any) -> bytes:
    """Encode a request as one compact line (without the trailing newline)."""
    line = msg if isinstance(msg, str) else json.dumps(msg, separators=(",", ":"), ensure_ascii=False)
    return line.encode("utf-8")


class PlotRunnerDisplay:
    """Connection to the Plot Runner panel. Use get_display() for the shared instance."""

    # USB VID/PID pairs that may be the panel. The T-Display S3 uses the ESP32-S3's
    # native USB (303A:1001); the others are common USB-UART bridges.
    KNOWN_VID_PID_PAIRS: List[Tuple[str, str]] = [
        ('303A', '1001'),  # Espressif native USB CDC (LilyGo T-Display S3)
        ('10C4', 'EA60'),  # Silicon Labs CP210x
        ('1A86', '7523'),  # CH340
        ('0403', '6001'),  # FTDI FT232R
    ]

    BAUD_RATE = 115200          # Ignored by native USB, set anyway.
    READ_TIMEOUT = 0.1          # Serial read poll interval (seconds).
    WRITE_TIMEOUT = 1.0
    REPLY_TIMEOUT = 1.0         # Per the firmware doc, 1 s is plenty.
    RECONNECT_INTERVAL = 3.0    # Delay between port scans while disconnected.
    MAX_CONSECUTIVE_TIMEOUTS = 2  # Reopen the port after this many missed replies.
    MAX_BUFFER_BYTES = 64 * 1024

    def __init__(self, port: Optional[str] = None):
        # Optional fixed port, e.g. PLOT_RUNNER_DISPLAY_PORT=/dev/ttyACM0.
        self.fixed_port = port or os.environ.get("PLOT_RUNNER_DISPLAY_PORT") or None

        self._ser: Optional[serial.Serial] = None
        self.device_path: Optional[str] = None
        self._connected = False        # Port open and AT check passed.
        self._port_open = False

        self._replies: "queue.Queue[Any]" = queue.Queue()
        self._events: "queue.Queue[Dict[str, Any]]" = queue.Queue()
        self._request_lock = threading.Lock()
        self._state_lock = threading.Lock()
        self._reopen_requested = threading.Event()
        self._stop = threading.Event()
        self._consecutive_timeouts = 0

        self._event_handler: Optional[Callable[[Dict[str, Any]], None]] = None
        self._io_thread: Optional[threading.Thread] = None
        self._dispatch_thread: Optional[threading.Thread] = None

    # ------------------------------------------------------------------ lifecycle

    def set_event_handler(self, handler: Callable[[Dict[str, Any]], None]):
        """Register the callback for device events. Called on the dispatcher thread."""
        self._event_handler = handler

    def start(self):
        """Start the I/O and dispatcher threads. Safe to call more than once."""
        if self._io_thread and self._io_thread.is_alive():
            return
        self._stop.clear()
        self._io_thread = threading.Thread(target=self._io_loop, name="display-io", daemon=True)
        self._dispatch_thread = threading.Thread(target=self._dispatch_loop, name="display-events", daemon=True)
        self._io_thread.start()
        self._dispatch_thread.start()
        logger.info("Display link started")

    def stop(self):
        self._stop.set()
        self._events.put({"command": "_STOP"})
        if self._io_thread:
            self._io_thread.join(timeout=2)
        if self._dispatch_thread:
            self._dispatch_thread.join(timeout=2)
        self._close_port()

    @property
    def connected(self) -> bool:
        return self._connected

    # ------------------------------------------------------------------ requests

    def ping(self) -> bool:
        """Send AT. Returns True on OK."""
        try:
            self.request("AT", require_connected=False)
            return True
        except DisplayError as e:
            logger.debug(f"AT failed: {e}")
            return False

    def arm(self, job: Dict[str, Any]):
        """Show a job on the Armed screen. Raises DisplayError on failure."""
        self.request(build_panel_message("ARMED", job))

    def plotting(self, job: Dict[str, Any], elapsed_time: float = 0):
        """Show the Progress screen for a plot the host started. Raises DisplayError on failure."""
        self.request(build_panel_message("PLOTTING", job, elapsed_time=elapsed_time))

    def idle(self):
        """Return the panel to the Idle screen. Raises DisplayError on failure."""
        self.request({"command": "IDLE"})

    def status(self) -> Dict[str, Any]:
        """Return the device's STATUS object. Raises DisplayError on failure."""
        return self.request({"command": "STATUS"}, expect_status=True)

    def request(self, msg: Any, timeout: Optional[float] = None, expect_status: bool = False,
                require_connected: bool = True) -> Any:
        """
        Send one request line and wait for its reply.

        Returns "OK" or, with expect_status, the STATUS dict.
        Raises DisplayUnavailable, DisplayTimeout or DisplayRejected.
        """
        timeout = self.REPLY_TIMEOUT if timeout is None else timeout
        data = encode_message(msg)
        if len(data) > MAX_LINE_BYTES:
            raise DisplayRejected(f"Line too long ({len(data)} bytes, max {MAX_LINE_BYTES})")

        with self._request_lock:
            ser = self._ser
            if ser is None or not self._port_open or (require_connected and not self._connected):
                raise DisplayUnavailable("Plot Runner display is not connected")

            # Drop late replies left over from an earlier timed-out request.
            self._drain_replies()

            try:
                ser.write(data + b"\n")
                ser.flush()
            except (serial.SerialException, OSError) as e:
                self._reopen_requested.set()
                raise DisplayUnavailable(f"Write failed: {e}")

            logger.debug(f"Display <- {data.decode('utf-8', 'replace')}")
            deadline = time.monotonic() + timeout
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    self._note_timeout(data)
                    raise DisplayTimeout(f"No reply to {data[:60].decode('utf-8', 'replace')}")
                try:
                    reply = self._replies.get(timeout=remaining)
                except queue.Empty:
                    continue

                if isinstance(reply, str) and reply.startswith("ERROR: "):
                    self._consecutive_timeouts = 0
                    raise DisplayRejected(reply[len("ERROR: "):])
                if expect_status and isinstance(reply, dict):
                    self._consecutive_timeouts = 0
                    return reply
                if not expect_status and reply == "OK":
                    self._consecutive_timeouts = 0
                    return reply
                # Reply of the wrong kind: a stale reply to an earlier request.
                logger.debug(f"Discarding out-of-sequence reply: {reply!r}")

    def _drain_replies(self):
        while True:
            try:
                stale = self._replies.get_nowait()
                logger.debug(f"Discarding stale reply: {stale!r}")
            except queue.Empty:
                return

    def _note_timeout(self, data: bytes):
        self._consecutive_timeouts += 1
        logger.warning(f"Display reply timeout ({self._consecutive_timeouts}) for {data[:60]!r}")
        if self._consecutive_timeouts >= self.MAX_CONSECUTIVE_TIMEOUTS:
            logger.warning("Display unresponsive, reopening port")
            self._consecutive_timeouts = 0
            self._reopen_requested.set()

    # ------------------------------------------------------------------ port handling

    def find_port(self) -> Optional[str]:
        """Find the panel's serial port, skipping the NextDraw (EiBotBoard)."""
        if self.fixed_port:
            return self.fixed_port
        try:
            for port in serial.tools.list_ports.comports():
                if "EiBotBoard" in (port.description or "") or "EiBotBoard" in (port.product or ""):
                    continue
                if port.vid is None or port.pid is None:
                    continue
                pair = (f"{port.vid:04X}", f"{port.pid:04X}")
                if pair in self.KNOWN_VID_PID_PAIRS:
                    return port.device
        except Exception as e:
            logger.error(f"Error scanning serial ports: {e}")
        return None

    def _open_port(self) -> bool:
        path = self.find_port()
        if not path:
            return False
        try:
            # DTR/RTS are left at pyserial's defaults: RTS asserted with DTR
            # de-asserted would reset the board.
            ser = serial.Serial(
                port=path,
                baudrate=self.BAUD_RATE,
                timeout=self.READ_TIMEOUT,
                write_timeout=self.WRITE_TIMEOUT,
            )
            ser.reset_input_buffer()
        except (serial.SerialException, OSError, ValueError) as e:
            logger.debug(f"Could not open display port {path}: {e}")
            return False

        with self._state_lock:
            self._ser = ser
            self.device_path = path
            self._port_open = True
            self._connected = False
        self._drain_replies()
        logger.info(f"Opened display port {path}")
        return True

    def _close_port(self):
        with self._state_lock:
            was_connected = self._connected
            ser, self._ser = self._ser, None
            self._port_open = False
            self._connected = False
        if ser is not None:
            try:
                ser.close()
            except Exception:
                pass
        if was_connected:
            logger.warning("Display disconnected")
            self._events.put({"command": EVENT_DISCONNECTED})

    # ------------------------------------------------------------------ threads

    def _io_loop(self):
        buf = b""
        while not self._stop.is_set():
            if self._reopen_requested.is_set():
                self._reopen_requested.clear()
                self._close_port()
                buf = b""

            if self._ser is None:
                if self._open_port():
                    # Handshake runs on the dispatcher thread, which can wait for replies.
                    self._events.put({"command": "_HANDSHAKE"})
                else:
                    self._stop.wait(self.RECONNECT_INTERVAL)
                continue

            try:
                chunk = self._ser.read(4096)
            except (serial.SerialException, OSError, TypeError, AttributeError) as e:
                logger.warning(f"Display read failed: {e}")
                self._close_port()
                buf = b""
                continue

            if not chunk:
                continue
            buf += chunk
            while b"\n" in buf:
                raw, buf = buf.split(b"\n", 1)
                self._route_line(raw.decode("utf-8", "replace").strip())
            if len(buf) > self.MAX_BUFFER_BYTES:
                logger.warning("Discarding oversized unterminated display output")
                buf = b""

    def _route_line(self, line: str):
        if not line:
            return
        if line == "OK" or line.startswith("ERROR: "):
            self._replies.put(line)
            return
        if line.startswith("{"):
            try:
                msg = json.loads(line)
            except ValueError:
                logger.debug(f"Display diagnostics (bad JSON): {line}")
                return
            if not isinstance(msg, dict):
                return
            if msg.get("command") == "STATUS":
                self._replies.put(msg)
            else:
                logger.info(f"Display event: {line}")
                self._events.put(msg)
            return
        if line == "DOUBLE_BUTTON_PRESS":
            self._events.put({"command": line})
            return
        logger.debug(f"Display diagnostics: {line}")

    def _dispatch_loop(self):
        while not self._stop.is_set():
            event = self._events.get()
            command = event.get("command")
            if command == "_STOP":
                return
            if command == "_HANDSHAKE":
                self._handshake()
                continue
            handler = self._event_handler
            if handler is None:
                continue
            try:
                handler(event)
            except Exception as e:
                logger.error(f"Error handling display event {command}: {e}", exc_info=True)

    def _handshake(self):
        # The board may still be printing boot chatter; give AT a few tries.
        for _ in range(3):
            if self._ser is None:
                return
            if self.ping():
                with self._state_lock:
                    self._connected = self._ser is not None
                if self._connected:
                    logger.info(f"Connected to Plot Runner display on {self.device_path}")
                    if self._event_handler:
                        try:
                            self._event_handler({"command": EVENT_CONNECTED})
                        except Exception as e:
                            logger.error(f"Error handling display connect: {e}", exc_info=True)
                return
            time.sleep(0.5)
        logger.warning(f"Device on {self.device_path} did not answer AT; will retry")
        self._reopen_requested.set()
        self._stop.wait(self.RECONNECT_INTERVAL)


def build_panel_message(command: str, job: Dict[str, Any], elapsed_time: Optional[float] = None) -> Dict[str, Any]:
    """
    Build an ARMED or PLOTTING message from a job dict with job_id, layer_name,
    ink_color, estimated_time and optional ink_name. PLOTTING may add
    elapsed_time (seconds already plotted).
    """
    msg = {
        "command": command,
        "job_id": job["job_id"],
        "layer_name": job["layer_name"],
        "ink_color": job["ink_color"],
        "estimated_time": job["estimated_time"],
    }
    if job.get("ink_name"):
        msg["ink_name"] = job["ink_name"]
    if command == "PLOTTING" and elapsed_time:
        msg["elapsed_time"] = elapsed_time
    return msg


_display_instance: Optional[PlotRunnerDisplay] = None
_display_lock = threading.Lock()


def get_display() -> PlotRunnerDisplay:
    """Get the shared display instance (not started; call start())."""
    global _display_instance
    if _display_instance is None:
        with _display_lock:
            if _display_instance is None:
                _display_instance = PlotRunnerDisplay()
    return _display_instance
