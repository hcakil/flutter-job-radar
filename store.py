"""SQLite persistence with URL dedupe."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse


TRACKING_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "utm_id",
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
    "ref",
    "ref_src",
}


@dataclass
class JobRow:
    url: str
    title: str
    snippet: str
    source: str
    score: int
    bucket: str
    age: str
    matched: str
    first_seen: str
    last_seen: str
    notified: int
    is_new: bool = False


def normalize_url(url: str) -> str:
    """Canonicalize job URLs for dedupe."""
    url = (url or "").strip()
    if not url:
        return ""
    parsed = urlparse(url)
    scheme = (parsed.scheme or "https").lower()
    netloc = parsed.netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    path = parsed.path.rstrip("/") or ""
    query_pairs = [
        (k, v)
        for k, v in parse_qsl(parsed.query, keep_blank_values=True)
        if k.lower() not in TRACKING_PARAMS
    ]
    query = urlencode(query_pairs, doseq=True)
    return urlunparse((scheme, netloc, path, "", query, ""))


def source_from_url(url: str) -> str:
    host = urlparse(url).netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return host


class JobStore:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def close(self) -> None:
        self._conn.close()

    def _init_schema(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                url TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                snippet TEXT NOT NULL DEFAULT '',
                source TEXT NOT NULL DEFAULT '',
                score INTEGER NOT NULL DEFAULT 0,
                bucket TEXT NOT NULL DEFAULT 'RED',
                age TEXT NOT NULL DEFAULT '',
                matched TEXT NOT NULL DEFAULT '',
                first_seen TEXT NOT NULL,
                last_seen TEXT NOT NULL,
                notified INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_jobs_bucket ON jobs(bucket);
            CREATE INDEX IF NOT EXISTS idx_jobs_notified ON jobs(notified);
            """
        )
        self._conn.commit()

    def job_count(self) -> int:
        row = self._conn.execute("SELECT COUNT(*) AS c FROM jobs").fetchone()
        return int(row["c"])

    def is_first_run(self) -> bool:
        if self.job_count() == 0:
            return True
        seeded = self.get_meta("seeded")
        return seeded != "1"

    def get_meta(self, key: str, default: str | None = None) -> str | None:
        row = self._conn.execute(
            "SELECT value FROM meta WHERE key = ?", (key,)
        ).fetchone()
        if row is None:
            return default
        return row["value"]

    def set_meta(self, key: str, value: str) -> None:
        self._conn.execute(
            """
            INSERT INTO meta(key, value) VALUES(?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, value),
        )
        self._conn.commit()

    def upsert_job(
        self,
        *,
        url: str,
        title: str,
        snippet: str,
        score: int,
        bucket: str,
        age: str = "",
        matched: str = "",
        mark_notified: bool | None = None,
    ) -> JobRow | None:
        """Insert or refresh a job. Returns JobRow if newly inserted, else None."""
        canonical = normalize_url(url)
        if not canonical:
            return None

        now = datetime.now(timezone.utc).isoformat()
        existing = self._conn.execute(
            "SELECT * FROM jobs WHERE url = ?", (canonical,)
        ).fetchone()

        source = source_from_url(canonical)
        if existing is None:
            notified = 1 if mark_notified else 0
            self._conn.execute(
                """
                INSERT INTO jobs(
                    url, title, snippet, source, score, bucket, age, matched,
                    first_seen, last_seen, notified
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    canonical,
                    title or "(untitled)",
                    snippet or "",
                    source,
                    score,
                    bucket,
                    age or "",
                    matched or "",
                    now,
                    now,
                    notified,
                ),
            )
            self._conn.commit()
            return JobRow(
                url=canonical,
                title=title or "(untitled)",
                snippet=snippet or "",
                source=source,
                score=score,
                bucket=bucket,
                age=age or "",
                matched=matched or "",
                first_seen=now,
                last_seen=now,
                notified=notified,
                is_new=True,
            )

        self._conn.execute(
            """
            UPDATE jobs
            SET title = ?,
                snippet = ?,
                source = ?,
                score = ?,
                bucket = ?,
                age = ?,
                matched = ?,
                last_seen = ?
            WHERE url = ?
            """,
            (
                title or existing["title"],
                snippet or existing["snippet"],
                source,
                score,
                bucket,
                age or existing["age"],
                matched or existing["matched"],
                now,
                canonical,
            ),
        )
        self._conn.commit()
        return None

    def mark_notified(self, urls: list[str]) -> None:
        if not urls:
            return
        now_urls = [normalize_url(u) for u in urls]
        self._conn.executemany(
            "UPDATE jobs SET notified = 1 WHERE url = ?",
            [(u,) for u in now_urls],
        )
        self._conn.commit()

    def list_jobs(
        self,
        *,
        buckets: list[str] | None = None,
        min_score: int | None = None,
        limit: int | None = None,
    ) -> list[JobRow]:
        clauses: list[str] = []
        params: list[Any] = []
        if buckets:
            placeholders = ",".join("?" for _ in buckets)
            clauses.append(f"bucket IN ({placeholders})")
            params.extend(buckets)
        if min_score is not None:
            clauses.append("score >= ?")
            params.append(min_score)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = f"""
            SELECT * FROM jobs
            {where}
            ORDER BY
                CASE bucket WHEN 'GREEN' THEN 0 WHEN 'YELLOW' THEN 1 ELSE 2 END,
                score DESC,
                first_seen DESC
        """
        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)
        rows = self._conn.execute(sql, params).fetchall()
        return [self._to_job(r, is_new=False) for r in rows]

    @staticmethod
    def _to_job(row: sqlite3.Row, *, is_new: bool) -> JobRow:
        return JobRow(
            url=row["url"],
            title=row["title"],
            snippet=row["snippet"],
            source=row["source"],
            score=int(row["score"]),
            bucket=row["bucket"],
            age=row["age"],
            matched=row["matched"],
            first_seen=row["first_seen"],
            last_seen=row["last_seen"],
            notified=int(row["notified"]),
            is_new=is_new,
        )
