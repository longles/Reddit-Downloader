import asyncio
import re
from datetime import datetime
from functools import cached_property
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

    def __init__(
        self,
        env_path: str,
        concurrent_downloads: Optional[int] = None,
        download_limit: Optional[int] = None,
    ):
        self.config = Config.from_env(env_path, concurrent_downloads, download_limit)
        self._reddit: Optional[asyncpraw.Reddit] = None
        self.downloader = Downloader(self.config)

    @cached_property
    async def reddit(self) -> asyncpraw.Reddit:
        if not self._reddit:
            self._reddit = asyncpraw.Reddit(
                user_agent=self.config.user_agent,
                client_id=self.config.client_id,
                client_secret=self.config.client_secret,
                username=self.config.username,
                password=self.config.password,
            )
        return self._reddit

    @staticmethod
    def extract_file_extension(url: str) -> Optional[str]:
        match = re.search(r"\.([a-zA-Z0-9]+)(?:\?|$)", url)
        return match.group(1).lower() if match else None

    async def get_submissions(self, username: str, limit: int) -> List[SubmissionData]:
        submissions = []
        try:
            reddit = await self.reddit
            user = await reddit.redditor(username)
            async for submission in user.submissions.new(limit=limit):
                submissions.append(SubmissionData.from_praw_submission(submission))
        except Exception:
            pass
        return submissions

    async def archive_user(self, username: str) -> None:
        download_path = Path("downloads") / username
        download_path.mkdir(parents=True, exist_ok=True)

        try:
            submissions = await self.get_submissions(
                username, self.config.download_limit
            )
            if not submissions:
                return

            async with aiohttp.ClientSession() as session:
                tasks = [
                    self._process_submission(session, sub, download_path)
                    for sub in submissions
                ]
                for task in tqdm(
                    asyncio.as_completed(tasks),
                    total=len(submissions),
                    desc=f"Archiving u/{username}",
                    unit="post",
                ):
                    await task

            duplicates_removed = await remove_duplicates(
                download_path, self.config.valid_formats
            )
            await self._write_archive_info(
                download_path, submissions, duplicates_removed
            )

        finally:
            if self._reddit:
                await self._reddit.close()

    async def process_submission(
        self, session: aiohttp.ClientSession, submission: SubmissionData, path: Path
    ) -> None:
        try:
            if submission.has_gallery:
                await self._process_gallery(session, submission, path)
            else:
                direct_url = await self.downloader.get_direct_url(
                    session, submission.url
                )
                if direct_url:
                    submission.url = direct_url
                    await self._process_single(session, submission, path)
        except Exception:
            pass

    async def process_gallery(
        self, session: aiohttp.ClientSession, submission: SubmissionData, path: Path
    ) -> int:
        if not submission.media_metadata:
            return 0

        tasks = []
        for idx, (_, image_data) in enumerate(submission.media_metadata.items(), 1):
            img_url = image_data["s"].get("u") or image_data["s"].get("gif")
            ext = self.extract_file_extension(img_url)
            if img_url and ext:
                filename = f"{submission.date_str}-{submission.id}-{idx}.{ext}"
                tasks.append(
                    self.downloader.download_file(session, img_url, path, filename)
                )

        results = await asyncio.gather(*tasks, return_exceptions=True)
        return sum(1 for r in results if isinstance(r, bool) and r)

    async def process_single(
        self, session: aiohttp.ClientSession, submission: SubmissionData, path: Path
    ) -> bool:
        ext = self.extract_file_extension(submission.url)
        if not ext or ext.lower() not in {
            fmt.strip(".") for fmt in self.config.valid_formats
        }:
            return False

        filename = f"{submission.date_str}-{submission.id}.{ext}"
        return await self.downloader.download_file(
            session, submission.url, path, filename
        )

    async def write_archive_info(
        self, path: Path, submissions: List[SubmissionData], duplicates_removed: int
    ) -> None:
        async with aiofiles.open(path / "archive_info.txt", "w") as f:
            info = [
                f"Archive created: {datetime.now().isoformat()}",
                f"Total submissions processed: {len(submissions)}",
                f"Latest submission ID: {submissions[0].id if submissions else 'none'}",
                f"Duplicate files removed: {duplicates_removed}",
            ]
            await f.write("\n".join(info) + "\n")
