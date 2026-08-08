"""Brave Search API client with throttle and 429 backoff."""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)

BRAVE_ENDPOINT = "https://api.search.brave.com/res/v1/web/search"
MIN_INTERVAL_SEC = 1.1
MAX_RETRIES = 4


class BraveClient:
    def __init__(self, api_key: str, timeout: float = 30.0) -> None:
        if not api_key:
            raise ValueError("BRAVE_API_KEY is required")
        self._api_key = api_key
        self._timeout = timeout
        self._last_request_at = 0.0

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < MIN_INTERVAL_SEC:
            time.sleep(MIN_INTERVAL_SEC - elapsed)

    def search(
        self,
        query: str,
        *,
        freshness: str = "pw",
        count: int = 20,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Return web results for a query. Raises on hard failures."""
        params = {
            "q": query,
            "count": min(count, 20),
            "offset": max(0, min(offset, 9)),
            "freshness": freshness,
            "extra_snippets": "true",
            "text_decorations": "false",
            "spellcheck": "true",
        }
        headers = {
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "X-Subscription-Token": self._api_key,
        }

        for attempt in range(MAX_RETRIES):
            self._throttle()
            try:
                with httpx.Client(timeout=self._timeout) as client:
                    response = client.get(
                        BRAVE_ENDPOINT, params=params, headers=headers
                    )
                self._last_request_at = time.monotonic()

                if response.status_code == 429:
                    retry_after = float(response.headers.get("Retry-After", "2"))
                    wait = max(retry_after, 2.0 * (attempt + 1))
                    logger.warning(
                        "Brave 429 for %r; sleeping %.1fs (attempt %d)",
                        query,
                        wait,
                        attempt + 1,
                    )
                    time.sleep(wait)
                    continue

                response.raise_for_status()
                payload = response.json()
                results = (payload.get("web") or {}).get("results") or []
                return [self._normalize_result(r) for r in results]
            except httpx.HTTPStatusError as exc:
                logger.error(
                    "Brave HTTP %s for %r: %s",
                    exc.response.status_code,
                    query,
                    exc.response.text[:200],
                )
                raise
            except httpx.HTTPError as exc:
                wait = 2.0 * (attempt + 1)
                logger.warning(
                    "Brave network error for %r: %s; retry in %.1fs",
                    query,
                    exc,
                    wait,
                )
                time.sleep(wait)

        raise RuntimeError(f"Brave search failed after {MAX_RETRIES} retries: {query}")

    @staticmethod
    def _normalize_result(raw: dict[str, Any]) -> dict[str, Any]:
        snippets = list(raw.get("extra_snippets") or [])
        description = raw.get("description") or ""
        return {
            "title": (raw.get("title") or "").strip(),
            "url": (raw.get("url") or "").strip(),
            "description": description.strip(),
            "age": (raw.get("age") or "").strip(),
            "extra_snippets": [s.strip() for s in snippets if s],
        }
