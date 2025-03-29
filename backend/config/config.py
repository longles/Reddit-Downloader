import dotenv
from dataclasses import dataclass
from typing import Optional, FrozenSet, Dict, Any


@dataclass(slots=True, frozen=True)
class Config:
    client_id: str
    client_secret: str
    username: str
    password: str
    user_agent: str = "windows:reddit-archiver:v1.0"
    valid_formats: FrozenSet[str] = frozenset(("jpg", "jpeg", "png", "gif", "mp4"))
    chunk_size: int = 32768
    max_concurrent_downloads: int = 10
    download_limit: int = 100
    download_bars: bool = False

    @classmethod
    def from_env(cls, env_path: str, **kwargs) -> "Config":
        """Create a Config from environment file with optional overrides"""
        config_dict = dotenv.dotenv_values(env_path)

        # Convert specific fields to the correct type
        if "max_concurrent_downloads" in kwargs:
            config_dict["max_concurrent_downloads"] = int(kwargs["max_concurrent_downloads"])
        if "download_limit" in kwargs:
            config_dict["download_limit"] = int(kwargs["download_limit"])
        if "download_bars" in kwargs:
            config_dict["download_bars"] = bool(kwargs["download_bars"])
        if "concurrent" in kwargs:
            config_dict["max_concurrent_downloads"] = int(kwargs["concurrent"])
        if "limit" in kwargs:
            config_dict["download_limit"] = int(kwargs["limit"])

        # Use .pop() to avoid passing unknown arguments
        if "concurrent" in kwargs:
            kwargs.pop("concurrent")
        if "limit" in kwargs:
            kwargs.pop("limit")

        # Update with any remaining kwargs
        for key, value in kwargs.items():
            if key in {"client_id", "client_secret", "username", "password", "user_agent",
                       "max_concurrent_downloads", "download_limit", "download_bars", "chunk_size"}:
                config_dict[key] = value

        return cls(**config_dict)
