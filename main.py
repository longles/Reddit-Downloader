import argparse
import asyncio

from core.archiver import RedditArchiver
from config.config import Config


def main() -> None:
    """CLI entry point for Reddit archiver."""
    parser = argparse.ArgumentParser(description="Archive Reddit user submissions")
    parser.add_argument("username", help="Reddit username")
    parser.add_argument("-l", "--limit", type=int, help="Submission limit")
    parser.add_argument(
        "-c", "--concurrent", type=int, help="Number of concurrent downloads"
    )
    parser.add_argument(
        "-d", "--download-bars", action="store_true", help="Show download bars"
    )
    args = parser.parse_args()

    config = Config.from_env(
        "./reddit.env", args.concurrent, args.limit, args.download_bars
    )
    archiver = RedditArchiver(config)
    asyncio.run(archiver.archive_user(args.username))


if __name__ == "__main__":
    main()
