import dotenv
from dataclasses import dataclass
from typing import Optional, FrozenSet


@dataclass(slots=True, frozen=True)
class Config:
    """Configuration for the Reddit archiver."""

    client_id: str
    client_secret: str
    username: str
    password: str
    user_agent: str = "windows:reddit-archiver:v1.0"
    valid_formats: FrozenSet[str] = frozenset((".jpg", ".jpeg", ".png", ".gif", ".mp4"))
    chunk_size: int = 32768
    max_concurrent_downloads: int = 4
    download_limit: int = 100

    @classmethod
    def from_env(
        cls,
        env_path: str,
        concurrent_downloads: Optional[int] = None,
        download_limit: Optional[int] = None,
    ) -> "Config":
        """Create Config from environment file."""
        config_dict = dotenv.dotenv_values(env_path)
        if concurrent_downloads is not None:
            config_dict["max_concurrent_downloads"] = concurrent_downloads
        if download_limit is not None:
            config_dict["download_limit"] = download_limit
        return cls(**config_dict)
