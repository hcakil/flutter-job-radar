"""Public job-board JSON feeds (Remotive + RemoteOK)."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from html import unescape
from typing import Any

import httpx

from age import age_label_from_datetime

logger = logging.getLogger(__name__)

REMOTIVE_URL = "https://remotive.com/api/remote-jobs"
REMOTEOK_URL = "https://remoteok.com/api"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_ISO_RE = re.compile(
    r"^(?P<dt>\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}:\d{2})?)"
)


def fetch_aggregator_jobs(*, timeout: float = 30.0) -> tuple[list[dict[str, Any]], int]:
    """Return (normalized jobs, error_count). Partial failure is allowed."""
    jobs: list[dict[str, Any]] = []
    errors = 0
    for name, fetcher in (
        ("remotive", _fetch_remotive),
        ("remoteok", _fetch_remoteok),
    ):
        try:
            batch = fetcher(timeout=timeout)
            logger.info("Aggregator %s → %d flutter jobs", name, len(batch))
            jobs.extend(batch)
        except Exception:
            errors += 1
            logger.exception("Aggregator failed: %s", name)
    return jobs, errors


def _headers() -> dict[str, str]:
    return {
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
    }


def _fetch_remotive(*, timeout: float) -> list[dict[str, Any]]:
    with httpx.Client(timeout=timeout, headers=_headers(), follow_redirects=True) as client:
        response = client.get(REMOTIVE_URL, params={"search": "flutter"})
        response.raise_for_status()
        payload = response.json()
    raw_jobs = payload.get("jobs") if isinstance(payload, dict) else payload
    if not isinstance(raw_jobs, list):
        return []
    out: list[dict[str, Any]] = []
    for item in raw_jobs:
        if not isinstance(item, dict):
            continue
        title = (item.get("title") or "").strip()
        company = (item.get("company_name") or "").strip()
        description = _strip_html(item.get("description") or "")
        tags = [str(t) for t in (item.get("tags") or []) if t]
        if not title or not _looks_flutter(title=title, tags=tags):
            continue
        url = (item.get("url") or "").strip()
        if not url:
            continue
        display = f"{title} - {company}".strip(" -") if company else title
        location = (item.get("candidate_required_location") or "").strip()
        extras = [p for p in (location, item.get("job_type") or "") if p]
        out.append(
            {
                "title": display,
                "url": url,
                "description": description[:800],
                "age": _age_from_value(item.get("publication_date")),
                "extra_snippets": extras,
            }
        )
    return out


def _fetch_remoteok(*, timeout: float) -> list[dict[str, Any]]:
    with httpx.Client(timeout=timeout, headers=_headers(), follow_redirects=True) as client:
        response = client.get(REMOTEOK_URL)
        response.raise_for_status()
        payload = response.json()
    if not isinstance(payload, list):
        return []
    out: list[dict[str, Any]] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        title = (item.get("position") or item.get("title") or "").strip()
        if not title:
            continue
        company = (item.get("company") or "").strip()
        tags = [str(t) for t in (item.get("tags") or []) if t]
        description = _strip_html(item.get("description") or "")
        if not _looks_flutter(title=title, tags=tags):
            continue
        url = (item.get("apply_url") or item.get("url") or "").strip()
        if not url:
            continue
        display = f"{title} - {company}".strip(" -") if company else title
        age = _age_from_epoch_or_date(item.get("epoch"), item.get("date"))
        extras = [p for p in (" ".join(tags), item.get("location") or "") if p]
        out.append(
            {
                "title": display,
                "url": url,
                "description": description[:800],
                "age": age,
                "extra_snippets": extras,
            }
        )
    return out


def _looks_flutter(*, title: str, tags: list[str]) -> bool:
    """Title/tags only. Description laundry-lists (Lemon.io) and company 'Dart' are ignored."""
    if re.search(r"\bflutter\b", title or "", flags=re.IGNORECASE):
        return True
    if re.search(
        r"\bdart\b.+\b(developer|engineer|sdk)\b|\b(developer|engineer).+\bdart\b",
        title or "",
        flags=re.IGNORECASE,
    ):
        return True
    cleaned = [t.strip().lower() for t in tags if t]
    if len(cleaned) <= 12 and ("flutter" in cleaned or "dart" in cleaned):
        return bool(
            re.search(
                r"\b(developer|engineer|mobile|software|programmer)\b",
                title or "",
                flags=re.IGNORECASE,
            )
        )
    return False


def _strip_html(text: str) -> str:
    cleaned = unescape(_HTML_TAG_RE.sub(" ", text or ""))
    return re.sub(r"\s+", " ", cleaned).strip()


def _age_from_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (int, float)):
        return _age_from_epoch_or_date(value, None)
    return _age_from_epoch_or_date(None, str(value))


def _age_from_epoch_or_date(epoch: Any, date_val: Any) -> str:
    when: datetime | None = None
    if isinstance(epoch, (int, float)) and epoch > 1_000_000_000_000:
        epoch = float(epoch) / 1000.0
    if isinstance(epoch, (int, float)) and epoch > 0:
        when = datetime.fromtimestamp(float(epoch), tz=timezone.utc)
    elif date_val:
        text = str(date_val).strip().replace("Z", "+00:00")
        if text.isdigit():
            stamp = float(text)
            if stamp > 1_000_000_000_000:
                stamp /= 1000.0
            when = datetime.fromtimestamp(stamp, tz=timezone.utc)
        else:
            try:
                if len(text) == 10:
                    parsed = datetime.fromisoformat(text)
                else:
                    parsed = datetime.fromisoformat(text)
            except ValueError:
                match = _ISO_RE.match(text)
                parsed = None
                if match:
                    raw = match.group("dt").replace(" ", "T")
                    if "T" not in raw:
                        raw += "T00:00:00"
                    try:
                        parsed = datetime.fromisoformat(raw)
                    except ValueError:
                        parsed = None
            if parsed is not None:
                when = parsed
    if when is None:
        return ""
    return age_label_from_datetime(when)
