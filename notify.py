"""Telegram digest notifications."""

from __future__ import annotations

import logging
from typing import Sequence

import httpx

from store import JobRow

logger = logging.getLogger(__name__)

TELEGRAM_MAX_LEN = 3900  # leave headroom under 4096
BUCKET_EMOJI = {"GREEN": "🟢", "YELLOW": "🟡", "RED": "🔴"}


def format_digest(
    jobs: Sequence[JobRow],
    *,
    filtered_count: int = 0,
    header_note: str | None = None,
) -> list[str]:
    """Build one or more Telegram messages for a digest."""
    green = sum(1 for j in jobs if j.bucket == "GREEN")
    yellow = sum(1 for j in jobs if j.bucket == "YELLOW")
    total = len(jobs)

    lines: list[str] = [
        f"<b>{total} new Flutter jobs</b> (🟢{green} 🟡{yellow}"
        + (f" · {filtered_count} filtered" if filtered_count else "")
        + ")",
    ]
    if header_note:
        lines.append(header_note)
    lines.append("")

    for job in sorted(
        jobs,
        key=lambda j: (0 if j.bucket == "GREEN" else 1, -j.score, j.title),
    ):
        emoji = BUCKET_EMOJI.get(job.bucket, "⚪")
        snippet = (job.snippet or "").replace("<", "&lt;").replace(">", "&gt;")
        if len(snippet) > 180:
            snippet = snippet[:177] + "…"
        title = job.title.replace("<", "&lt;").replace(">", "&gt;")
        meta_bits = [job.source]
        if job.age:
            meta_bits.append(job.age)
        lines.append(f"{emoji} <b>[{job.score}]</b> {title}")
        lines.append(" · ".join(meta_bits))
        if snippet:
            lines.append(snippet)
        lines.append(job.url)
        lines.append("")

    text = "\n".join(lines).strip()
    return _chunk_message(text)


def _chunk_message(text: str) -> list[str]:
    if len(text) <= TELEGRAM_MAX_LEN:
        return [text]
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    for block in text.split("\n\n"):
        block_len = len(block) + (2 if current else 0)
        if current and current_len + block_len > TELEGRAM_MAX_LEN:
            chunks.append("\n\n".join(current))
            current = [block]
            current_len = len(block)
        else:
            current.append(block)
            current_len += block_len
    if current:
        chunks.append("\n\n".join(current))
    return chunks


def send_telegram(
    *,
    bot_token: str,
    chat_id: str,
    messages: Sequence[str],
    timeout: float = 30.0,
) -> None:
    if not bot_token or not chat_id:
        raise ValueError("TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are required")
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    with httpx.Client(timeout=timeout) as client:
        for message in messages:
            response = client.post(
                url,
                json={
                    "chat_id": chat_id,
                    "text": message,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True,
                },
            )
            if response.status_code >= 400:
                logger.error("Telegram error: %s", response.text[:300])
                response.raise_for_status()
            logger.info("Telegram message sent (%d chars)", len(message))


def send_simple_message(*, bot_token: str, chat_id: str, text: str) -> None:
    send_telegram(bot_token=bot_token, chat_id=chat_id, messages=[text])
