from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional


@dataclass(slots=True)
class SubmissionData:
    id: str
    url: str
    created: float
    media_metadata: Optional[Dict[str, Any]] = field(default=None)
    title: Optional[str] = field(default=None)

    @property
    def date_str(self) -> str:
        return datetime.fromtimestamp(self.created).strftime("%Y-%m-%d")

    @property
    def has_gallery(self) -> bool:
        return bool(self.media_metadata)

    @classmethod
    def from_praw_submission(cls, submission: Any) -> "SubmissionData":
        return cls(
            id=submission.id,
            url=submission.url,
            created=submission.created,
            media_metadata=getattr(submission, "media_metadata", None),
            title=submission.title,
        )
