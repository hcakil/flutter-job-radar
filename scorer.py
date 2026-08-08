"""Keyword scoring and GREEN/YELLOW/RED eligibility buckets."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable


SCORE_THRESHOLD = 5


@dataclass(frozen=True)
class ScoreResult:
    score: int
    bucket: str  # GREEN | YELLOW | RED
    matched: tuple[str, ...]


def _contains(text: str, patterns: Iterable[str]) -> list[str]:
    hits: list[str] = []
    for pattern in patterns:
        if re.search(pattern, text, flags=re.IGNORECASE):
            hits.append(pattern)
    return hits


def score_job(title: str, description: str, extra_snippets: list[str] | None = None) -> ScoreResult:
    """Score a job listing from Brave title/snippet fields."""
    snippets = " ".join(extra_snippets or [])
    body = f"{description} {snippets}".strip()
    full = f"{title} {body}".lower()
    title_l = title.lower()

    score = 0
    matched: list[str] = []

    # Positive signals
    if re.search(r"\bflutter\b", title_l):
        score += 5
        matched.append("flutter@title:+5")
    elif re.search(r"\bflutter\b", full):
        score += 3
        matched.append("flutter@body:+3")

    if _contains(full, [r"\bworldwide\b", r"\banywhere\b", r"work from anywhere"]):
        score += 4
        matched.append("worldwide/anywhere:+4")

    if _contains(full, [r"\bemea\b"]):
        score += 4
        matched.append("EMEA:+4")

    if _contains(full, [r"\bturkey\b", r"türkiye", r"turkiye"]):
        score += 3
        matched.append("Turkey:+3")

    if _contains(full, [r"\bcontractor\b", r"\bb2b\b", r"freelance"]):
        score += 3
        matched.append("contractor/B2B:+3")

    if _contains(full, [r"\bremote\b", r"work from home", r"\bwfh\b"]):
        score += 2
        matched.append("remote:+2")

    if _contains(
        full,
        [
            r"\bsenior\b",
            r"\blead\b",
            r"\bprincipal\b",
            r"product engineer",
            r"mobile engineer",
        ],
    ):
        score += 2
        matched.append("senior/lead/mobile:+2")

    if re.search(r"\bdart\b", full):
        score += 1
        matched.append("dart:+1")

    # Negative signals
    if _contains(
        full,
        [
            r"us residents? only",
            r"u\.?s\.? (citizens?|residents?) only",
            r"must be (a )?us (citizen|resident)",
            r"authorized to work in the (united states|u\.?s\.?a?\.?)",
            r"must be authorized to work in (the )?u\.?s",
            r"eligibility to work in the united states",
        ],
    ):
        score -= 10
        matched.append("US-only:-10")

    if _contains(
        full,
        [
            r"eu citizens? only",
            r"european (union )?citizens? only",
            r"must be (an )?eu citizen",
            r"right to work in the (eu|eea|european union)",
        ],
    ):
        score -= 8
        matched.append("EU-only:-8")

    if _contains(
        full,
        [
            r"\bonsite\b",
            r"\bon-site\b",
            r"in[- ]office only",
            r"must (be|work) (on[- ]site|in[- ]office)",
            r"no remote",
            r"not remote",
        ],
    ):
        score -= 8
        matched.append("onsite:-8")

    if _contains(full, [r"\bintern(ship)?\b", r"\bjunior\b", r"\bentry[- ]level\b"]):
        score -= 5
        matched.append("junior/intern:-5")

    if _contains(
        full,
        [
            r"local employment required",
            r"must (live|reside|be based) in",
            r"relocation required",
        ],
    ):
        score -= 6
        matched.append("local-required:-6")

    bucket = _bucket(full, score)
    return ScoreResult(score=score, bucket=bucket, matched=tuple(matched))


def _bucket(full: str, score: int) -> str:
    """Assign GREEN / YELLOW / RED for a Turkey-based remote seeker."""
    us_block = bool(
        _contains(
            full,
            [
                r"us residents? only",
                r"u\.?s\.? (citizens?|residents?) only",
                r"must be (a )?us (citizen|resident)",
                r"authorized to work in the (united states|u\.?s\.?a?\.?)",
                r"must be authorized to work in (the )?u\.?s",
                r"eligibility to work in the united states",
            ],
        )
    )
    eu_block = bool(
        _contains(
            full,
            [
                r"eu citizens? only",
                r"european (union )?citizens? only",
                r"must be (an )?eu citizen",
                r"right to work in the (eu|eea|european union)",
            ],
        )
    )
    onsite = bool(
        _contains(
            full,
            [
                r"\bonsite\b",
                r"\bon-site\b",
                r"in[- ]office only",
                r"must (be|work) (on[- ]site|in[- ]office)",
                r"no remote",
                r"not remote",
            ],
        )
    )
    local_req = bool(
        _contains(
            full,
            [
                r"local employment required",
                r"relocation required",
            ],
        )
    )

    if us_block or eu_block or onsite or local_req:
        return "RED"

    green_signals = _contains(
        full,
        [
            r"\bworldwide\b",
            r"\banywhere\b",
            r"work from anywhere",
            r"\bturkey\b",
            r"türkiye",
            r"turkiye",
            r"\bemea\b.*\b(contractor|b2b|freelance)\b",
            r"\b(contractor|b2b|freelance)\b.*\bemea\b",
        ],
    )
    # EMEA alone + contractor somewhere in text
    if not green_signals and (
        _contains(full, [r"\bemea\b"])
        and _contains(full, [r"\bcontractor\b", r"\bb2b\b", r"freelance"])
    ):
        green_signals = ["emea+contractor"]

    if green_signals and score >= SCORE_THRESHOLD:
        return "GREEN"

    if score >= SCORE_THRESHOLD:
        return "YELLOW"

    return "RED"


def is_notifiable(result: ScoreResult) -> bool:
    return result.score >= SCORE_THRESHOLD and result.bucket in {"GREEN", "YELLOW"}
