import asyncio
from typing import List

from config.config import Config
from core.archiver import RedditArchiver
from utils.cli import parse_arguments


async def process_users(archiver: RedditArchiver, usernames: List[str]) -> None:
    """Process multiple usernames sequentially."""
    try:
        for username in usernames:
            await archiver.archive_user(username)
    finally:
        await archiver.close()


def main() -> None:
    """CLI entry point for Reddit archiver."""
    usernames, limit, concurrent, download_bars = parse_arguments()

    if not usernames:
        print("No usernames found to process")
        return

    # Create config and archiver
    config = Config.from_env(
        "./reddit.env", concurrent, limit, download_bars
    )
    archiver = RedditArchiver(config)

    # Process all usernames
    asyncio.run(process_users(archiver, usernames))


if __name__ == "__main__":
    main()
