"""
NextDraw Plotter API Server
A Flask application for controlling NextDraw plotters via REST API.
"""

import os
import json
import threading
import time
import tempfile
import hashlib
from datetime import datetime
from flask import Flask, request, jsonify, stream_template
from flask_cors import CORS
import logging
from logging.handlers import RotatingFileHandler
from werkzeug.utils import secure_filename

from plotter_controller import PlotterController
from config_manager import ConfigManager
from remote_update import RemoteUpdateManager

# Initialize Flask app
app = Flask(__name__)
CORS(app)

# Configure Flask for large file uploads
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500MB limit
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 31536000  # 1 year cache

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
update_manager = RemoteUpdateManager()

# Global status tracking
app_status = {
    "status": "IDLE",
    "job_info": None,
    "error_message": None,
    "last_updated": datetime.now().isoformat(),
    "uptime_start": datetime.now().isoformat()
}

def update_status(status, job_info=None, error=None):
    """Update global application status"""
    global app_status
    app_status.update({
        "status": status,
        "error_message": error,
        "last_updated": datetime.now().isoformat()
    })

    # If job info is provided, update it
    if job_info:
        app_status["job_info"] = job_info
    elif status == "IDLE":
        # Clear job info when going to IDLE state
        app_status["job_info"] = None

    logger.info(f"Status updated: {status}")

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": "1.0.1"
    })

