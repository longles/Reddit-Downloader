import asyncio
import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Set, Tuple

import aiofiles
import imagehash
import numpy as np
from PIL import Image

Image.MAX_IMAGE_PIXELS = None


@dataclass
class FileHash:
    path: Path
    hash_value: str


def alpharemover(image: Image.Image) -> Image.Image:
    if image.mode != "RGBA":
        return image
    canvas = Image.new("RGBA", image.size, (255, 255, 255, 255))
    canvas.paste(image, mask=image)
    return canvas.convert("RGB")


def with_ztransform_preprocess(hashfunc, hash_size=8):
    def function(path):
        image = alpharemover(Image.open(path))
        image = image.convert("L").resize((hash_size, hash_size), Image.LANCZOS)
        data = image.getdata()
        quantiles = np.arange(100)
        quantiles_values = np.percentile(data, quantiles)
        zdata = (np.interp(data, quantiles_values, quantiles) / 100 * 255).astype(
            np.uint8
        )
        image.putdata(zdata)
        return hashfunc(image)

    return function


dhash_z_transformed = with_ztransform_preprocess(imagehash.dhash, hash_size=8)


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

    async def get_image_hash(self, file: Path) -> Tuple[Path, str]:
        try:
            if hash_value := await asyncio.get_event_loop().run_in_executor(
                None, dhash_z_transformed, str(file)
            ):
                return FileHash(file, str(hash_value))
        except Exception as e:
            print(f"Error hashing image {file}: {e}")
        return FileHash(file, "")

    async def get_video_hash(self, file: Path) -> Tuple[Path, str]:
        hash_value = await self.calculate_file_hash(file)
        return FileHash(file, hash_value)

    async def remove_duplicates(self, path: Path, valid_formats: Set[str]) -> int:
        files = [f for f in path.glob("*") if f.suffix.lower() in valid_formats]
        image_files = [
            f for f in files if f.suffix.lower() in {".jpg", ".jpeg", ".png", ".gif"}
        ]
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
                *[self.get_video_hash(f) for f in video_files]
            )

            for file_hash in hash_results:
                if file_hash.hash_value:
                    hash_map.setdefault(file_hash.hash_value, []).append(file_hash.path)

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
