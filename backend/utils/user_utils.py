from pathlib import Path
from typing import List

def get_usernames_from_file(file_path: str) -> List[str]:
    """Read usernames from a file, one per line."""
    try:
        with open(file_path, 'r') as file:
            return [line.strip() for line in file if line.strip()]
    except Exception as e:
        print(f"Error reading usernames file: {e}")
        return []


def get_usernames_from_folders() -> List[str]:
    """Get usernames from existing folders in the downloads directory."""
    downloads_dir = Path("downloads")
    if not downloads_dir.exists() or not downloads_dir.is_dir():
        print("Downloads directory not found")
        return []

    return [folder.name for folder in downloads_dir.iterdir() if folder.is_dir()]