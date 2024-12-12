from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional


@dataclass(slots=True)
class SubmissionData:
    """Reddit submission data container."""

    id: str
    url: str
    created: float
    media_metadata: Optional[Dict[str, Any]] = field(default=None)
    title: Optional[str] = field(default=None)

    @property
    def date_str(self) -> str:
        """Format submission date as YYYY-MM-DD."""
        return datetime.fromtimestamp(self.created).strftime("%Y-%m-%d")

    @property
    def has_gallery(self) -> bool:
        """Check if submission contains a gallery."""
        return bool(self.media_metadata)

    @classmethod
    def from_praw_submission(cls, submission: Any) -> "SubmissionData":
        """Create SubmissionData from a PRAW submission object."""
        return cls(
            id=submission.id,
            url=submission.url,
            created=submission.created,
            media_metadata=getattr(submission, "media_metadata", None),
            title=submission.title,
        )
