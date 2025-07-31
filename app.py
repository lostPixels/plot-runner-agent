"""
NextDraw Plotter API Server - Simplified Project-Based Workflow
A Flask application for controlling NextDraw plotters with multi-layer project support.
"""

import os
import json
import threading
import time
import logging
from datetime import datetime
from flask import Flask, request, jsonify
from flask_cors import CORS
from logging.handlers import RotatingFileHandler
from werkzeug.exceptions import RequestEntityTooLarge

from plotter_controller import PlotterController
from config_manager import ConfigManager
from project_manager import ProjectManager, ProjectStatus

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
config_manager = ConfigManager()
plotter_controller = PlotterController(config_manager)
project_manager = ProjectManager()

# Global system status
system_status = {
    "plotter_status": "IDLE",
    "current_layer": None,
    "plot_progress": 0,
    "last_error": None,
    "uptime_start": datetime.now().isoformat()
}

# Lock for thread safety
status_lock = threading.Lock()


@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": "2.0.0",
        "uptime_start": system_status['uptime_start']
    }), 200


@app.route('/status', methods=['GET'])
def get_status():
    """Get comprehensive system and project status"""
    try:
        with status_lock:
            project_status = project_manager.get_project_status()

            response = {
                "timestamp": datetime.now().isoformat(),
                "system": {
                    "plotter_status": system_status['plotter_status'],
                    "current_layer": system_status['current_layer'],
                    "plot_progress": system_status['plot_progress'],
                    "last_error": system_status['last_error'],
                    "plotter_connected": plotter_controller.is_connected()
                },
                "project": project_status
            }

            return jsonify(response), 200

    except Exception as e:
        logger.error(f"Error getting status: {str(e)}")
        return jsonify({"error": "Failed to get status"}), 500


@app.route('/project', methods=['POST'])
def create_project():
    """Create a new project, clearing any existing project"""
    try:
        data = request.json
        if not data:
            return jsonify({"error": "No project data provided"}), 400

        # Validate required fields
        if 'total_layers' not in data:
            return jsonify({"error": "total_layers is required"}), 400

        if not isinstance(data['total_layers'], int) or data['total_layers'] < 1:
            return jsonify({"error": "total_layers must be a positive integer"}), 400

        # Create the project
        project_info = project_manager.create_project(data)

        logger.info(f"Created new project: {project_info['id']}")

        return jsonify({
            "message": "Project created successfully",
            "project": project_info
        }), 201

    except Exception as e:
        logger.error(f"Error creating project: {str(e)}")
        return jsonify({"error": str(e)}), 500


@app.route('/project/layer/<layer_id>', methods=['POST'])
def upload_layer(layer_id):
    """Upload a layer SVG file - supports both direct and chunked upload"""
    try:
        # Check if project exists
        if not project_manager.current_project:
            return jsonify({"error": "No active project"}), 400

        # Check if it's a chunked upload
        if 'chunk_number' in request.form:
            # Handle chunked upload
            chunk_info = {
                'chunk_number': int(request.form.get('chunk_number', 0)),
                'total_chunks': int(request.form.get('total_chunks', 1)),
                'file_id': request.form.get('file_id', layer_id),
                'filename': request.form.get('filename', f'{layer_id}.svg')
            }

            if 'chunk_data' not in request.files:
                return jsonify({"error": "No chunk data provided"}), 400

            chunk_file = request.files['chunk_data']
            chunk_data = chunk_file.read()

            result = project_manager.upload_layer_chunked(layer_id, chunk_data, chunk_info)

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

            # Upload the layer
            layer_info = project_manager.upload_layer(layer_id, file_data, file.filename)

            logger.info(f"Layer {layer_id} uploaded successfully")

            return jsonify({
                "message": "Layer uploaded successfully",
                "layer": layer_info
            }), 200

    except Exception as e:
        logger.error(f"Error uploading layer {layer_id}: {str(e)}")
        return jsonify({"error": str(e)}), 500


