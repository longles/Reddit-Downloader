import asyncio
import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Set
import aiofiles
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

    async def calculate_file_hash(self, file_path: Path) -> str:
        sha256_hash = hashlib.sha256()
        try:
            async with aiofiles.open(file_path, "rb") as f:
                while chunk := await f.read(self.chunk_size):
                    sha256_hash.update(chunk)
            return sha256_hash.hexdigest()
        except Exception as e:
            print(f"Error calculating hash for {file_path}: {e}")
            return ""

    async def get_image_hash(self, file: Path) -> FileHash:
        try:
            image = Image.open(file).convert("RGB")
            hash_value = imagehash.dhash(image)
            return FileHash(file, str(hash_value))
        except Exception as e:
            print(f"Error hashing image {file}: {e}")
        return FileHash(file, "")

    async def remove_duplicates(self, path: Path, valid_formats: Set[str]) -> int:
        files = [f for f in path.glob("*") if f.suffix.lower() in valid_formats]
        image_files = [f for f in files if f.suffix.lower() != ".mp4"]
        video_files = [f for f in files if f.suffix.lower() == ".mp4"]

        removed = 0

        if image_files:
            hash_map: Dict[str, List[Path]] = {}
            hash_results = await asyncio.gather(
                *[self.get_image_hash(f) for f in image_files]
            )

            for file_hash in hash_results:
                if file_hash.hash_value:
                    hash_map.setdefault(file_hash.hash_value, []).append(file_hash.path)

            removed += await self._remove_duplicates_from_map(hash_map)

        if video_files:
            hash_map: Dict[str, List[Path]] = {}
            hash_results = await asyncio.gather(
                *[self.calculate_file_hash(f) for f in video_files]
            )

            for file_hash, path in zip(hash_results, video_files):
                if file_hash:
                    hash_map.setdefault(file_hash, []).append(path)

            removed += await self._remove_duplicates_from_map(hash_map)

        return removed

    async def _remove_duplicates_from_map(self, hash_map: Dict[str, List[Path]]) -> int:
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
