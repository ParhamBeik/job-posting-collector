"""normalize(): look-alike spellings of the same text compare equal."""

import pytest

from collector.normalize import normalize


@pytest.mark.parametrize(
    "a, b",
    [
        ("نقشه برداري", "نقشه برداری"),  # Arabic yeh (as on the site) vs Persian yeh
        ("كارشناس", "کارشناس"),  # Arabic kaf vs Persian kaf
        ("AutoCAD", "autocad"),
        ("۳ سال", "3 سال"),  # Persian digits
        ("٣ سال", "3 سال"),  # Arabic-Indic digits
        ("پروژه‌های", "پروژه های"),  # half-space vs space
        ("  مهندس   عمران\n", "مهندس عمران"),
    ],
)
def test_variants_normalize_to_the_same_text(a, b):
    assert normalize(a) == normalize(b)


def test_different_words_stay_different():
    assert normalize("عمران") != normalize("معماری")


def test_output_is_the_canonical_form():
    assert normalize("  نقشه برداري ۱۴۰۵  AutoCAD ") == "نقشه برداری 1405 autocad"
