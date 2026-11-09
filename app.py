"""
NextDraw Plotter API Server - Simplified Single SVG Workflow
A Flask application for controlling NextDraw plotters with a single current SVG file.
"""

import os
import threading
import time
import logging
from datetime import datetime
from flask import Flask, request, jsonify, g
from flask_cors import CORS
from logging.handlers import RotatingFileHandler
from werkzeug.exceptions import RequestEntityTooLarge

from plotter_controller import PlotterController
from svg_manager import SVGManager
from serial_communication import get_display
from display_jobs import DisplayJobController, JobRequestError

# Initialize Flask app
app = Flask(__name__)
CORS(app)

# Configure Flask for large file uploads
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500MB limit
app.config['REQUEST_TIMEOUT'] = 300  # 5 minutes timeout

# Configure logging
if not os.path.exists('logs'):
    os.makedirs('logs')

# Get the root logger
root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)

# Remove any existing handlers to avoid duplicates after reload
for handler in root_logger.handlers[:]:
    root_logger.removeHandler(handler)

# Create formatter
formatter = logging.Formatter('%(asctime)s %(levelname)s: %(message)s')

# Create and configure file handler
file_handler = RotatingFileHandler('logs/app.log', maxBytes=10000000, backupCount=5)
file_handler.setFormatter(formatter)
file_handler.setLevel(logging.INFO)

# Create and configure console handler
console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)
console_handler.setLevel(logging.INFO)

# Add handlers to root logger
root_logger.addHandler(file_handler)
root_logger.addHandler(console_handler)

logger = logging.getLogger(__name__)
logger.info("Logging system initialized/reinitialized")

# Initialize core components
plotter_controller = PlotterController()
svg_manager = SVGManager()

# Global system status
system_status = {
    "plotter_status": "IDLE",
    "current_layer": None,
    "current_job_id": None,
    "plot_source": None,
    "plot_progress": 0,
    "last_error": None,
    "time_data": None,
    "uptime_start": datetime.now().isoformat()
}

# Lock for thread safety
status_lock = threading.Lock()

@app.before_request
def before_request():
    """Log request start and track timing"""
    g.start_time = time.time()
    logger.info(f"Request started: {request.method} {request.path}")


@app.after_request
def after_request(response):
    """Log request completion and duration"""
    if hasattr(g, 'start_time'):
        elapsed = time.time() - g.start_time
        logger.info(f"Request completed: {request.method} {request.path} - Status: {response.status_code} - Duration: {elapsed:.3f}s")
        if elapsed > 1.0:
            logger.warning(f"Slow request detected: {request.method} {request.path} took {elapsed:.3f}s")
    return response


@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": "3.0.0",
        "uptime_start": system_status['uptime_start']
    }), 200


@app.route('/status', methods=['GET'])
def get_status():
    """Get comprehensive system status"""
    try:
        logger.debug("get_status: Acquiring status lock")
        with status_lock:
            logger.debug("get_status: Lock acquired, getting SVG status")
            svg_status = svg_manager.get_svg_status()
            logger.debug("get_status: SVG status retrieved")

            response = {
                "timestamp": datetime.now().isoformat(),
                "system": {
                    "plotter_status": system_status['plotter_status'],
                    "current_layer": system_status['current_layer'],
                    "current_job_id": system_status['current_job_id'],
                    "plot_source": system_status['plot_source'],
                    "time_data": system_status['time_data'],
                    "uptime_start": system_status['uptime_start']
                },
                "svg": svg_status
            }

        # Outside status_lock: the display controller takes its own lock first
        # and then status_lock, so never nest them the other way round.
        response["display"] = display_jobs.get_state()
        return jsonify(response), 200

    except Exception as e:
        logger.error(f"Error getting status: {str(e)}")
        return jsonify({"error": "Failed to get status"}), 500


