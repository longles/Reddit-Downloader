import argparse
import asyncio

from core.archiver import RedditArchiver


def main() -> None:
    """CLI entry point for Reddit archiver."""
    parser = argparse.ArgumentParser(description="Archive Reddit user submissions")
    parser.add_argument("username", help="Reddit username")
    parser.add_argument("-l", "--limit", type=int, help="Submission limit")
    parser.add_argument(
        "-c", "--concurrent", type=int, help="Number of concurrent downloads"
    )
    args = parser.parse_args()

    archiver = RedditArchiver("./reddit.env", args.concurrent, args.limit)
    asyncio.run(archiver.archive_user(args.username))


if __name__ == "__main__":
    main()
