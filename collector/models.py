"""The standard shapes every source adapter produces. The rest of the app sees only these."""

from dataclasses import dataclass
from datetime import date, datetime

from collector.dates import tehran_midnight_utc


@dataclass(frozen=True)
class Tag:
    kind: str  # "province" or "field"
    slug: str  # the source's own label id, e.g. "civil"
    label: str | None = None  # as shown on the source, e.g. "عمران"; listing cards carry none


@dataclass(frozen=True)
class Issue:
    """One problem found while collecting. Codes are listed in PLAN.md section 6."""

    code: str
    severity: str  # "error" or "warning"
    detail: str
    url: str | None = None

    @classmethod
    def error(cls, code: str, detail: str, url: str | None = None) -> "Issue":
        return cls(code, "error", detail, url)

    @classmethod
    def warning(cls, code: str, detail: str, url: str | None = None) -> "Issue":
        return cls(code, "warning", detail, url)


@dataclass(frozen=True)
class ListingItem:
    """One card on a listing page."""

    source_post_id: str
    url: str
    title: str
    published_date: date  # Gregorian date of the Tehran calendar day shown on the card
    tags: tuple[Tag, ...]


@dataclass(frozen=True)
class Posting:
    """One full posting, ready to store."""

    source: str
    source_post_id: str
    url: str
    title: str
    body: str  # plain text, one paragraph or list item per line
    published_date: date
    tags: tuple[Tag, ...]
    parser_version: str
    members_only_omitted: bool = False  # the source hid part of the posting (contact details) from the public

    @property
    def published_at(self) -> datetime:
        """00:00 Tehran on the publication day, in UTC (storage convention)."""
        return tehran_midnight_utc(self.published_date)