@app.route('/api/svg', methods=['POST'])
def upload_svg():
    """Upload a new SVG file - supports both direct and chunked upload"""
    try:
        # Check if it's a chunked upload
        if 'chunk_number' in request.form:
            # Handle chunked upload
            chunk_info = {
                'chunk_number': int(request.form.get('chunk_number', 0)),
                'total_chunks': int(request.form.get('total_chunks', 1)),
                'file_id': request.form.get('file_id', 'svg_upload'),
                'filename': request.form.get('filename', 'design.svg'),
                'job_id': (request.form.get('job_id') or '').strip() or None
            }

            if 'chunk_data' not in request.files:
                return jsonify({"error": "No chunk data provided"}), 400

            chunk_file = request.files['chunk_data']
            chunk_data = chunk_file.read()

            if chunk_info['chunk_number'] == 0:
                display_jobs.on_svg_changed()

            result = svg_manager.upload_svg_chunked(chunk_data, chunk_info)

            return jsonify(result), 200

        else:
            # Handle direct upload
            if 'file' not in request.files:
                return jsonify({"error": "No file provided"}), 400

            file = request.files['file']
            if file.filename == '':
                return jsonify({"error": "No file selected"}), 400

            # Read file data
            file_data = file.read()

            # Check file size
            if len(file_data) > app.config['MAX_CONTENT_LENGTH']:
                return jsonify({"error": "File too large"}), 413

            # Upload the SVG (an armed job no longer applies once the file changes)
            display_jobs.on_svg_changed()
            job_id = (request.form.get('job_id') or '').strip() or None
            svg_info = svg_manager.upload_svg(file_data, file.filename, job_id=job_id)

            logger.info(f"SVG uploaded successfully: {file.filename}")

            return jsonify({
                "message": "SVG uploaded successfully",
                "svg": svg_info
            }), 200

    except Exception as e:
        logger.error(f"Error uploading SVG: {str(e)}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/svg', methods=['GET'])
def get_svg_status():
    """Get the status of the current SVG"""
    try:
        logger.debug("GET /api/svg: Getting SVG status")
        svg_status = svg_manager.get_svg_status()
        logger.debug(f"GET /api/svg: SVG status retrieved: {bool(svg_status)}")

        if svg_status:
            return jsonify(svg_status), 200
        else:
            return jsonify({
                "message": "No SVG loaded",
                "is_ready": False
            }), 200

    except Exception as e:
        logger.error(f"Error getting SVG status: {str(e)}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/svg/filename', methods=['GET'])
def get_svg_filename():
    """Get the filename of the current SVG"""
    try:
        filename = svg_manager.get_original_filename()

        if filename:
            return jsonify({
                "filename": filename,
                "has_svg": True
            }), 200
        else:
            return jsonify({
                "filename": None,
                "has_svg": False
            }), 200

    except Exception as e:
        logger.error(f"Error getting SVG filename: {str(e)}")
        return jsonify({"error": str(e)}), 500


@app.route('/plot/<layer_name>', methods=['POST'])
def plot_layer(layer_name):
    """Execute plotting for a specific layer by name"""
    request_start_time = time.time()
    try:
        logger.debug(f"plot_layer: Checking if SVG is ready for layer {layer_name}")
        # Check if SVG is ready
        if not svg_manager.is_svg_ready():
            return jsonify({"error": "No SVG uploaded or SVG not ready"}), 400

        # Check if plotter is busy
        with status_lock:
            if system_status['plotter_status'] != "IDLE":
                return jsonify({
                    "error": "Plotter is busy",
                    "current_status": system_status['plotter_status']
                }), 409

        # Check if layer is valid
        if not svg_manager.is_valid_layer(layer_name):
            available_layers = svg_manager.get_available_layers()
            return jsonify({
                "error": f"Layer '{layer_name}' not found",
                "available_layers": available_layers
            }), 404

        # Get SVG file path
        svg_path = svg_manager.get_svg_file_path()
        svg_name = svg_manager.get_original_filename()

        # Track SVG file size
        svg_size_mb = 0
        if svg_path and os.path.exists(svg_path):
            svg_size_bytes = os.path.getsize(svg_path)
            svg_size_mb = svg_size_bytes / (1024 * 1024)
            logger.info(f"SVG file '{svg_name}' size: {svg_size_mb:.2f} MB ({svg_size_bytes:,} bytes)")

        if not svg_path:
            return jsonify({"error": "No SVG file found"}), 404

        # Get config from request body
        body = request.get_json(silent=True) or {}
        config_overrides = body.get('config_content', {})
        if config_overrides:
            logger.info(f"Received config with {len(config_overrides)} parameters")

        logger.info(f"Received request to plot layer '{layer_name}' from {svg_name}")

        pre_plot_elapsed = time.time() - request_start_time
        logger.info(f"Pre-plot preparation time: {pre_plot_elapsed:.3f}s | SVG size: {svg_size_mb:.2f}MB")

        # Starts the plot and shows it on the panel (PLOTTING). Replaces anything armed.
        try:
            started, error = display_jobs.start_remote_plot(layer_name, body)
        except JobRequestError as e:
            logger.warning(f"Plot request refused: {e.message}")
            return jsonify(e.to_dict()), e.status_code
        if not started:
            with status_lock:
                current = system_status['plotter_status']
            return jsonify({"error": error, "current_status": current}), 409

        request_elapsed = time.time() - request_start_time
        logger.info(f"Plot request completed in {request_elapsed:.3f}s (returning 202 to client)")

        return jsonify({
            "message": "Plot started",
            "layer_name": layer_name,
            "svg_name": svg_name
        }), 202

    except Exception as e:
        logger.error(f"Error starting plot for layer {layer_name}: {str(e)}")
        return jsonify({"error": str(e)}), 500


def start_plot_job(layer_name, config_overrides=None, time_data=None, progress_in_mm=None,
                   job_id=None, source="api", on_finished=None, request_start_time=None):
    """
    Start plotting a layer of the loaded SVG in a background thread.

    Used by POST /plot/<layer> and by the panel's Start button (START_PLOT).
    Returns (started, error). If started, on_finished(outcome) is called once the
    plot ends, with outcome "completed", "paused" or "failed".
    """
    request_start_time = request_start_time or time.time()
    svg_path = svg_manager.get_svg_file_path()
    svg_name = svg_manager.get_original_filename()
    if not svg_path or not os.path.exists(svg_path):
        return False, "No SVG file found"

    # Check-and-set under one lock so two starts can't both win.
    with status_lock:
        if system_status['plotter_status'] != "IDLE":
            return False, f"Plotter is busy ({system_status['plotter_status']})"
        system_status['plotter_status'] = "PLOTTING"
        system_status['current_layer'] = layer_name
        system_status['current_job_id'] = job_id
        system_status['plot_source'] = source
        system_status['plot_progress'] = 0
        system_status['time_data'] = time_data

    def execute_plot():
        plot_thread_start = time.time()
        logger.info(f"Plot thread started - Time from request: {plot_thread_start - request_start_time:.3f}s")
        outcome = "failed"

        try:
            controller_start = time.time()
            logger.info(f"Calling plotter_controller.plot_file() - Time from request: {controller_start - request_start_time:.3f}s")
            result = plotter_controller.plot_file(
                svg_path,
                config_overrides=config_overrides or {},
                job_name=f"{svg_name}_{layer_name}",
                layer_name=layer_name,
                progress_in_mm=progress_in_mm
            )

            controller_end = time.time()
            logger.info(f"plotter_controller.plot_file() returned - Duration: {controller_end - controller_start:.3f}s")

            # Check the result to see if it was successful
            success = result.get('success', False) if result else False
            if success:
                outcome = "completed"
            elif result and 'paused' in str(result.get('message', '')).lower():
                outcome = "paused"
            elif result and result.get('error') == "Job was cancelled":
                outcome = "stopped"

            with status_lock:
                if outcome == "stopped":
                    # POST /plot/stop already reset the status; don't overwrite it with ERROR.
                    logger.info(f"Plot of layer {layer_name} stopped")
                    return
                if outcome == "paused":
                    # Resumable: keep the layer/job so /status still says what's paused.
                    system_status['plotter_status'] = "PAUSED"
                    logger.info(f"Plot of layer {layer_name} paused")
                    return
                if success:
                    system_status['plotter_status'] = "IDLE"
                    system_status['plot_progress'] = 100
                    system_status['time_data'] = None
                    logger.info(f"Successfully plotted layer {layer_name}")
                else:
                    system_status['plotter_status'] = "ERROR"
                    system_status['last_error'] = "Plot execution failed"
                    system_status['time_data'] = None
                    logger.error(f"Failed to plot layer {layer_name}")

                system_status['current_layer'] = None
                system_status['current_job_id'] = None
                system_status['plot_source'] = None

        except Exception as e:
            logger.error(f"Error executing plot for layer {layer_name}: {str(e)}")
            with status_lock:
                system_status['plotter_status'] = "ERROR"
                system_status['last_error'] = str(e)
                system_status['current_layer'] = None
                system_status['current_job_id'] = None
                system_status['plot_source'] = None
                system_status['time_data'] = None

        finally:
            if on_finished:
                try:
                    on_finished(outcome)
                except Exception as e:
                    logger.error(f"Error in plot finished callback: {e}", exc_info=True)

    plot_thread = threading.Thread(target=execute_plot, daemon=True)
    plot_thread.start()
    return True, None


def start_bullseye_job():
    """Draw the bullseye in the background (the panel's Draw Bullseye button)."""
    with status_lock:
        if system_status['plotter_status'] != "IDLE":
            return False, f"Plotter is busy ({system_status['plotter_status']})"
        system_status['plotter_status'] = "PLOTTING"
        system_status['current_layer'] = None
        system_status['current_job_id'] = None
        system_status['plot_source'] = "bullseye"

    def run():
        try:
            result = plotter_controller.draw_bullseye()
            success = bool(result and result.get('success'))
        except Exception as e:
            logger.error(f"Bullseye failed: {e}")
            success = False
        with status_lock:
            system_status['plotter_status'] = "IDLE" if success else "ERROR"
            if not success:
                system_status['last_error'] = "Bullseye plot failed"
            system_status['plot_source'] = None

    threading.Thread(target=run, daemon=True).start()
    logger.info("Drawing bullseye (requested from display)")
    return True, None


def is_plotter_idle():
    with status_lock:
        return system_status['plotter_status'] == "IDLE"


@app.route('/arm', methods=['POST'])
def arm_job():
    """Arm one layer of the loaded SVG on the Plot Runner panel.

    The plot starts when the operator presses Start on the panel.
    """
    try:
        armed = display_jobs.arm(request.get_json(silent=True))
        return jsonify({"message": "Armed", "armed_job": armed}), 200
    except JobRequestError as e:
        logger.warning(f"Arm refused: {e.message}")
        return jsonify(e.to_dict()), e.status_code
    except Exception as e:
        logger.error(f"Error arming job: {str(e)}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route('/arm', methods=['GET'])
def get_arm_state():
    """Current panel state, armed job and last panel event."""
    return jsonify(display_jobs.get_state()), 200


@app.route('/arm', methods=['DELETE'])
def disarm_job():
    """Cancel the armed job and return the panel to IDLE."""
    try:
        had_job = display_jobs.disarm("host")
        return jsonify({"message": "Disarmed" if had_job else "Nothing was armed", "disarmed": had_job}), 200
    except Exception as e:
        logger.error(f"Error disarming: {str(e)}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route('/plot/stop', methods=['POST'])
def stop_plot():
    """Stop current plotting operation"""
    try:
        success = plotter_controller.stop()

        with status_lock:
            if success:
                system_status['plotter_status'] = "IDLE"
                system_status['current_layer'] = None
                system_status['current_job_id'] = None
                system_status['plot_source'] = None
                system_status['plot_progress'] = 0

        if success:
            display_jobs.plot_stopped()

        return jsonify({
            "message": "Plot stopped" if success else "Failed to stop plot",
            "success": success
        }), 200 if success else 500

    except Exception as e:
        logger.error(f"Error stopping plot: {str(e)}")
        return jsonify({"error": str(e)}), 500


@app.route('/plot/pause', methods=['POST'])
def pause_plot():
    """Pause current plotting operation"""
    try:
        success = plotter_controller.pause()

        with status_lock:
            if success:
                system_status['plotter_status'] = "PAUSED"

        if success:
            display_jobs.plot_paused()

        return jsonify({
            "message": "Plot paused" if success else "Failed to pause plot",
            "success": success
        }), 200 if success else 500

    except Exception as e:
        logger.error(f"Error pausing plot: {str(e)}")
        return jsonify({"error": str(e)}), 500


@app.route('/plot/resume', methods=['POST'])
def resume_plot():
    """Resume paused plotting operation"""
    try:
        success = plotter_controller.resume()

        with status_lock:
            if success:
                system_status['plotter_status'] = "PLOTTING"
                logger.info("Plot resume initiated, status set to PLOTTING")
                # The background status sync thread will handle tracking when it completes

        if success:
            display_jobs.plot_resumed()

        return jsonify({
            "message": "Plot resumed" if success else "Failed to resume plot",
            "success": success
        }), 200 if success else 500

    except Exception as e:
        logger.error(f"Error resuming plot: {str(e)}")
        return jsonify({"error": str(e)}), 500


@app.route('/svg/clear', methods=['DELETE'])
def clear_svg():
    """Clear current SVG from memory"""
    try:
        # Check if plotter is busy
        with status_lock:
            if system_status['plotter_status'] == "PLOTTING":
                return jsonify({"error": "Cannot clear SVG while plotting"}), 409

        display_jobs.on_svg_changed()
        success = svg_manager.clear_svg()

        if success:
            logger.info("SVG cleared successfully")
            return jsonify({"message": "SVG cleared"}), 200
        else:
            return jsonify({"message": "No SVG to clear"}), 404

    except Exception as e:
        logger.error(f"Error clearing SVG: {str(e)}")
        return jsonify({"error": str(e)}), 500


@app.route('/utility/<command>', methods=['POST'])
def utility_command(command):
    """Execute utility commands"""
    try:
        data = request.get_json() or {}

        result = plotter_controller.execute_utility(command, data)
        return jsonify({"result": result})
    except Exception as e:
        logger.error(f"Error executing utility command {command}: {str(e)}")
        return jsonify({"error": str(e)}), 500


@app.route('/logs', methods=['GET'])
def get_logs():
    """Get recent log entries"""
    try:
        lines = request.args.get('lines', 100, type=int)
        log_file = 'logs/app.log'

        if not os.path.exists(log_file):
            return jsonify({"logs": []})

        with open(log_file, 'r') as f:
            logs = f.readlines()

        # Return last N lines
        recent_logs = logs[-lines:] if len(logs) > lines else logs
        return jsonify({"logs": [log.strip() for log in recent_logs]})
    except Exception as e:
        logger.error(f"Error getting logs: {str(e)}")
        return jsonify({"error": str(e)}), 500


# Error handlers
@app.errorhandler(404)
def not_found(error):
    return jsonify({"error": "Endpoint not found"}), 404


@app.errorhandler(RequestEntityTooLarge)
def request_entity_too_large(error):
    return jsonify({
        "error": "File too large",
        "max_size_mb": app.config['MAX_CONTENT_LENGTH'] / (1024 * 1024)
    }), 413


@app.errorhandler(500)
def internal_error(error):
    logger.error(f"Internal server error: {str(error)}")
    return jsonify({"error": "Internal server error"}), 500


# Update plotter progress callback
def update_plot_progress(progress):
    """Callback to update plot progress"""
    with status_lock:
        system_status['plot_progress'] = progress


# Set the progress callback
plotter_controller.set_progress_callback(update_plot_progress)


# Background status sync thread
def sync_status_with_controller():
    """Continuously sync app status with plotter controller status"""
    last_controller_status = None

    while True:
        try:
            time.sleep(0.5)  # Check every 500ms

            # Get current plotter controller status
            controller_status = plotter_controller.get_status()
            current_status = controller_status.get('status', 'DISCONNECTED')

            # Only update if status changed
            if current_status != last_controller_status:
                with status_lock:
                    # Map controller status to app status
                    if current_status == 'IDLE':
                        if system_status['plotter_status'] in ['PLOTTING', 'PAUSED', 'ERROR']:
                            system_status['plotter_status'] = "IDLE"
                            system_status['current_layer'] = None
                            system_status['current_job_id'] = None
                            system_status['plot_source'] = None
                            system_status['plot_progress'] = 0
                            logger.info(f"Status sync: Controller is IDLE, app status updated from {system_status['plotter_status']} to IDLE")

                    elif current_status == 'PLOTTING':
                        if system_status['plotter_status'] != 'PLOTTING':
                            system_status['plotter_status'] = "PLOTTING"
                            logger.info("Status sync: Controller is PLOTTING")

                    elif current_status == 'PAUSED':
                        if system_status['plotter_status'] != 'PAUSED':
                            system_status['plotter_status'] = "PAUSED"
                            logger.info("Status sync: Controller is PAUSED")

                    elif current_status == 'ERROR':
                        if system_status['plotter_status'] != 'ERROR':
                            system_status['plotter_status'] = "ERROR"
                            system_status['last_error'] = controller_status.get('last_error', 'Unknown error')
                            logger.error(f"Status sync: Controller ERROR - {system_status['last_error']}")

                last_controller_status = current_status

                # Outside status_lock (lock order: display_jobs, then status_lock).
                # Lets the panel notice the end of a resumed plot.
                if current_status in ('IDLE', 'ERROR'):
                    display_jobs.controller_finished()

        except Exception as e:
            logger.error(f"Error in status sync thread: {str(e)}")
            time.sleep(2)  # Wait longer on error


# Plot Runner panel: serial link, armed-job state and device events
display_jobs = DisplayJobController(
    get_display(),
    svg_manager,
    start_plot=start_plot_job,
    is_plotter_idle=is_plotter_idle,
    start_bullseye=start_bullseye_job,
)
display_jobs.start()


# Start background status sync thread
status_sync_thread = threading.Thread(target=sync_status_with_controller, daemon=True)
status_sync_thread.start()
logger.info("Started background status sync thread")


if __name__ == '__main__':
    logger.info("Starting NextDraw Plotter API Server (Simplified)")
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
