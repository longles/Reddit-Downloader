import asyncio
import hashlib
import concurrent.futures
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Set, Tuple

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
            return FileHash(file, str(imagehash.phash(image)))
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
        # Group files by size first for quick filtering
        size_groups: Dict[int, List[Tuple[Path, bool]]] = {}

        files = [
            (f, f.suffix.lower() in [".mp4", ".gif"])  # Treat GIFs like videos
            for f in path.glob("*")
            if f.suffix.lower()[1:] in valid_formats
        ]

        if not files:
            return 0

        # Group by file size first
        for file, is_video in files:
            try:
                file_size = file.stat().st_size
                size_groups.setdefault(file_size, []).append((file, is_video))
            except Exception as e:
                print(f"Error getting file size for {file}: {e}")

        # Only process groups with more than one file (potential duplicates)
        hash_map: Dict[str, List[Path]] = {}
        tasks = []
        loop = asyncio.get_event_loop()

        with concurrent.futures.ProcessPoolExecutor() as process_pool:
            for size_group in size_groups.values():
                if len(size_group) <= 1:
                    continue  # Skip unique file sizes

                for file, is_video in size_group:
                    if is_video:
                        tasks.append(
                            loop.run_in_executor(
                                process_pool,
                                self._process_file_hash,
                                file,
                                self.chunk_size,
                            )
                        )
                    else:
                        tasks.append(
                            loop.run_in_executor(
                                process_pool, self._process_image_hash, file
                            )
                        )

            if tasks:  # Only gather if there are tasks
                file_hashes = await asyncio.gather(*tasks)

                for file_hash in file_hashes:
                    if file_hash.hash_value:
                        hash_map.setdefault(file_hash.hash_value, []).append(
                            file_hash.path
                        )

        batch_size = 100
        total_removed = 0

        for i in range(0, len(tasks), batch_size):
            batch_tasks = tasks[i : i + batch_size]
            batch_hashes = await asyncio.gather(*batch_tasks)
            batch_hash_map: Dict[str, List[Path]] = {}

            for file_hash in batch_hashes:
                if file_hash.hash_value:
                    batch_hash_map.setdefault(file_hash.hash_value, []).append(
                        file_hash.path
                    )

            total_removed += await self.remove_duplicates_from_map(batch_hash_map)

        return total_removed

    # Static methods for process pool (must be picklable)
    @staticmethod
    def _process_image_hash(file):
        try:
            image = Image.open(file).convert("RGB")
            phash = imagehash.phash(image)
            whash = imagehash.whash(image)
            combined = f"{phash}_{whash}"
            return FileHash(file, combined)
        except Exception as e:
            print(f"Error hashing image {file}: {e}")
        return FileHash(file, "")

    @staticmethod
    def _process_file_hash(file, chunk_size):
        sha256_hash = hashlib.sha256()
        try:
            with open(file, "rb") as f:
                while chunk := f.read(chunk_size):
                    sha256_hash.update(chunk)
            return FileHash(file, sha256_hash.hexdigest())
        except Exception as e:
            print(f"Error calculating hash for {file}: {e}")
            return FileHash(file, "")

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
