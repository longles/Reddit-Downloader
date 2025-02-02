import asyncio
import re
from pathlib import Path
from typing import Optional, Set

import aiofiles
import aiohttp
from tqdm import tqdm

from config.config import Config


class Downloader:
    def __init__(self, config: Config):
        self.config = config
        self._download_semaphore = asyncio.Semaphore(config.max_concurrent_downloads)
        self._seen_urls: Set[str] = set() 

    async def is_url_seen(self, url: str) -> bool:
        return url in self._seen_urls

    async def mark_url_seen(self, url: str) -> None:
        self._seen_urls.add(url)

    async def download_file(
        self, session: aiohttp.ClientSession, url: str, path: Path, filename: str
    ) -> None:
        if await self.is_url_seen(url):
            return

        try:
            filepath = path / filename
            temp_filepath = filepath.with_suffix(".tmp")

            async with self._download_semaphore, session.get(url) as response:
                response.raise_for_status()
                total_bytes = int(response.headers.get("content-length", 0))

                with tqdm(
                    total=total_bytes,
                    unit="B",
                    unit_scale=True,
                    desc=filename,
                    leave=False,
                ) as pbar:
                    async with aiofiles.open(temp_filepath, "wb") as f:
                        async for chunk in response.content.iter_chunked(
                            self.config.chunk_size
                        ):
                            await f.write(chunk)
                            pbar.update(len(chunk))

            await asyncio.to_thread(temp_filepath.replace, filepath)
            await self.mark_url_seen(url)

        except Exception:
            if temp_filepath.exists():
                await asyncio.to_thread(temp_filepath.unlink)

    async def get_direct_url(
        self, session: aiohttp.ClientSession, url: str
    ) -> Optional[str]:
        try:
            if "redgifs.com" in url:
                async with session.get(url) as response:
                    response.raise_for_status()
                    html = await response.text()
                if match := re.search(
                    r"(https://media\.redgifs\.com/.*?-mobile\.jpg)", html
                ):
                    return match.group(1).replace("-mobile.jpg", ".mp4")
        except Exception:
            return None
        return url
