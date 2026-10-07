"""Persian dates, the midnight-Tehran convention, UTC formatting and Tehran day ranges.

Expected Gregorian dates are written out by hand from calendar arithmetic
(1 Farvardin 1405 = 2026-03-21; months 1-6 have 31 days, 7-11 have 30), not computed
with the library under test.
"""

from datetime import date, datetime, timezone

import pytest

from collector.dates import (
    TEHRAN,
    DateParseError,
    collection_window,
    format_utc,
    jalali_to_gregorian,
    parse_jalali_date,
    tehran_day_range,
    tehran_midnight_utc,
    tehran_today,
)


def utc(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def test_card_date_becomes_midnight_tehran_in_utc():
    day = parse_jalali_date("۱۴ مهر ۱۴۰۵")
    assert day == date(2026, 10, 6)
    assert format_utc(tehran_midnight_utc(day)) == "2026-10-05T20:30:00Z"


@pytest.mark.parametrize(
    "text, expected",
    [
        ("۱ فروردین ۱۴۰۵", date(2026, 3, 21)),
        ("۱ اردیبهشت ۱۴۰۵", date(2026, 4, 21)),
        ("۱ خرداد ۱۴۰۵", date(2026, 5, 22)),
        ("۱ تیر ۱۴۰۵", date(2026, 6, 22)),
        ("۱ مرداد ۱۴۰۵", date(2026, 7, 23)),
        ("۱ شهریور ۱۴۰۵", date(2026, 8, 23)),
        ("۱ مهر ۱۴۰۵", date(2026, 9, 23)),
        ("۱ آبان ۱۴۰۵", date(2026, 10, 23)),
        ("۱ آذر ۱۴۰۵", date(2026, 11, 22)),
        ("۱ دی ۱۴۰۵", date(2026, 12, 22)),
        ("۱ بهمن ۱۴۰۵", date(2027, 1, 21)),
        ("۱ اسفند ۱۴۰۵", date(2027, 2, 20)),
    ],
)
def test_every_month_name(text, expected):
    assert parse_jalali_date(text) == expected


def test_last_day_of_31_and_30_day_months():
    assert parse_jalali_date("۳۱ شهریور ۱۴۰۵") == date(2026, 9, 22)
    assert parse_jalali_date("۳۰ مهر ۱۴۰۵") == date(2026, 10, 22)
    with pytest.raises(DateParseError):
        parse_jalali_date("۳۱ مهر ۱۴۰۵")


def test_esfand_30_exists_only_in_leap_years():
    assert jalali_to_gregorian(1403, 12, 30) == date(2025, 3, 20)  # 1403 is a leap year
    assert parse_jalali_date("۲۹ اسفند ۱۴۰۵") == date(2027, 3, 20)
    with pytest.raises(DateParseError):
        parse_jalali_date("۳۰ اسفند ۱۴۰۵")


def test_ascii_digits_and_arabic_letter_variants_are_accepted():
    assert parse_jalali_date("14 مهر 1405") == date(2026, 10, 6)
    assert parse_jalali_date("۱ دي ۱۴۰۵") == date(2026, 12, 22)  # Arabic yeh in دي


@pytest.mark.parametrize("text", ["۱۴ مهرماه ۱۴۰۵", "۱۴ October ۱۴۰۵", "", "دیروز", "۱۴/۰۷/۱۴۰۵"])
def test_unreadable_dates_raise_instead_of_guessing(text):
    with pytest.raises(DateParseError):
        parse_jalali_date(text)


def test_offset_comes_from_the_timezone_database_not_a_constant():
    # Iran observed daylight saving time until 2022: midnight on 2021-06-01 was UTC+04:30.
    assert format_utc(tehran_midnight_utc(date(2021, 6, 1))) == "2021-05-31T19:30:00Z"


def test_window_covers_today_and_six_previous_tehran_days():
    window = collection_window(utc("2026-10-07T17:00:00Z"))  # 20:30 in Tehran
    assert (window.first_day, window.last_day) == (date(2026, 10, 1), date(2026, 10, 7))
    assert format_utc(window.start) == "2026-09-30T20:30:00Z"
    assert format_utc(window.end) == "2026-10-07T20:30:00Z"


def test_today_is_decided_in_tehran_not_utc():
    now = utc("2026-10-07T21:30:00Z")  # still 7 Oct in UTC, already 01:00 on 8 Oct in Tehran
    assert tehran_today(now) == date(2026, 10, 8)
    window = collection_window(now)
    assert (window.first_day, window.last_day) == (date(2026, 10, 2), date(2026, 10, 8))
    assert format_utc(window.start) == "2026-10-01T20:30:00Z"


@pytest.mark.parametrize(
    "instant, inside",
    [
        ("2026-09-30T20:29:59Z", False),
        ("2026-09-30T20:30:00Z", True),
        ("2026-10-07T20:29:59Z", True),
        ("2026-10-07T20:30:00Z", False),  # end is exclusive
    ],
)
def test_window_boundaries(instant, inside):
    assert collection_window(utc("2026-10-07T17:00:00Z")).contains(utc(instant)) is inside


def test_inclusive_day_filter_becomes_half_open_utc_range():
    days = tehran_day_range(date(2026, 10, 4), date(2026, 10, 6))
    assert format_utc(days.start) == "2026-10-03T20:30:00Z"
    assert format_utc(days.end) == "2026-10-06T20:30:00Z"
    single = tehran_day_range(date(2026, 10, 6), date(2026, 10, 6))
    assert single.contains(tehran_midnight_utc(date(2026, 10, 6)))
    assert not single.contains(tehran_midnight_utc(date(2026, 10, 7)))


def test_reversed_day_range_is_rejected():
    with pytest.raises(ValueError):
        tehran_day_range(date(2026, 10, 6), date(2026, 10, 4))


def test_naive_datetimes_are_rejected():
    with pytest.raises(ValueError):
        tehran_today(datetime(2026, 10, 7, 12, 0))
    with pytest.raises(ValueError):
        format_utc(datetime(2026, 10, 7, 12, 0))


def test_format_utc_converts_other_zones_to_z():
    assert format_utc(datetime(2026, 10, 7, 15, 30, tzinfo=TEHRAN)) == "2026-10-07T12:00:00Z"
