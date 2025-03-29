import asyncio
import re
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Set, Callable

import aiohttp
import asyncpraw

from config.config import Config
from core.downloader import Downloader
from core.duplicates import remove_duplicates
from models.submission import SubmissionData

# Create logger
logger = logging.getLogger("archiver")

class RedditArchiver:
    """Downloads and archives Reddit user submissions."""

    def __init__(self, config: Config, progress_callback: Optional[Callable] = None):
        """Initialize with configuration and optional progress callback."""
        self.config = config
        self._reddit = None
        self.downloader = Downloader(
            self.config.chunk_size,
            self.config.max_concurrent_downloads,
            progress_callback
        )
        self.processed_paths = set()
        self.progress_callback = progress_callback
        self.log_callback = None

    def set_log_callback(self, callback):
        """Set a log callback."""
        self.log_callback = callback

    def log(self, level, message):
        """Log a message using logger or callback if available."""
        if level == "info":
            logger.info(message)
        elif level == "error":
            logger.error(message)
        elif level == "debug":
            logger.debug(message)

        if self.log_callback:
            self.log_callback(message)

    async def get_reddit(self) -> asyncpraw.Reddit:
        """Get or create the Reddit client."""
        if not self._reddit:
            self._reddit = asyncpraw.Reddit(
                client_id=self.config.client_id,
                client_secret=self.config.client_secret,
                username=self.config.username,
                password=self.config.password,
                user_agent=self.config.user_agent
            )
        return self._reddit

    async def get_submissions(self, username: str, limit: int) -> List[SubmissionData]:
        """Fetch submissions for a given user."""
        submissions = []
        try:
            reddit = await self.get_reddit()
            user = await reddit.redditor(username)
            async for submission in user.submissions.new(limit=limit):
                submissions.append(SubmissionData.from_praw_submission(submission))
        except Exception as e:
            self.log("error", f"Failed to fetch submissions for u/{username}: {e}")
        return submissions

    async def archive_user(self, username: str, limit: Optional[int] = None) -> Path:
        """Archive a Reddit user's submissions."""
        download_path = Path("downloads") / username
        actual_limit = limit if limit is not None else self.config.download_limit

        try:
            # Get submissions
            submissions = await self.get_submissions(username, actual_limit)
            if not submissions:
                self.log("info", f"No submissions found for u/{username}")
                return download_path

            # Create download directory
            download_path.mkdir(parents=True, exist_ok=True)
            self.processed_paths.add(download_path)

            # Process submissions
            async with aiohttp.ClientSession() as session:
                tasks = [
                    self.process_submission(session, sub, download_path)
                    for sub in submissions
                ]
                await asyncio.gather(*tasks)

        except Exception as e:
            self.log("error", f"Failed to process user u/{username}: {e}")

        return download_path

    async def remove_duplicates_in_path(self, path: Path, progress_callback=None) -> int:
        """Remove duplicates in a specific path."""
        return await remove_duplicates(path, self.config.valid_formats, progress_callback)

    async def close(self) -> None:
        """Close the Reddit connection."""
        if self._reddit:
            await self._reddit.close()
            self._reddit = None

    @staticmethod
    def extract_file_extension(url: str) -> Optional[str]:
        """Extract file extension from a URL."""
        match = re.search(r"\.([a-zA-Z0-9]+)(?:\?|$)", url)
        return match.group(1).lower() if match else None

    async def process_submission(
        self, session: aiohttp.ClientSession, submission: SubmissionData, path: Path
    ) -> None:
        """Process a single submission."""
        try:
            if submission.has_gallery:
                await self.process_gallery(session, submission, path)
            else:
                if direct_url := await self.downloader.get_direct_url(
                    session, submission.url
                ):
                    submission.url = direct_url
                    await self.process_single(session, submission, path)
        except Exception as e:
            self.log("error", f"Failed to process submission {submission.id}: {e}")

    async def process_gallery(
        self, session: aiohttp.ClientSession, submission: SubmissionData, path: Path
    ) -> None:
        """Process a gallery submission."""
        if not submission.media_metadata:
            return

        tasks = []
        for idx, (_, image_data) in enumerate(submission.media_metadata.items(), 1):
            img_url = image_data["s"].get("u") or image_data["s"].get("gif")
            ext = self.extract_file_extension(img_url)
            if img_url and ext and ext in self.config.valid_formats:
                filename = f"{submission.date_str}-{submission.id}-{idx}.{ext}"
                tasks.append(
                    self.downloader.download_file(session, img_url, path, filename)
                )

        if tasks:
            await asyncio.gather(*tasks)

    async def process_single(
        self, session: aiohttp.ClientSession, submission: SubmissionData, path: Path
    ) -> None:
        """Process a single media submission."""
        ext = self.extract_file_extension(submission.url)
        if not ext or ext.lower() not in self.config.valid_formats:
            return

        filename = f"{submission.date_str}-{submission.id}.{ext}"
        await self.downloader.download_file(session, submission.url, path, filename)
