"""Persian (Jalali) dates, Tehran calendar days and UTC timestamps.

Conventions:
- Every stored or returned timestamp is UTC, formatted ISO 8601 with "Z".
- The source shows only a date. A posting's publication instant is 00:00 in Tehran on that
  day: a storage convention, not an observed publication time.
- Day ranges are Tehran calendar days, converted to a half-open UTC range [start, end).
- Tehran's offset always comes from the time zone database, never a hard-coded +03:30.
"""

import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import jdatetime

from collector.normalize import normalize

TEHRAN = ZoneInfo("Asia/Tehran")
WINDOW_DAYS = 7  # today and the previous six calendar days

MONTHS = {
    name: number
    for number, name in enumerate(
        ["فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
         "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"],
        start=1,
    )
}
_DATE_TEXT = re.compile(r"^(\d{1,2}) (\S+) (\d{4})$")


class DateParseError(ValueError):
    """A source date that cannot be read. Never replaced by a guessed default."""


def jalali_to_gregorian(year: int, month: int, day: int) -> date:
    try:
        return jdatetime.date(year, month, day).togregorian()
    except ValueError as error:
        raise DateParseError(f"no such Jalali date {year}-{month:02d}-{day:02d}") from error


def parse_jalali_date(text: str) -> date:
    """'۱۴ مهر ۱۴۰۵' → date(2026, 10, 6). Raises DateParseError on anything else."""
    match = _DATE_TEXT.match(normalize(text))
    if not match:
        raise DateParseError(f"not a 'day month year' date: {text!r}")
    day, month_name, year = match.groups()
    if month_name not in MONTHS:
        raise DateParseError(f"unknown month {month_name!r} in {text!r}")
    return jalali_to_gregorian(int(year), MONTHS[month_name], int(day))


def tehran_midnight_utc(day: date) -> datetime:
    """00:00 Tehran on `day`, as an aware UTC datetime."""
    return datetime.combine(day, time(0), tzinfo=TEHRAN).astimezone(timezone.utc)


def tehran_today(now: datetime) -> date:
    """The calendar day in Tehran at instant `now` (which must carry a time zone)."""
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    return now.astimezone(TEHRAN).date()


@dataclass(frozen=True)
class DayRange:
    """Tehran calendar days first_day..last_day (inclusive) as UTC [start, end)."""

    first_day: date
    last_day: date
    start: datetime
    end: datetime

    def contains(self, instant: datetime) -> bool:
        return self.start <= instant < self.end


def tehran_day_range(first_day: date, last_day: date) -> DayRange:
    if first_day > last_day:
        raise ValueError(f"start day {first_day} is after end day {last_day}")
    return DayRange(
        first_day,
        last_day,
        tehran_midnight_utc(first_day),
        tehran_midnight_utc(last_day + timedelta(days=1)),
    )


def collection_window(now: datetime) -> DayRange:
    """Today in Tehran and the previous six days. Call once, at the start of a run."""
    today = tehran_today(now)
    return tehran_day_range(today - timedelta(days=WINDOW_DAYS - 1), today)


def format_utc(instant: datetime) -> str:
    """ISO 8601 in UTC with 'Z', e.g. 2026-10-05T20:30:00Z."""
    if instant.tzinfo is None:
        raise ValueError("instant must be timezone-aware")
    return instant.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
