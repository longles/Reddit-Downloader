import asyncio
import re
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import aiofiles
import aiohttp
import asyncpraw
from tqdm import tqdm

from config.config import Config
from core.downloader import Downloader
from core.duplicates import remove_duplicates
from models.submission import SubmissionData


class RedditArchiver:
    """Downloads and archives Reddit user submissions."""

    def __init__(self, config: Config):
        self.config = config
        self._reddit: Optional[asyncpraw.Reddit] = None
        self.downloader = Downloader(self.config)

    async def get_reddit(self) -> asyncpraw.Reddit:
        """Get or create the Reddit client."""
        if not self._reddit:
            self._reddit = asyncpraw.Reddit(
                user_agent=self.config.user_agent,
                client_id=self.config.client_id,
                client_secret=self.config.client_secret,
                username=self.config.username,
                password=self.config.password,
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
            print(f"Error fetching submissions for {username}: {e}")
        return submissions

    async def archive_user(self, username: str) -> None:
        """Archive a Reddit user's submissions."""
        try:
            if not (
                submissions := await self.get_submissions(
                    username, self.config.download_limit
                )
            ):
                print(f"No submissions found for {username}")
                return

            download_path = Path("downloads") / username
            download_path.mkdir(parents=True, exist_ok=True)

            await self._process_submissions(username, submissions, download_path)
            await remove_duplicates(download_path, self.config.valid_formats)
        except Exception as e:
            print(f"Error processing user {username}: {e}")

    async def _process_submissions(
        self, username: str, submissions: List[SubmissionData], download_path: Path
    ) -> None:
        """Process all submissions for a user."""
        async with aiohttp.ClientSession() as session:
            tasks = [
                self.process_submission(session, sub, download_path)
                for sub in submissions
            ]
            for task in tqdm(
                asyncio.as_completed(tasks),
                total=len(submissions),
                desc=f"Archiving u/{username}",
                unit="post",
            ):
                await task

    async def close(self) -> None:
        """Close the Reddit connection when all processing is complete."""
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
        except Exception:
            pass

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
            if img_url and ext:
                filename = f"{submission.date_str}-{submission.id}-{idx}.{ext}"
                tasks.append(
                    self.downloader.download_file(session, img_url, path, filename)
                )
        await asyncio.gather(*tasks)

    async def process_single(
        self, session: aiohttp.ClientSession, submission: SubmissionData, path: Path
    ) -> None:
        """Process a single media submission."""
        ext = self.extract_file_extension(submission.url).lower()
        if ext not in self.config.valid_formats:
            return

        filename = f"{submission.date_str}-{submission.id}.{ext}"
        await self.downloader.download_file(session, submission.url, path, filename)
