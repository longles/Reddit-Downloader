import asyncio
import threading
import uuid
from typing import Dict, List, Optional, Callable, Any, Set, Tuple
from datetime import datetime
from pathlib import Path
import logging
from dataclasses import dataclass, field

from config.config import Config
from core.archiver import RedditArchiver
from utils.user_utils import get_usernames_from_file, get_usernames_from_folders

# Configure logging
logging.basicConfig(
    level=logging.ERROR,  # Change to ERROR to suppress most console messages
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        # Default to no console output - UIs will add their own handlers
        logging.NullHandler()
    ],
)
logger = logging.getLogger("archiver_service")


class JobStatus:
    """Status constants for archiving jobs"""

    PENDING = "pending"
    RUNNING = "running"
    STOPPING = "stopping"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"


class DownloadStatus:
    """Status constants for download items"""

    PENDING = "pending"
    STARTED = "started"
    PROGRESS = "progress"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class DownloadProgress:
    """Represents a single download item with progress tracking"""

    job_id: str
    download_id: str
    total_bytes: int = 0
    current_bytes: int = 0
    status: str = DownloadStatus.PENDING
    error: Optional[str] = None
    start_time: datetime = field(default_factory=datetime.now)
    end_time: Optional[datetime] = None
    percentage: int = 0
    filename: str = ""
    url: str = ""

    def update(
        self, current_bytes: int, status: str, error: Optional[str] = None
    ) -> "DownloadProgress":
        """Update download progress"""
        self.current_bytes = current_bytes
        self.status = status

        if status in (DownloadStatus.COMPLETED, DownloadStatus.FAILED):
            self.end_time = datetime.now()

        if error:
            self.error = error

        if self.total_bytes > 0:
            self.percentage = min(100, int(current_bytes * 100 / self.total_bytes))
        else:
            self.percentage = 0 if status != DownloadStatus.COMPLETED else 100

        return self

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            "job_id": self.job_id,
            "download_id": self.download_id,
            "total_bytes": self.total_bytes,
            "current_bytes": self.current_bytes,
            "status": self.status,
            "error": self.error,
            "percentage": self.percentage,
            "filename": self.filename,
            "url": self.url,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
        }


class DuplicateRemovalStatus:
    """Status constants for duplicate removal process"""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class DuplicateRemovalProgress:
    """Represents duplicate removal progress"""

    job_id: str
    username: str
    status: str = DuplicateRemovalStatus.PENDING
    files_scanned: int = 0
    files_processed: int = 0
    duplicates_found: int = 0
    duplicates_removed: int = 0
    percentage: int = 0
    error: Optional[str] = None
    start_time: datetime = field(default_factory=datetime.now)
    end_time: Optional[datetime] = None

    def update(
        self,
        files_scanned: int,
        files_processed: int,
        duplicates_found: int,
        duplicates_removed: int,
        status: str,
        error: Optional[str] = None,
    ) -> "DuplicateRemovalProgress":
        """Update duplicate removal progress"""
        self.files_scanned = files_scanned
        self.files_processed = files_processed
        self.duplicates_found = duplicates_found
        self.duplicates_removed = duplicates_removed
        self.status = status

        if status in (DuplicateRemovalStatus.COMPLETED, DuplicateRemovalStatus.FAILED):
            self.end_time = datetime.now()

        if error:
            self.error = error

        if self.files_scanned > 0:
            self.percentage = min(
                100, int(self.files_processed * 100 / self.files_scanned)
            )

        return self

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            "job_id": self.job_id,
            "username": self.username,
            "status": self.status,
            "files_scanned": self.files_scanned,
            "files_processed": self.files_processed,
            "duplicates_found": self.duplicates_found,
            "duplicates_removed": self.duplicates_removed,
            "percentage": self.percentage,
            "error": self.error,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
        }


