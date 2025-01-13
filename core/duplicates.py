import asyncio
import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Set

import imagehash
from PIL import Image


Image.MAX_IMAGE_PIXELS = None


@dataclass
class FileHash:
    path: Path
    hash_value: str


class DuplicateHandler:
    def __init__(self, chunk_size: int = 65536):
        self.chunk_size = chunk_size

    @staticmethod
    def get_image_hash(file: Path) -> FileHash:
        try:
            image = Image.open(file).convert("RGB")
            hash_value = imagehash.dhash(image)
            return FileHash(file, str(hash_value))
        except Exception as e:
            print(f"Error hashing image {file}: {e}")
        return FileHash(file, "")

    @staticmethod
    def get_file_hash(file: Path, chunk_size: int) -> FileHash:
        sha256_hash = hashlib.sha256()
        try:
            with open(file, "rb") as f:
                while chunk := f.read(chunk_size):
                    sha256_hash.update(chunk)
            return FileHash(file, sha256_hash.hexdigest())
        except Exception as e:
            print(f"Error calculating hash for {file}: {e}")
            return FileHash(file, "")

    async def remove_duplicates(self, path: Path, valid_formats: Set[str]) -> int:
        files = [f for f in path.glob("*") if f.suffix.lower() in valid_formats]
        image_files = [f for f in files if f.suffix.lower() != ".mp4"]
        video_files = [f for f in files if f.suffix.lower() == ".mp4"]

        hash_map: Dict[str, List[Path]] = {}
        image_hash = video_hash = []

        if image_files:
            image_hash = await asyncio.gather(
                *[asyncio.to_thread(self.get_image_hash, f) for f in image_files]
            )

        if video_files:
            video_hash = await asyncio.gather(
                *[
                    asyncio.to_thread(self.get_file_hash, f, self.chunk_size)
                    for f in video_files
                ]
            )

        for file_hash in image_hash + video_hash:
            if file_hash.hash_value:
                hash_map.setdefault(file_hash.hash_value, []).append(file_hash.path)

        return await self.remove_duplicates_from_map(hash_map)

    async def remove_duplicates_from_map(self, hash_map: Dict[str, List[Path]]) -> int:
        removed = 0
        for files in hash_map.values():
            if len(files) <= 1:
                continue

            files.sort(key=lambda f: f.stat().st_mtime)
            for duplicate in files[1:]:
                try:
                    duplicate.unlink()
                    removed += 1
                except Exception as e:
                    print(f"Error removing {duplicate}: {e}")

        return removed


async def remove_duplicates(
    path: Path, valid_formats: Set[str], chunk_size: int = 65536
) -> int:
    handler = DuplicateHandler(chunk_size)
    return await handler.remove_duplicates(path, valid_formats)
