"""Source adapters: one module per website, all answering the same four questions.

Adding a website = one new module implementing `Source`, its fixtures, and one line in SOURCES.
"""

from typing import Protocol

from collector.models import Issue, ListingItem, Posting
from collector.sources.eng_estekhdam import EngEstekhdam


class Source(Protocol):
    name: str
    parser_version: str
    field_groups: dict[str, str]  # field-tag slug → industry group key (collector/industry.py)

    def listing_url(self, page: int) -> str:
        """Address of listing page `page` (1-based)."""

    def check_page(self, html: str, kind: str) -> str | None:
        """None if `html` is the expected kind of page ("listing" or "posting"), else an issue code."""

    def parse_listing(self, html: str) -> tuple[list[ListingItem], list[Issue]]:
        """Valid cards, plus one issue per card that could not be read."""

    def parse_posting(self, html: str, item: ListingItem) -> tuple[Posting | None, list[Issue]]:
        """The posting (None if it has an error) and any issues found."""


SOURCES: dict[str, Source] = {"eng-estekhdam": EngEstekhdam()}
