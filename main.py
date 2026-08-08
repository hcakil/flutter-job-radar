#!/usr/bin/env python3
"""Flutter Job Radar V1 — Brave Search → score → SQLite → Telegram/HTML."""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from brave_client import BraveClient
from notify import format_digest, send_simple_message, send_telegram
from queries import QUERIES
from render import render_html
from scorer import SCORE_THRESHOLD, is_notifiable, score_job
from store import JobRow, JobStore

ROOT = Path(__file__).resolve().parent
DEFAULT_DB = ROOT / "data" / "jobs.db"
DEFAULT_HTML = ROOT / "output.html"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("job_radar")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Flutter Job Radar V1")
    parser.add_argument(
        "--freshness",
        choices=["pd", "pw", "pm", "py", "auto"],
        default="auto",
        help="Brave freshness filter (default: auto = pm first run, else pw)",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=DEFAULT_DB,
        help="SQLite database path",
    )
    parser.add_argument(
        "--html",
        type=Path,
        default=DEFAULT_HTML,
        help="HTML output path",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Skip Telegram; still write DB and HTML",
    )
    parser.add_argument(
        "--notify-seed",
        action="store_true",
        help="On first/backfill run, also send full digest (default: silent seed)",
    )
    return parser.parse_args()


def resolve_freshness(store: JobStore, requested: str) -> tuple[str, bool]:
    """Return (freshness, is_backfill)."""
    first = store.is_first_run()
    if requested != "auto":
        return requested, first and requested == "pm"
    if first:
        return "pm", True
    return "pw", False


def build_snippet(description: str, extras: list[str]) -> str:
    parts = [description] + list(extras or [])
    text = " ".join(p for p in parts if p).strip()
    if len(text) > 400:
        return text[:397] + "…"
    return text


def run() -> int:
    load_dotenv(ROOT / ".env")
    args = parse_args()

    api_key = os.getenv("BRAVE_API_KEY", "").strip()
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()

    if not api_key:
        logger.error("BRAVE_API_KEY missing. Copy .env.example → .env")
        return 1

    store = JobStore(args.db)
    try:
        freshness, is_backfill = resolve_freshness(store, args.freshness)
        logger.info(
            "Run start · freshness=%s · backfill=%s · jobs_in_db=%d",
            freshness,
            is_backfill,
            store.job_count(),
        )

        client = BraveClient(api_key)
        new_rows: list[JobRow] = []
        filtered_new = 0
        seen_urls: set[str] = set()
        query_errors = 0

        for query in QUERIES:
            try:
                results = client.search(query, freshness=freshness, count=20)
            except Exception:
                query_errors += 1
                logger.exception("Query failed: %s", query)
                continue

            logger.info("Query %r → %d results", query, len(results))
            for raw in results:
                url = raw.get("url") or ""
                if not url or url in seen_urls:
                    continue
                seen_urls.add(url)

                scored = score_job(
                    raw.get("title") or "",
                    raw.get("description") or "",
                    raw.get("extra_snippets") or [],
                )
                snippet = build_snippet(
                    raw.get("description") or "",
                    raw.get("extra_snippets") or [],
                )
                # On backfill, mark as already notified so we don't flood later
                mark_notified = is_backfill and not args.notify_seed

                row = store.upsert_job(
                    url=url,
                    title=raw.get("title") or "",
                    snippet=snippet,
                    score=scored.score,
                    bucket=scored.bucket,
                    age=raw.get("age") or "",
                    matched=", ".join(scored.matched),
                    mark_notified=mark_notified,
                )
                if row is None:
                    continue

                if is_notifiable(scored):
                    new_rows.append(row)
                else:
                    filtered_new += 1

        # Prefer GREEN then YELLOW, higher score first
        new_rows.sort(key=lambda j: (0 if j.bucket == "GREEN" else 1, -j.score))

        now = datetime.now(timezone.utc).isoformat()
        store.set_meta("last_run_at", now)
        store.set_meta("last_freshness", freshness)
        if is_backfill:
            store.set_meta("seeded", "1")

        report_jobs = store.list_jobs(
            buckets=["GREEN", "YELLOW"],
            min_score=SCORE_THRESHOLD,
        )
        render_html(
            report_jobs,
            output_path=args.html,
            run_note=f"freshness={freshness}; new={len(new_rows)}; filtered_new={filtered_new}",
        )
        logger.info("Wrote HTML → %s (%d jobs)", args.html, len(report_jobs))

        if args.dry_run:
            logger.info(
                "Dry-run: would notify %d jobs (backfill=%s)",
                len(new_rows),
                is_backfill,
            )
            _print_summary(new_rows, filtered_new, is_backfill)
            return 0 if query_errors == 0 else 2

        if not bot_token or not chat_id:
            logger.warning("Telegram secrets missing; skipping notify")
            return 0 if query_errors == 0 else 2

        if is_backfill and not args.notify_seed:
            send_simple_message(
                bot_token=bot_token,
                chat_id=chat_id,
                text=(
                    f"<b>Flutter Job Radar</b> seeded quietly\n"
                    f"Freshness: <code>{freshness}</code>\n"
                    f"Stored: {store.job_count()} jobs\n"
                    f"Would-be matches: {len(new_rows)} "
                    f"(🟢{sum(1 for j in new_rows if j.bucket == 'GREEN')} "
                    f"🟡{sum(1 for j in new_rows if j.bucket == 'YELLOW')})\n"
                    f"Filtered: {filtered_new}\n"
                    f"Daily digests will only include <b>new</b> listings."
                ),
            )
            # Ensure seeded rows won't re-notify
            store.mark_notified([j.url for j in new_rows])
            logger.info("Backfill complete — silent seed notification sent")
            return 0 if query_errors == 0 else 2

        if not new_rows:
            send_simple_message(
                bot_token=bot_token,
                chat_id=chat_id,
                text=(
                    f"<b>Flutter Job Radar</b> — no new matches "
                    f"(freshness=<code>{freshness}</code>, "
                    f"filtered={filtered_new})."
                ),
            )
            logger.info("No new notifiable jobs")
            return 0 if query_errors == 0 else 2

        messages = format_digest(new_rows, filtered_count=filtered_new)
        send_telegram(bot_token=bot_token, chat_id=chat_id, messages=messages)
        store.mark_notified([j.url for j in new_rows])
        logger.info("Notified %d new jobs", len(new_rows))
        return 0 if query_errors == 0 else 2
    finally:
        store.close()


def _print_summary(jobs: list[JobRow], filtered: int, backfill: bool) -> None:
    print("---")
    print(f"backfill={backfill} new_notifiable={len(jobs)} filtered_new={filtered}")
    for job in jobs[:20]:
        print(f"  [{job.bucket} {job.score}] {job.title} · {job.url}")


if __name__ == "__main__":
    sys.exit(run())