@app.route('/plot/<layer_id>', methods=['POST'])
def plot_layer(layer_id):
    """Execute plotting for a specific layer"""
    try:
        # Check if project is ready
        if not project_manager.is_project_ready():
            return jsonify({"error": "Project not ready for plotting"}), 400

        # Check if plotter is busy
        with status_lock:
            if system_status['plotter_status'] != "IDLE":
                return jsonify({
                    "error": "Plotter is busy",
                    "current_status": system_status['plotter_status']
                }), 409

        # Get layer file path
        svg_path = project_manager.get_layer_file_path(layer_id)
        if not svg_path:
            return jsonify({"error": f"Layer {layer_id} not found"}), 404

        # Get layer info
        layer_info = project_manager.get_layer_info(layer_id)
        if not layer_info:
            return jsonify({"error": f"Layer {layer_id} info not found"}), 404

        # Start plotting in background thread
        def execute_plot():
            try:
                with status_lock:
                    system_status['plotter_status'] = "PLOTTING"
                    system_status['current_layer'] = layer_id
                    system_status['plot_progress'] = 0

                project_manager.update_project_status(ProjectStatus.PLOTTING)

                # Get config overrides from request body
                config_overrides = request.json if request.json else {}

                # Execute the plot
                success = plotter_controller.plot_file(
                    svg_path,
                    config_overrides=config_overrides,
                    job_name=f"{project_manager.current_project['name']}_{layer_info['name']}"
                )

                with status_lock:
                    if success:
                        system_status['plotter_status'] = "IDLE"
                        system_status['plot_progress'] = 100
                        logger.info(f"Successfully plotted layer {layer_id}")
                    else:
                        system_status['plotter_status'] = "ERROR"
                        system_status['last_error'] = "Plot execution failed"
                        logger.error(f"Failed to plot layer {layer_id}")

                    system_status['current_layer'] = None

            except Exception as e:
                logger.error(f"Error executing plot for layer {layer_id}: {str(e)}")
                with status_lock:
                    system_status['plotter_status'] = "ERROR"
                    system_status['last_error'] = str(e)
                    system_status['current_layer'] = None

        # Start plot thread
        plot_thread = threading.Thread(target=execute_plot, daemon=True)
        plot_thread.start()

        return jsonify({
            "message": "Plot started",
            "layer_id": layer_id,
            "layer_name": layer_info['name']
        }), 202

    except Exception as e:
        logger.error(f"Error starting plot for layer {layer_id}: {str(e)}")
        return jsonify({"error": str(e)}), 500


@app.route('/plot/stop', methods=['POST'])
def stop_plot():
    """Stop current plotting operation"""
    try:
        success = plotter_controller.stop_plotting()

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
        success = plotter_controller.pause_plotting()

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
        success = plotter_controller.resume_plotting()

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


@app.route('/project', methods=['DELETE'])
def clear_project():
    """Clear current project from memory"""
    try:
        # Check if plotter is busy
        with status_lock:
            if system_status['plotter_status'] == "PLOTTING":
                return jsonify({"error": "Cannot clear project while plotting"}), 409

        success = project_manager.clear_project()

        if success:
            logger.info("Project cleared successfully")
            return jsonify({"message": "Project cleared"}), 200
        else:
            return jsonify({"message": "No project to clear"}), 404

    except Exception as e:
        logger.error(f"Error clearing project: {str(e)}")
        return jsonify({"error": str(e)}), 500


@app.route('/config', methods=['GET'])
def get_config():
    """Get current plotter configuration"""
    try:
        config = config_manager.get_all_config()
        return jsonify(config), 200
    except Exception as e:
        logger.error(f"Error getting config: {str(e)}")
        return jsonify({"error": str(e)}), 500


@app.route('/config', methods=['PUT'])
def update_config():
    """Update plotter configuration"""
    try:
        data = request.json
        if not data:
            return jsonify({"error": "No configuration data provided"}), 400

        config_manager.update_config(data)

        return jsonify({
            "message": "Configuration updated",
            "config": config_manager.get_all_config()
        }), 200

    except Exception as e:
        logger.error(f"Error updating config: {str(e)}")
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
    logger.info("Starting NextDraw Plotter API Server (Project-Based)")
    app.run(host='0.0.0.0', port=5000, debug=False)
