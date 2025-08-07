"""
NextDraw Plotter API Server - Simplified Single SVG Workflow
A Flask application for controlling NextDraw plotters with a single current SVG file.
"""

import os
import json
import threading
import time
import logging
from datetime import datetime
from flask import Flask, request, jsonify, g
from flask_cors import CORS
from logging.handlers import RotatingFileHandler
from serial_communication import sendPlotStartToSerial
from werkzeug.exceptions import RequestEntityTooLarge

from plotter_controller import PlotterController
from svg_manager import SVGManager

# Initialize Flask app
app = Flask(__name__)
CORS(app)

# Configure Flask for large file uploads
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500MB limit
app.config['REQUEST_TIMEOUT'] = 300  # 5 minutes timeout

# Configure logging
if not os.path.exists('logs'):
    os.makedirs('logs')

logging.basicConfig(
    handlers=[
        RotatingFileHandler('logs/app.log', maxBytes=10000000, backupCount=5),
        logging.StreamHandler()
    ],
    level=logging.INFO,
    format='%(asctime)s %(levelname)s: %(message)s'
)

logger = logging.getLogger(__name__)

# Initialize core components
plotter_controller = PlotterController()
svg_manager = SVGManager()

# Global system status
system_status = {
    "plotter_status": "IDLE",
    "current_layer": None,
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
                    "time_data": system_status['time_data'],
                    "uptime_start": system_status['uptime_start']
                },
                "svg": svg_status
            }

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
                'filename': request.form.get('filename', 'design.svg')
            }

            if 'chunk_data' not in request.files:
                return jsonify({"error": "No chunk data provided"}), 400

            chunk_file = request.files['chunk_data']
            chunk_data = chunk_file.read()

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

            # Upload the SVG
            svg_info = svg_manager.upload_svg(file_data, file.filename)

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

        if not svg_path:
            return jsonify({"error": "No SVG file found"}), 404

        # Get config from request body
        config_overrides = {}
        if request.json:
            config_overrides = request.json.get('config_content', {})
            logger.info(f"Received config with {len(config_overrides)} parameters")

        logger.info(f"Received request to plot layer '{layer_name}' from {svg_name}")

        time_data = request.json.get('time_data');

        try:
            sendPlotStartToSerial(time_data, svg_name, layer_name)
        except Exception as e:
            logger.error(f"Error sending plot data to serial display: {str(e)}")


        # Start plotting in background thread
        def execute_plot():
            try:
                with status_lock:
                    system_status['plotter_status'] = "PLOTTING"
                    system_status['current_layer'] = layer_name
                    system_status['plot_progress'] = 0
                    system_status['time_data'] = time_data

                # Execute the plot
                success = plotter_controller.plot_file(
                    svg_path,
                    config_overrides=config_overrides,
                    job_name=f"{svg_name}_{layer_name}",
                    layer_name=layer_name
                )

                #time.sleep(15000)
                success = True

                with status_lock:
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

            except Exception as e:
                logger.error(f"Error executing plot for layer {layer_name}: {str(e)}")
                with status_lock:
                    system_status['plotter_status'] = "ERROR"
                    system_status['last_error'] = str(e)
                    system_status['current_layer'] = None
                    system_status['time_data'] = None

        # Start plot thread
        plot_thread = threading.Thread(target=execute_plot, daemon=True)
        plot_thread.start()


        return jsonify({
            "message": "Plot started",
            "layer_name": layer_name,
            "svg_name": svg_name
        }), 202

    except Exception as e:
        logger.error(f"Error starting plot for layer {layer_name}: {str(e)}")
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
                system_status['plot_progress'] = 0

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


if __name__ == '__main__':
    logger.info("Starting NextDraw Plotter API Server (Simplified)")
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
