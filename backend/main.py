import asyncio
from typing import List
from pathlib import Path

from config.config import Config
from utils.cli import parse_arguments
from core.archiver import RedditArchiver  # Added missing import


async def process_users(
    config: Config,
    usernames: List[str],
    download_limit: int = 100
) -> None:
    """Process multiple usernames and remove duplicates at the end."""
    if not usernames:
        print("[ERROR] No usernames provided")
        return

    print(f"[INFO] Starting archive process for {len(usernames)} users")

    # Create archiver - fixed initialization
    archiver = RedditArchiver(config)
    user_paths = []

    try:
        # Process each user
        for username in usernames:
            path = await archiver.archive_user(username, download_limit)
            user_paths.append(path)

        # Remove duplicates after all users have been processed
        print("[INFO] Removing duplicates across all downloaded content...")
        removed_count = 0
        for path in user_paths:
            if path.exists() and path.is_dir():
                count = await archiver.remove_duplicates_in_path(path)
                removed_count += count

        print(f"[SUCCESS] Removed {removed_count} duplicate files")
    finally:
        await archiver.close()


def main() -> None:
    """CLI entry point for Reddit archiver."""
    usernames, limit, concurrent, download_bars = parse_arguments()

    if not usernames:
        print("[ERROR] No usernames found to process")
        return

    # Create config
    config = Config.from_env(
        "./reddit.env", concurrent=concurrent, limit=limit, download_bars=download_bars
    )

    # Process all usernames
    asyncio.run(process_users(config, usernames, config.download_limit))
    print("[SUCCESS] Archive process complete")


if __name__ == "__main__":
    main()
