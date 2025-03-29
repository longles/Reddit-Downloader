import argparse
from typing import Tuple, List, Optional

from utils.user_utils import get_usernames_from_file, get_usernames_from_folders

def parse_arguments() -> Tuple[List[str], Optional[int], Optional[int], bool]:
    """Parse command line arguments and return processed values."""
    parser = argparse.ArgumentParser(description="Archive Reddit user submissions")

    # Username input group - allow only one of these options
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--username", "-u", help="Single Reddit username")
    group.add_argument("--from-file", "-f", help="Path to a file with usernames (one per line)")
    group.add_argument("--from-folders", "-F", action="store_true", help="Use existing folder names as usernames")

    # Other options
    parser.add_argument("-l", "--limit", type=int, help="Submission limit")
    parser.add_argument(
        "-c", "--concurrent", type=int, help="Number of concurrent downloads"
    )
    parser.add_argument(
        "-d", "--download-bars", action="store_true", help="Show download bars"
    )
    args = parser.parse_args()

    # Get usernames based on the provided option
    usernames: List[str] = []
    if args.username:
        usernames = [args.username]
    elif args.from_file:
        usernames = get_usernames_from_file(args.from_file)
    elif args.from_folders:
        usernames = get_usernames_from_folders()

    return usernames, args.limit, args.concurrent, args.download_bars