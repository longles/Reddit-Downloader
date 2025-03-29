import os
import io
import sys
import threading
import logging
from typing import List, Dict, Any, Optional
from pathlib import Path
from flask import Flask, request, jsonify, send_from_directory
from flask_socketio import SocketIO
from flask_cors import CORS
from datetime import datetime

from services.archiver_service import (
    ArchiverService,
    get_usernames,
    JobStatus,
    DownloadStatus,
)

# Configure root logger to suppress console output when running as webapp
root_logger = logging.getLogger()
# Remove any existing handlers
for handler in root_logger.handlers[:]:
    root_logger.removeHandler(handler)
# Set level to ERROR to suppress most messages
root_logger.setLevel(logging.ERROR)

# Create app
app = Flask(__name__)
app.config["SECRET_KEY"] = os.urandom(24).hex()
app.config["UPLOAD_FOLDER"] = "uploads"
socketio = SocketIO(app, cors_allowed_origins="*")
CORS(app)  # Enable CORS for all routes

# Create uploads directory if it doesn't exist
Path(app.config["UPLOAD_FOLDER"]).mkdir(exist_ok=True)

# Configure logger
logger = logging.getLogger("api_server")
# Create a file handler instead of console output
file_handler = logging.FileHandler("webapp.log")
file_handler.setFormatter(
    logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
)
logger.addHandler(file_handler)
logger.setLevel(logging.INFO)

# Get archiver service instance
archiver_service = ArchiverService()


# Register event callbacks
def on_download_progress(job_id: str, progress):
    """Callback for download progress updates"""
    # Log the download progress data for debugging
    logger.info(f"Download progress: {progress.download_id}, Status: {progress.status}, Bytes: {progress.current_bytes}/{progress.total_bytes}")

    socketio.emit(
        "download_progress",
        {
            "task_id": job_id,
            "download_id": progress.download_id,
            "filename": progress.filename or "Unknown file",
            "total_bytes": progress.total_bytes,
            "current_bytes": progress.current_bytes,
            "status": progress.status,
            "percentage": progress.percentage if hasattr(progress, 'percentage') else 0,
            "error": progress.error,
            "url": progress.url or "",
        },
    )
    # Log after emitting
    logger.debug(f"Emitted download_progress event for {progress.download_id}")


def on_job_update(job_id: str, job_data: Dict[str, Any]):
    """Callback for job status updates"""
    socketio.emit(
        "job_update",
        {
            "task_id": job_id,
            "status": job_data["status"],
            "processed_users": job_data.get("processed_users", 0),
            "total_users": job_data.get("total_users", 0),
            "error": job_data.get("error"),
        },
    )


def on_log_message(job_id: str, message: str):
    """Callback for log messages"""
    socketio.emit(
        "log_update",
        {"task_id": job_id, "log": message, "timestamp": datetime.now().isoformat()},
    )


def on_duplicate_removal_progress(job_id: str, progress):
    """Callback for duplicate removal progress updates"""
    socketio.emit(
        "duplicate_removal_progress",
        {
            "task_id": job_id,
            "username": progress.username,
            "files_scanned": progress.files_scanned,
            "files_processed": progress.files_processed,
            "duplicates_found": progress.duplicates_found,
            "duplicates_removed": progress.duplicates_removed,
            "status": progress.status,
            "percentage": progress.percentage,
            "error": progress.error,
        },
    )


# Register callbacks with the service
archiver_service.register_callback("download", on_download_progress)
archiver_service.register_callback("job", on_job_update)
archiver_service.register_callback("log", on_log_message)
archiver_service.register_callback("duplicate_removal", on_duplicate_removal_progress)


@app.route("/api/users/folders", methods=["GET"])
def get_folder_users():
    """Get usernames from existing folders"""
    users = get_usernames("folders")
    return jsonify(users)


@app.route("/api/users/file", methods=["POST"])
def upload_user_file():
    """Process uploaded username file"""
    if "userFile" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files["userFile"]
    if file.filename == "":
        return jsonify({"error": "No file selected"}), 400

    # Save file temporarily
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    filepath = Path(app.config["UPLOAD_FOLDER"]) / f"users_{timestamp}.txt"
    file.save(filepath)

    # Read usernames
    users = get_usernames("file", str(filepath))

    # Return the list of users and the file path for later reference
    return jsonify({"users": users, "filepath": str(filepath)})


@app.route("/api/archive/start", methods=["POST"])
def start_archive():
    """Start the archiving process"""
    data = request.json
    input_method = data.get("inputMethod")
    users = []

    # Get users based on input method
    if input_method == "username":
        username = data.get("username", "").strip()
        if username:
            users = [username]
    elif input_method == "file":
        filepath = data.get("filepath")
        if filepath:
            users = get_usernames("file", filepath)
    elif input_method == "folders":
        users = get_usernames("folders")

    if not users:
        return jsonify({"error": "No users selected"}), 400

    # Get options
    options = {
        "download_limit": int(data.get("limit", 100)),
        "max_concurrent_downloads": int(data.get("concurrent", 10)),
        "download_bars": False,
    }

    try:
        # Start the archiving job
        job_id = archiver_service.start_job(users, **options)

        return jsonify(
            {
                "task_id": job_id,
                "status": "started",
                "message": f"Started archiving {len(users)} users",
            }
        )
    except Exception as e:
        logger.exception("Error starting archive job")
        return jsonify({"error": str(e)}), 500


@app.route("/api/archive/status/<task_id>", methods=["GET"])
def get_status(task_id):
    """Get status of an archiving job"""
    job = archiver_service.get_job(task_id)
    if not job:
        return jsonify({"error": "Task not found"}), 404

    return jsonify(job)


@app.route("/api/archive/stop/<task_id>", methods=["POST"])
def stop_archive(task_id):
    """Stop an archiving task"""
    success = archiver_service.stop_job(task_id)

    if success:
        return jsonify({"status": "stopping", "message": "Stopping archive task..."})
    else:
        return jsonify({"error": "Could not stop task"}), 400


@app.route("/api/downloads/<task_id>", methods=["GET"])
def get_downloads(task_id):
    """Get current downloads for a task"""
    downloads = archiver_service.get_job_downloads(task_id)
    return jsonify([d.to_dict() for d in downloads])


@app.route("/api/jobs", methods=["GET"])
def get_all_jobs():
    """Get all jobs"""
    jobs = archiver_service.get_all_jobs()
    return jsonify(jobs)


@app.route("/uploads/<path:filename>")
def download_file(filename):
    """Serve uploaded files"""
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)


@app.route("/api/logs/<task_id>", methods=["GET"])
def get_logs(task_id):
    """Get logs for a specific job (stub - implement actual log retrieval)"""
    # This is a simplified version - you may need to implement log storage and retrieval
    return jsonify(
        {
            "logs": [
                {
                    "timestamp": "2025-03-29T12:00:00",
                    "message": f"Sample log for job {task_id}",
                    "level": "INFO",
                }
            ]
        }
    )


@socketio.on("connect")
def handle_connect():
    logger.info(f"Client connected: {request.sid}")


@socketio.on("disconnect")
def handle_disconnect():
    logger.info(f"Client disconnected: {request.sid}")


if __name__ == "__main__":
    # Run the Flask app with SocketIO
    port = int(os.environ.get("PORT", 5000))
    debug = bool(os.environ.get("ARCHIVER_DEBUG", False))
    socketio.run(app, host="0.0.0.0", port=port, debug=debug)
