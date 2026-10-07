"""One text normalization, shared by stored search text, search queries, tags and dates.

Using the same function on both sides of every comparison keeps them from drifting apart.
"""

import re

# Persian (۰-۹) and Arabic-Indic (٠-٩) digits → ASCII; Arabic yeh/kaf → Persian forms.
_TABLE = str.maketrans(
    "۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩يك",
    "01234567890123456789یک",
)
_ZWNJ = "‌"  # zero-width non-joiner: the "half-space" inside Persian words
_SPACES = re.compile(r"\s+")


def ascii_digits(text: str) -> str:
    """Only the digit and letter-variant mapping, without case or spacing changes."""
    return text.translate(_TABLE)


def normalize(text: str) -> str:
    """Casefold Latin, unify Persian letter and digit variants, collapse spacing."""
    text = ascii_digits(text).replace(_ZWNJ, " ").casefold()
    return _SPACES.sub(" ", text).strip()
