"""Parse listing age strings and gate late-indexed search results."""

from __future__ import annotations

import re
from datetime import datetime, timezone

# Brave often indexes LinkedIn/ATS days late. 3 days dropped still-open
# jobs (Netguru ~1 week). 14 days still skips month-old closed Easy Apply.
STALE_MAX_DAYS = 14

_AGE_RE = re.compile(
    r"(?:about\s+)?(\d+)\s*(minute|hour|day|week|month|year)s?\s+ago",
    flags=re.IGNORECASE,
)


def parse_age_days(age: str) -> int | None:
    """Best-effort age in whole days. None if unknown."""
    text = (age or "").strip().lower()
    if not text:
        return None
    if text in {"today", "just now", "now"}:
        return 0
    if text == "yesterday":
        return 1
    match = _AGE_RE.search(text)
    if not match:
        return None
    count = int(match.group(1))
    unit = match.group(2).lower()
    if unit == "minute":
        return 0
    if unit == "hour":
        return count // 24
    if unit == "day":
        return count
    if unit == "week":
        return count * 7
    if unit == "month":
        return count * 30
    return count * 365


def format_age_days(days: int) -> str:
    """Brave-style age label for display."""
    if days <= 0:
        return "today"
    if days == 1:
        return "1 day ago"
    if days < 7:
        return f"{days} days ago"
    weeks = max(1, days // 7)
    if days < 30:
        return "1 week ago" if weeks == 1 else f"{weeks} weeks ago"
    months = max(1, days // 30)
    return "1 month ago" if months == 1 else f"{months} months ago"


def age_label_from_datetime(when: datetime) -> str:
    now = datetime.now(timezone.utc)
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    days = max(0, (now - when.astimezone(timezone.utc)).days)
    return format_age_days(days)


def is_stale_age(age: str, *, max_days: int = STALE_MAX_DAYS) -> bool:
    """True when the listing is older than max_days. Unknown age is not stale."""
    days = parse_age_days(age)
    if days is None:
        return False
    return days > max_days
