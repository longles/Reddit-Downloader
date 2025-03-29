import asyncio
import re
import logging
from pathlib import Path
from typing import Optional, Set, Callable

import aiofiles
import aiohttp

# Add logger setup
logger = logging.getLogger("downloader")

class DownloadStatus:
    """Download status constants"""
    STARTED = "started"
    PROGRESS = "progress"
    COMPLETED = "completed"
    FAILED = "failed"

class Downloader:
    """Downloads files with progress tracking and concurrency limits"""

    def __init__(self, chunk_size: int = 32768, max_concurrent: int = 10, progress_callback: Optional[Callable] = None):
        """
        Initialize downloader

        Args:
            chunk_size: Size of chunks to read/write
            max_concurrent: Maximum number of concurrent downloads
            progress_callback: Optional callback function for progress updates
                Signature: callback(download_id, current, total, status, error=None)
        """
        self.chunk_size = chunk_size
        self._download_semaphore = asyncio.Semaphore(max_concurrent)
        self._seen_urls: Set[str] = set()
        self.progress_callback = progress_callback

    async def download_file(
        self, session: aiohttp.ClientSession, url: str, path: Path, filename: str
    ) -> Path:
        """
        Download a file with progress tracking
        """
        if url in self._seen_urls:
            return None

        download_id = f"{path.name}/{filename}"
        temp_filepath = None
        result_path = None

        try:
            filepath = path / filename
            temp_filepath = filepath.with_suffix(".tmp")

            # Log the start of download
            logger.info(f"Starting download of {url} to {filepath}")

            # Initial notification
            self._report_progress(download_id, 0, 0, DownloadStatus.STARTED, filename=filename, url=url)

            async with self._download_semaphore, session.get(url, headers={'User-Agent': 'Mozilla/5.0'}) as response:
                response.raise_for_status()

                total_bytes = int(response.headers.get("content-length", 0))

                logger.info(f"Download size for {filename}: {total_bytes} bytes")

                # Report initial progress with correct size
                self._report_progress(download_id, 0, total_bytes, DownloadStatus.STARTED, filename=filename, url=url)

                downloaded_bytes = 0
                async with aiofiles.open(temp_filepath, "wb") as f:
                    async for chunk in response.content.iter_chunked(self.chunk_size):
                        await f.write(chunk)
                        downloaded_bytes += len(chunk)
                        self._report_progress(
                            download_id, downloaded_bytes, total_bytes, DownloadStatus.PROGRESS,
                            filename=filename, url=url
                        )

                # Log completion
                logger.info(f"Download complete: {filename}, size: {downloaded_bytes} bytes")

            # Finalize download
            await asyncio.to_thread(temp_filepath.replace, filepath)
            self._seen_urls.add(url)

            # For completed downloads, always use the actual final size for both current and total
            self._report_progress(
                download_id, downloaded_bytes, downloaded_bytes, DownloadStatus.COMPLETED,
                filename=filename, url=url
            )

            result_path = filepath

        except Exception as e:
            logger.error(f"Download failed for {url}: {str(e)}")
            self._report_progress(download_id, 0, 0, DownloadStatus.FAILED, error=str(e),
                                filename=filename, url=url)

            # Clean up temp file
            if temp_filepath and temp_filepath.exists():
                await asyncio.to_thread(temp_filepath.unlink)

        return result_path

    async def get_direct_url(self, session: aiohttp.ClientSession, url: str) -> Optional[str]:
        """
        Convert special URLs to direct download links

        Args:
            session: aiohttp client session
            url: URL to check and possibly convert

        Returns:
            Direct URL or original URL if no conversion is needed
        """
        try:
            if "redgifs.com" in url:
                async with session.get(url) as response:
                    response.raise_for_status()
                    html = await response.text()
                if match := re.search(
                    r"(https://media\.redgifs\.com/.*?-mobile\.jpg)", html
                ):
                    return match.group(1).replace("-mobile.jpg", ".mp4")
            if "vidble.com/watch" in url:
                vid_id = url.split("=")[1]
                return f"https://vidble.com/{vid_id}.mp4"
        except Exception:
            return None
        return url

    def _report_progress(self, download_id: str, current: int, total: int,
                       status: str, error: Optional[str] = None,
                       filename: str = "", url: str = "") -> None:
        """Report download progress through callback if available"""

        # Log callback data for debugging
        logger.debug(f"Progress report: {download_id}, {current}/{total} bytes, status={status}")

        if self.progress_callback:
            self.progress_callback(download_id, current, total, status, error, filename, url)