@app.route('/status', methods=['GET'])
def get_status():
    """Get current plotter status"""
    try:
        plotter_status = plotter_controller.get_status()

        return jsonify({
            "plotter": plotter_status,
            "app": app_status,
            "config": config_manager.get_current_config()
        })
    except Exception as e:
        logger.error(f"Error getting status: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/plot', methods=['POST'])
def submit_plot():
    """Submit a new plot job"""
    try:
        # Handle both JSON and multipart/form-data
        if request.content_type and request.content_type.startswith('multipart/form-data'):
            return submit_plot_multipart()
        else:
            return submit_plot_json()

    except Exception as e:
        logger.error(f"Error submitting plot: {str(e)}")
        return jsonify({"error": str(e)}), 500

def submit_plot_json():
    """Handle JSON plot submission"""
    data = request.get_json()

    logger.info("DIRECT EXECUTE JOB")

    if not data:
        return jsonify({"error": "No data provided"}), 400

    # Check if plotter is busy
    if not plotter_controller.is_idle():
        return jsonify({"error": "Plotter is busy. Cannot start new job."}), 409

    # Check SVG content size for JSON submissions
    svg_content = data.get('svg_content', '')
    if svg_content and len(svg_content) > 100 * 1024 * 1024:  # 100MB
        return jsonify({
            "error": "SVG content too large for JSON submission. Use multipart upload instead.",
            "suggestion": "Use /plot/upload endpoint for files > 100MB"
        }), 413

    # Validate required fields
    if 'svg_content' not in data and 'svg_file' not in data:
        return jsonify({"error": "Either svg_content or svg_file must be provided"}), 400

    # Validate start_mm parameter if provided
    start_mm = data.get('start_mm')
    if start_mm is not None:
        try:
            start_mm = float(start_mm)
        except (ValueError, TypeError):
            return jsonify({"error": "start_mm must be a valid number"}), 400

    # Create job with optional configuration overrides
    job_data = {
        "svg_content": data.get('svg_content'),
        "svg_file": data.get('svg_file'),
        "config_overrides": data.get('config', {}),
        "name": data.get('name', f"Job_{int(time.time())}"),
        "description": data.get('description', ''),
        "start_mm": start_mm,
        "submitted_at": datetime.now().isoformat()
    }

    # Update application status with job info
    update_status("PLOTTING", job_data)
    
    # Execute job in a new thread
    def execute_in_thread():
        try:
            result = plotter_controller.execute_job(job_data)
            if result.get('success', False):
                update_status("IDLE", None)
            else:
                update_status("ERROR", None, result.get('error', 'Unknown error'))
        except Exception as e:
            update_status("ERROR", None, str(e))

    threading.Thread(target=execute_in_thread, daemon=True).start()

    return jsonify({
        "svg_file": data.get('svg_file'),
        "status": "started",
    }), 201

def submit_plot_multipart():
    """Handle multipart file upload"""
    # Check if plotter is busy
    if not plotter_controller.is_idle():
        return jsonify({"error": "Plotter is busy. Cannot start new job."}), 409

    # Create uploads directory if it doesn't exist
    upload_dir = app.config['UPLOAD_FOLDER']
    if not os.path.exists(upload_dir):
        os.makedirs(upload_dir)

    # Check if file is in request
    if 'svg_file' not in request.files:
        return jsonify({"error": "No file provided in multipart request"}), 400

    file = request.files['svg_file']
    if file.filename == '':
        return jsonify({"error": "No file selected"}), 400

    # Validate file extension
    if not file.filename.lower().endswith('.svg'):
        return jsonify({"error": "Only SVG files are allowed"}), 400

    # Generate secure filename with timestamp
    timestamp = int(time.time())
    secure_name = secure_filename(file.filename)
    filename = f"{timestamp}_{secure_name}"
    filepath = os.path.join(upload_dir, filename)

    # Save file with progress tracking for large files
    try:
        file.save(filepath)

        # Verify file size
        file_size = os.path.getsize(filepath)
        logger.info(f"Uploaded file {filename}, size: {file_size} bytes")

        # Get job metadata from form data
        start_mm = request.form.get('start_mm')
        if start_mm is not None and start_mm.strip():
            try:
                start_mm = float(start_mm)
            except ValueError:
                return jsonify({"error": "start_mm must be a valid number"}), 400
        else:
            start_mm = None

        job_data = {
            "svg_file": filepath,
            "config_overrides": json.loads(request.form.get('config', '{}')),
            "name": request.form.get('name', f"Upload_{timestamp}"),
            "description": request.form.get('description', ''),
            "start_mm": start_mm,
            "submitted_at": datetime.now().isoformat(),
            "file_size": file_size,
            "original_filename": file.filename
        }

        # Update application status with job info
        update_status("PLOTTING", job_data)

        # Execute job in a new thread
        def execute_in_thread():
            try:
                result = plotter_controller.execute_job(job_data)
                if result.get('success', False):
                    update_status("IDLE", None)
                else:
                    update_status("ERROR", None, result.get('error', 'Unknown error'))
            except Exception as e:
                update_status("ERROR", None, str(e))
                # Clean up file if execution failed
                if os.path.exists(filepath):
                    os.remove(filepath)

        threading.Thread(target=execute_in_thread, daemon=True).start()

        return jsonify({
            "status": "started",
            "file_size": file_size,
            "uploaded_filename": filename
        }), 201

    except Exception as e:
        # Clean up file if job creation failed
        if os.path.exists(filepath):
            os.remove(filepath)
        raise e

@app.route('/plot/upload', methods=['POST'])
def upload_plot():
    """Dedicated endpoint for large file uploads"""
    return submit_plot_multipart()

@app.route('/plot/chunk', methods=['POST'])
def upload_plot_chunk():
    """Handle chunked uploads for very large files"""
    try:
        # Get chunk metadata
        chunk_number = int(request.form.get('chunk', 0))
        total_chunks = int(request.form.get('total_chunks', 1))
        file_id = request.form.get('file_id', '')
        original_filename = request.form.get('filename', 'upload.svg')

        if not file_id:
            return jsonify({"error": "file_id required"}), 400

        # Create temp directory for chunks
        temp_dir = os.path.join(tempfile.gettempdir(), 'nextdraw_chunks', file_id)
        if not os.path.exists(temp_dir):
            os.makedirs(temp_dir)

        # Save chunk
        if 'chunk_data' not in request.files:
            return jsonify({"error": "No chunk data provided"}), 400

        chunk_file = request.files['chunk_data']
        chunk_path = os.path.join(temp_dir, f"chunk_{chunk_number}")
        chunk_file.save(chunk_path)

        # Check if all chunks are uploaded
        uploaded_chunks = len([f for f in os.listdir(temp_dir) if f.startswith('chunk_')])

        if uploaded_chunks == total_chunks:
            # Reassemble file
            upload_dir = app.config['UPLOAD_FOLDER']
            if not os.path.exists(upload_dir):
                os.makedirs(upload_dir)

            timestamp = int(time.time())
            secure_name = secure_filename(original_filename)
            final_filename = f"{timestamp}_{secure_name}"
            final_path = os.path.join(upload_dir, final_filename)

            # Combine chunks
            with open(final_path, 'wb') as final_file:
                for i in range(total_chunks):
                    chunk_path = os.path.join(temp_dir, f"chunk_{i}")
                    with open(chunk_path, 'rb') as chunk:
                        final_file.write(chunk.read())

            # Clean up chunks
            import shutil
            shutil.rmtree(temp_dir)

            # Verify final file
            file_size = os.path.getsize(final_path)

            # Create job
            job_data = {
                "svg_file": final_path,
                "config_overrides": json.loads(request.form.get('config', '{}')),
                "priority": int(request.form.get('priority', 1)),
                "name": request.form.get('name', f"ChunkedUpload_{timestamp}"),
                "description": request.form.get('description', ''),
                "submitted_at": datetime.now().isoformat(),
                "file_size": file_size,
                "original_filename": original_filename
            }

            job_id = job_queue.add_job(job_data)

            if plotter_controller.is_idle():
                threading.Thread(target=process_jobs, daemon=True).start()

            return jsonify({
                "job_id": job_id,
                "status": "queued",
                "position": job_queue.get_position(job_id),
                "file_size": file_size,
                "message": "File assembled and job created"
            }), 201
        else:
            return jsonify({
                "status": "chunk_received",
                "chunk": chunk_number,
                "total_chunks": total_chunks,
                "uploaded_chunks": uploaded_chunks
            }), 200

    except Exception as e:
        logger.error(f"Error handling chunk upload: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/jobs', methods=['GET'])
def get_jobs():
    """Get current job status"""
    try:
        # Return only current job info
        return jsonify({
            "current_job": app_status
        })
    except Exception as e:
        logger.error(f"Error getting jobs: {str(e)}")
        return jsonify({"error": str(e)}), 500

# Removed job details endpoint as there is no longer a job queue

# Removed job cancel endpoint as there is no longer a job queue

@app.route('/pause', methods=['POST'])
def pause_plotting():
    """Pause current plotting job"""
    try:
        if plotter_controller.pause():
            update_status("PAUSED", app_status.get("job_info"))
            return jsonify({"message": "Plotting paused"})
        else:
            return jsonify({"error": "No active job to pause"}), 400
    except Exception as e:
        logger.error(f"Error pausing: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/resume', methods=['POST'])
def resume_plotting():
    """Resume paused plotting job"""
    try:
        if plotter_controller.resume():
            update_status("PLOTTING", app_status.get("job_info"))
            return jsonify({"message": "Plotting resumed"})
        else:
            return jsonify({"error": "No paused job to resume"}), 400
    except Exception as e:
        logger.error(f"Error resuming: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/stop', methods=['POST'])
def stop_plotting():
    """Stop current plotting job"""
    print("Stopping plotting job")
    try:
        if plotter_controller.stop():
            update_status("IDLE", None)
            return jsonify({"message": "Plotting stopped"})
        else:
            print("No active job to stop")
            return jsonify({"error": "No active job to stop"}), 400
    except Exception as e:
        logger.error(f"Error stopping: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/config', methods=['GET'])
def get_config():
    """Get current configuration"""
    try:
        return jsonify(config_manager.get_current_config())
    except Exception as e:
        logger.error(f"Error getting config: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/config', methods=['PUT'])
def update_config():
    """Update configuration"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No configuration data provided"}), 400

        config_manager.update_config(data)
        return jsonify({"message": "Configuration updated"})
    except Exception as e:
        logger.error(f"Error updating config: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/config/reset', methods=['POST'])
def reset_config():
    """Reset configuration to defaults"""
    try:
        config_manager.reset_to_defaults()
        return jsonify({"message": "Configuration reset to defaults"})
    except Exception as e:
        logger.error(f"Error resetting config: {str(e)}")
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

@app.route('/update', methods=['POST'])
def trigger_update():
    """Trigger remote update"""
    try:
        data = request.get_json() or {}
        branch = data.get('branch', 'main')
        force = data.get('force', False)

        if not plotter_controller.is_idle():
            return jsonify({"error": "Cannot update while plotting"}), 400

        result = update_manager.update(branch, force)
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error during update: {str(e)}")
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

# Process jobs function removed - direct execution implemented in submit functions

@app.errorhandler(404)
def not_found(error):
    return jsonify({"error": "Endpoint not found"}), 404

@app.errorhandler(413)
def request_entity_too_large(error):
    return jsonify({
        "error": "File too large",
        "max_size": "500MB",
        "suggestion": "Use chunked upload endpoint /plot/chunk for very large files"
    }), 413

@app.errorhandler(500)
def internal_error(error):
    return jsonify({"error": "Internal server error"}), 500

if __name__ == '__main__':
    logger.info("Starting NextDraw Plotter API Server")

    # Initialize plotter connection
    try:
        plotter_controller.initialize()
        update_status("IDLE")
    except Exception as e:
        logger.error(f"Failed to initialize plotter: {str(e)}")
        update_status("ERROR", None, f"Plotter initialization failed: {str(e)}")

    # Start the Flask app
    app.run(
        host='0.0.0.0',
        port=5000,
        debug=False,
        threaded=True
    )