class ArchiverService:
    """Unified service for managing Reddit archiving jobs"""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ArchiverService, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        # Job management
        self.jobs: Dict[str, Dict[str, Any]] = {}
        self.active_archivers: Dict[str, Dict[str, Any]] = {}

        # Callback management
        self.progress_callbacks: Dict[str, List[Callable]] = {
            "download": [],
            "job": [],
            "log": [],
            "duplicate_removal": [],  # Add new callback type
        }

        # Download tracking
        self.downloads: Dict[str, DownloadProgress] = {}

        # Duplicate removal tracking
        self.duplicate_removals: Dict[str, DuplicateRemovalProgress] = {}

        self._initialized = True
        logger.info("ArchiverService initialized")

    def register_callback(self, callback_type: str, callback: Callable) -> None:
        """Register a callback for various events"""
        if callback_type not in self.progress_callbacks:
            raise ValueError(f"Unknown callback type: {callback_type}")

        if callback not in self.progress_callbacks[callback_type]:
            self.progress_callbacks[callback_type].append(callback)

    def unregister_callback(self, callback_type: str, callback: Callable) -> None:
        """Unregister a callback"""
        if (
            callback_type in self.progress_callbacks
            and callback in self.progress_callbacks[callback_type]
        ):
            self.progress_callbacks[callback_type].remove(callback)

    def broadcast_event(self, event_type: str, *args, **kwargs) -> None:
        """Broadcast an event to registered callbacks"""
        for callback in self.progress_callbacks.get(event_type, []):
            try:
                callback(*args, **kwargs)
            except Exception as e:
                logger.error(f"Error in {event_type} callback: {str(e)}")

    def log(self, job_id: str, message: str) -> None:
        """Log a message and broadcast it to callbacks"""
        logger.info(f"[Job {job_id}] {message}")
        self.broadcast_event("log", job_id, message)

    def update_download_progress(
        self,
        job_id: str,
        download_id: str,
        current: int,
        total: int,
        status: str,
        filename: str = "",
        url: str = "",
        error: Optional[str] = None,
    ) -> None:
        """Update download progress and broadcast update"""
        # Create download progress object if it doesn't exist
        if download_id not in self.downloads:
            self.downloads[download_id] = DownloadProgress(
                job_id=job_id,
                download_id=download_id,
                total_bytes=total,
                filename=filename,
                url=url,
            )

        # Update progress
        progress = self.downloads[download_id].update(current, status, error)

        # Broadcast update
        self.broadcast_event("download", job_id, progress)

        # Clean up completed/failed downloads after a while
        if status in (DownloadStatus.COMPLETED, DownloadStatus.FAILED):

            def cleanup_download():
                if download_id in self.downloads:
                    del self.downloads[download_id]

            # Schedule cleanup after 30 seconds
            threading.Timer(30, cleanup_download).start()

    def update_duplicate_removal_progress(
        self,
        job_id: str,
        username: str,
        files_scanned: int,
        files_processed: int,
        duplicates_found: int,
        duplicates_removed: int,
        status: str,
        error: Optional[str] = None,
    ) -> None:
        """Update duplicate removal progress and broadcast update"""
        # Create progress object if it doesn't exist
        progress_id = f"{job_id}_{username}"
        if progress_id not in self.duplicate_removals:
            self.duplicate_removals[progress_id] = DuplicateRemovalProgress(
                job_id=job_id, username=username
            )

        # Update progress
        progress = self.duplicate_removals[progress_id]

        # Set values
        progress.files_scanned = files_scanned
        progress.files_processed = files_processed
        progress.duplicates_found = duplicates_found
        progress.duplicates_removed = duplicates_removed
        progress.status = status

        # Force percentage to 100 if completed
        if status == DuplicateRemovalStatus.COMPLETED:
            progress.percentage = 100
            progress.end_time = datetime.now()
        elif files_scanned > 0:
            progress.percentage = min(99, int(files_processed * 100 / files_scanned))

        if error:
            progress.error = error

        # Broadcast update
        self.broadcast_event("duplicate_removal", job_id, progress)

        # Clean up completed/failed operations after a while
        if status in (DuplicateRemovalStatus.COMPLETED, DuplicateRemovalStatus.FAILED):
            def cleanup_progress():
                if progress_id in self.duplicate_removals:
                    del self.duplicate_removals[progress_id]

            # Schedule cleanup after 30 seconds
            threading.Timer(30, cleanup_progress).start()

    def _download_progress_wrapper(
        self,
        download_id: str,
        current: int,
        total: int,
        status: str,
        error: Optional[str] = None,
        filename: str = "",
        url: str = "",
    ) -> None:
        """Wrapper for download progress callback from downloader"""
        # Find job ID this download belongs to
        for job_id, job in self.active_archivers.items():
            if job.get("running", False):
                # Extract filename from download_id if not provided
                if not filename:
                    parts = download_id.split("/")
                    filename = parts[-1] if parts else download_id

                # Create a complete progress object to pass to the callback
                progress = type('DownloadProgress', (), {})()
                progress.download_id = download_id
                progress.current_bytes = current
                progress.total_bytes = total
                progress.status = status
                progress.error = error
                progress.filename = filename
                progress.url = url

                # Calculate percentage for convenience
                if total > 0:
                    progress.percentage = min(100, int((current * 100) / total))
                else:
                    progress.percentage = 0 if status != DownloadStatus.COMPLETED else 100

                # Send to registered callbacks
                self.broadcast_event("download", job_id, progress)
                return

    def start_job(self, usernames: List[str], **config_options) -> str:
        """Start a new archiving job and return the job ID"""
        if not usernames:
            raise ValueError("No usernames provided")

        # Generate a unique job ID
        job_id = str(uuid.uuid4())

        # Create config
        config = Config.from_env("./reddit.env", **config_options)

        # Create job record - extract JSON-serializable values
        self.jobs[job_id] = {
            "id": job_id,
            "usernames": usernames,
            "config_params": {
                "download_limit": config.download_limit,
                "max_concurrent_downloads": config.max_concurrent_downloads,
                "download_bars": config.download_bars,
                "chunk_size": config.chunk_size,
            },
            "status": JobStatus.PENDING,
            "start_time": datetime.now().isoformat(),
            "end_time": None,
            "processed_users": 0,
            "total_users": len(usernames),
            "error": None,
        }

        # Start job in a background thread
        thread = threading.Thread(
            target=self._run_job_thread, args=(job_id, usernames, config), daemon=True
        )
        thread.start()

        logger.info(f"Started job {job_id} for {len(usernames)} users")
        return job_id

    def stop_job(self, job_id: str) -> bool:
        """Stop a running job"""
        if job_id not in self.jobs:
            return False

        if self.jobs[job_id]["status"] != JobStatus.RUNNING:
            return False

        self.jobs[job_id]["status"] = JobStatus.STOPPING

        if job_id in self.active_archivers:
            self.active_archivers[job_id]["running"] = False
            if self.active_archivers[job_id].get("cancellation_event"):
                self.active_archivers[job_id]["cancellation_event"].set()

        self.log(job_id, "Stopping archive job")
        return True

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get a job by ID"""
        return self.jobs.get(job_id)

    def get_all_jobs(self) -> List[Dict[str, Any]]:
        """Get all jobs"""
        return list(self.jobs.values())

    def get_job_downloads(self, job_id: str) -> List[DownloadProgress]:
        """Get all downloads for a specific job"""
        return [d for d in self.downloads.values() if d.job_id == job_id]

    def _run_job_thread(self, job_id: str, usernames: List[str], config: Config):
        """Run a job in a separate thread"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            self.jobs[job_id]["status"] = JobStatus.RUNNING
            self.log(job_id, f"Starting archive process for {len(usernames)} users")

            # Create archiver with our progress callback
            archiver = RedditArchiver(config, self._download_progress_wrapper)

            # Connect log callback to archiver
            def log_callback(message):
                self.log(job_id, message)

            archiver.set_log_callback(log_callback)

            # Create cancellation event
            cancellation_event = asyncio.Event()

            # Store in active archivers
            self.active_archivers[job_id] = {
                "archiver": archiver,
                "running": True,
                "cancellation_event": cancellation_event,
            }

            # Process users
            loop.run_until_complete(
                self._process_users(job_id, archiver, usernames, cancellation_event)
            )

            # Update status
            if self.jobs[job_id]["status"] == JobStatus.STOPPING:
                self.jobs[job_id]["status"] = JobStatus.CANCELED
                self.log(job_id, "Archive job canceled")
            else:
                self.jobs[job_id]["status"] = JobStatus.COMPLETED
                self.log(job_id, "Archive process complete")

        except Exception as e:
            logger.exception(f"Error in job thread for {job_id}: {str(e)}")
            self.jobs[job_id]["status"] = JobStatus.FAILED
            self.jobs[job_id]["error"] = str(e)
            self.log(job_id, f"Error during archiving: {str(e)}")
        finally:
            # Cleanup
            if job_id in self.active_archivers:
                archiver = self.active_archivers[job_id].get("archiver")
                if archiver:
                    loop.run_until_complete(archiver.close())
                del self.active_archivers[job_id]

            # Update job end time
            self.jobs[job_id]["end_time"] = datetime.now().isoformat()

            # Broadcast job status update
            self.broadcast_event("job", job_id, self.jobs[job_id])

    async def _process_users(
        self,
        job_id: str,
        archiver: RedditArchiver,
        usernames: List[str],
        cancellation_event: asyncio.Event,
    ) -> None:
        """Process multiple usernames and remove duplicates at the end."""
        processed_paths = set()
        try:
            for i, username in enumerate(usernames):
                # Check if we should stop
                if cancellation_event.is_set() or not self.active_archivers.get(
                    job_id, {}
                ).get("running", False):
                    self.log(job_id, f"Stopping after processing {i} users")
                    return

                self.log(
                    job_id, f"Processing user {i+1}/{len(usernames)}: u/{username}"
                )
                await archiver.archive_user(username)

                # Update job progress
                self.jobs[job_id]["processed_users"] = i + 1
                self.broadcast_event("job", job_id, self.jobs[job_id])

                # Add to processed paths for duplicate removal
                user_path = Path("downloads") / username
                if user_path.exists() and user_path.is_dir():
                    processed_paths.add(user_path)

            # Only remove duplicates if we haven't been canceled
            if not cancellation_event.is_set() and self.active_archivers.get(
                job_id, {}
            ).get("running", False):
                self.log(job_id, "Removing duplicates across all downloaded content...")
                removed_count = 0
                for path in processed_paths:
                    username = path.name

                    # Create a progress callback for this user's duplicate removal
                    def make_progress_callback(job_id, username):
                        def callback(
                            files_scanned,
                            files_processed,
                            duplicates_found,
                            duplicates_removed,
                            status,
                            error=None,
                        ):
                            self.update_duplicate_removal_progress(
                                job_id,
                                username,
                                files_scanned,
                                files_processed,
                                duplicates_found,
                                duplicates_removed,
                                status,
                                error,
                            )

                        return callback

                    progress_callback = make_progress_callback(job_id, username)
                    count = await archiver.remove_duplicates_in_path(
                        path, progress_callback
                    )
                    removed_count += count

                self.log(job_id, f"Removed {removed_count} duplicate files")
        except Exception as e:
            self.log(job_id, f"Error during processing: {str(e)}")
            raise


# Functions to get usernames from different sources
def get_usernames(source: str, value: str = "") -> List[str]:
    """Get usernames from different sources"""
    if source == "username":
        return [value] if value else []
    elif source == "file":
        return get_usernames_from_file(value) if value else []
    elif source == "folders":
        return get_usernames_from_folders()
    return []
