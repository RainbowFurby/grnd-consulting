"""
Event-date extraction from Malaysian bazaar / vendor-call posts.

Posts in this space mix English and Malay freely, and dates show up in a
handful of recurring shapes:

    "8/8"                     "8 Ogos"          "8-9 Aug"
    "08-08-2026"              "8 & 9 August"    "23 hb Ogos"
    "Sabtu & Ahad"            "this weekend"    "hujung minggu ini"

The goal here is not a general-purpose date parser. It is to answer three
questions well enough to filter on:

    1. Does this post reference a weekend?
    2. What dates does it reference, if any?
    3. Are those dates still in the future?

Anything we cannot parse is reported as "unknown" rather than guessed at,
so the caller can decide how lenient to be.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta

# --------------------------------------------------------------------------
# Vocabulary
# --------------------------------------------------------------------------

MONTHS: dict[str, int] = {
    # English
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
    # Malay
    "januari": 1,
    "februari": 2,
    "mac": 3,
    "mei": 5,
    "julai": 7,
    "ogos": 8, "ogo": 8,
    "okt": 10, "oktober": 10,
    "dis": 12, "disember": 12,
}

WEEKDAY_WORDS: dict[str, int] = {
    "monday": 0, "mon": 0, "isnin": 0,
    "tuesday": 1, "tue": 1, "tues": 1, "selasa": 1,
    "wednesday": 2, "wed": 2, "rabu": 2,
    "thursday": 3, "thu": 3, "thurs": 3, "khamis": 3,
    "friday": 4, "fri": 4, "jumaat": 4, "jumat": 4,
    "saturday": 5, "sat": 5, "sabtu": 5,
    "sunday": 6, "sun": 6, "ahad": 6,
}

WEEKEND_PHRASES = (
    "weekend",
    "hujung minggu",
    "hujung mgu",
    "sat-sun",
    "sat & sun",
    "sat and sun",
    "sat/sun",
    "sabtu & ahad",
    "sabtu ahad",
    "sabtu dan ahad",
    "sabtu-ahad",
)

_MONTH_ALTERNATION = "|".join(sorted(MONTHS, key=len, reverse=True))

# "8 Aug", "8 Ogos 2026", "8hb Ogos", "8 hb Ogos"
_DAY_MONTH = re.compile(
    rf"\b(?P<day>\d{{1,2}})\s*(?:hb|haribulan)?\s*"
    rf"(?P<month>{_MONTH_ALTERNATION})\b"
    rf"(?:\s*(?P<year>\d{{4}}))?",
    re.IGNORECASE,
)

# "Aug 8", "August 8, 2026" — the lookahead keeps "May 8pm" from parsing as a date.
_MONTH_DAY = re.compile(
    rf"\b(?P<month>{_MONTH_ALTERNATION})\s+(?P<day>\d{{1,2}})\b(?!\s*(?:am|pm|[:.]\d))"
    rf"(?:\s*,?\s*(?P<year>\d{{4}}))?",
    re.IGNORECASE,
)

# "8-9 Aug", "8 & 9 Ogos", "23 dan 24 August", "8 - 9 Aug 2026"
_RANGE_DAY_MONTH = re.compile(
    rf"\b(?P<d1>\d{{1,2}})\s*(?:-|–|—|&|\+|/|and|dan|hingga|to)\s*"
    rf"(?P<d2>\d{{1,2}})\s*(?:hb|haribulan)?\s*"
    rf"(?P<month>{_MONTH_ALTERNATION})\b"
    rf"(?:\s*(?P<year>\d{{4}}))?",
    re.IGNORECASE,
)

# "8/8", "08-08-2026". Dots are deliberately not accepted as separators —
# "11.30" is a time far more often than it is a date. The trailing lookahead
# rejects "10-6pm" style opening hours.
_NUMERIC = re.compile(
    r"(?<![\d/\-])(?P<day>\d{1,2})[/\-](?P<month>\d{1,2})"
    r"(?:[/\-](?P<year>\d{2,4}))?(?![\d/\-])(?!\s*[ap]m)",
    re.IGNORECASE,
)

# "RM10-15" is a price range, not the 15th of October.
_PRICE_PREFIX = re.compile(r"(?:rm|myr|\$)\s*$", re.IGNORECASE)


@dataclass
class DateInfo:
    """What we managed to learn about when an event happens."""

    dates: list[date] = field(default_factory=list)
    mentions_weekend: bool = False
    has_future_date: bool = False
    has_only_past_dates: bool = False

    @property
    def is_weekend(self) -> bool:
        """True if an explicit weekend phrase or any weekend-falling date is present."""
        return self.mentions_weekend or any(d.weekday() >= 5 for d in self.dates)

    @property
    def earliest(self) -> date | None:
        return min(self.dates) if self.dates else None

    def describe(self) -> str:
        """Short human string for the Telegram alert, e.g. '8-9 Aug (Sat-Sun)'."""
        if not self.dates:
            return "weekend (date unclear)" if self.mentions_weekend else ""

        ordered = sorted(set(self.dates))
        shown = ordered[:3]
        day_names = [d.strftime("%a") for d in shown]
        if len(shown) == 1:
            return f"{shown[0].strftime('%-d %b')} ({day_names[0]})"

        same_month = len({(d.year, d.month) for d in shown}) == 1
        if same_month:
            days = "-".join(str(d.day) for d in shown)
            label = f"{days} {shown[0].strftime('%b')}"
        else:
            label = ", ".join(d.strftime("%-d %b") for d in shown)

        suffix = "-".join(day_names)
        more = f" +{len(ordered) - len(shown)} more" if len(ordered) > len(shown) else ""
        return f"{label} ({suffix}){more}"


def _resolve_year(day: int, month: int, year: int | None, today: date) -> date | None:
    """
    Build a date, inferring the year when the post omits it.

    Bazaar posts almost always advertise upcoming events, so a bare "8 Aug"
    seen in December means next August, not the one eight months gone. We
    roll forward when the bare date is more than `PAST_GRACE_DAYS` behind us,
    which keeps last-weekend's post from being read as next year's event.
    """
    PAST_GRACE_DAYS = 45

    if year is not None:
        if year < 100:
            year += 2000
        try:
            return date(year, month, day)
        except ValueError:
            return None

    for candidate_year in (today.year, today.year + 1):
        try:
            candidate = date(candidate_year, month, day)
        except ValueError:
            continue
        if candidate >= today - timedelta(days=PAST_GRACE_DAYS):
            return candidate
    return None


def _add(found: list[date], value: date | None) -> None:
    if value is not None and value not in found:
        found.append(value)


def extract_dates(text: str, today: date | None = None) -> DateInfo:
    """Pull every event date we can recognise out of a post."""
    today = today or date.today()
    lowered = text.lower()
    found: list[date] = []

    # Ranges first — "8-9 Aug" would otherwise be read as just "9 Aug".
    consumed_spans: list[tuple[int, int]] = []
    for m in _RANGE_DAY_MONTH.finditer(lowered):
        month = MONTHS[m.group("month").lower()]
        year = int(m.group("year")) if m.group("year") else None
        d1, d2 = int(m.group("d1")), int(m.group("d2"))
        start = _resolve_year(d1, month, year, today)
        end = _resolve_year(d2, month, year, today)
        _add(found, start)
        _add(found, end)
        # Fill a short span so "8-11 Aug" covers the weekend inside it.
        if start and end and 0 < (end - start).days <= 6:
            for offset in range(1, (end - start).days):
                _add(found, start + timedelta(days=offset))
        consumed_spans.append(m.span())

    def _overlaps_consumed(span: tuple[int, int]) -> bool:
        return any(span[0] < end and start < span[1] for start, end in consumed_spans)

    for pattern in (_DAY_MONTH, _MONTH_DAY):
        for m in pattern.finditer(lowered):
            if _overlaps_consumed(m.span()):
                continue
            month = MONTHS[m.group("month").lower()]
            year = int(m.group("year")) if m.group("year") else None
            _add(found, _resolve_year(int(m.group("day")), month, year, today))

    for m in _NUMERIC.finditer(lowered):
        if _PRICE_PREFIX.search(lowered[max(0, m.start() - 6):m.start()]):
            continue
        day, month = int(m.group("day")), int(m.group("month"))
        # Malaysian posts are day-first; anything with month > 12 is a
        # US-style date or not a date at all, so swap or skip.
        if month > 12:
            day, month = month, day
        if not (1 <= month <= 12 and 1 <= day <= 31):
            continue
        year = int(m.group("year")) if m.group("year") else None
        _add(found, _resolve_year(day, month, year, today))

    mentions_weekend = any(p in lowered for p in WEEKEND_PHRASES) or any(
        re.search(rf"\b{re.escape(word)}\b", lowered)
        for word, idx in WEEKDAY_WORDS.items()
        if idx >= 5
    )

    future = [d for d in found if d >= today]
    return DateInfo(
        dates=sorted(found),
        mentions_weekend=mentions_weekend,
        has_future_date=bool(future),
        has_only_past_dates=bool(found) and not future,
    )
