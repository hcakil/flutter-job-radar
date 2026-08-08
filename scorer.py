"""Keyword scoring and GREEN/YELLOW/RED eligibility buckets."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable


SCORE_THRESHOLD = 5

# Flutter-the-framework must appear in title or body; otherwise hard reject.
NO_FLUTTER_PENALTY = -20
COMPANY_NOISE_PENALTY = -20
NON_ENG_ROLE_PENALTY = -15


@dataclass(frozen=True)
class ScoreResult:
    score: int
    bucket: str  # GREEN | YELLOW | RED
    matched: tuple[str, ...]
    flutter_relevant: bool = False


def _contains(text: str, patterns: Iterable[str]) -> list[str]:
    hits: list[str] = []
    for pattern in patterns:
        if re.search(pattern, text, flags=re.IGNORECASE):
            hits.append(pattern)
    return hits


def _is_flutter_company_noise(title: str, full: str) -> bool:
    """Flutter Entertainment / Flutter CEE employer, not the SDK."""
    return bool(
        _contains(
            full,
            [
                r"flutter entertainment",
                r"flutter central",
                r"flutter cee",
                r"flutter group",
                r"flutter\.com",
                r"igaming",
                r"\bpaddy\s?power\b",
                r"\bfan\s?duel\b",
                r"\bsisy\b",
            ],
        )
        or re.search(
            r"^flutter\b.+\bhiring\b",
            title,
            flags=re.IGNORECASE,
        )
        or re.search(
            r"\bat flutter\b(?!\s*(developer|engineer|dev|sdk))",
            full,
            flags=re.IGNORECASE,
        )
    )


def _has_flutter_tech_signal(title: str, full: str) -> bool:
    """True when Flutter/Dart refers to the mobile framework role."""
    if _is_flutter_company_noise(title, full):
        return False

    title_role = bool(
        re.search(
            r"""
            \bflutter\s*(/|\+|and)?\s*dart\b
            |\bdart\s*(/|\+|and)?\s*flutter\b
            |\bflutter\s+(developer|engineer|dev|programmer|mobile)
            |\b(developer|engineer|dev|programmer)\s+(?:[\w./+\-]+\s+){0,3}flutter\b
            |\b(senior|lead|mid|staff|principal)?\s*flutter\s+(developer|engineer|dev)
            |\bmobile\s+(?:app\s+)?(?:developer|engineer).{0,40}\bflutter\b
            |\bflutter\b.{0,40}\bmobile\s+(?:app\s+)?(?:developer|engineer)
            """,
            title,
            flags=re.IGNORECASE | re.VERBOSE,
        )
    )
    if title_role:
        return True

    has_flutter = bool(re.search(r"\bflutter\b", full, flags=re.IGNORECASE))
    if not has_flutter:
        return False

    # Eng title + Flutter listed in stack (e.g. "Python, Go, and Flutter")
    eng_title = bool(
        re.search(
            r"\b(software|mobile|flutter|forward.?deployed|full.?stack)\b.{0,40}\b(engineer|developer|dev)\b"
            r"|\b(engineer|developer)\b",
            title,
            flags=re.IGNORECASE,
        )
    )
    if eng_title and not _is_non_engineering_role(title, ""):
        if _contains(
            full,
            [
                r"\bdart\b",
                r"\bflutter\s+sdk\b",
                r"react\s*native\s+or\s+flutter",
                r"flutter\s+or\s+react\s*native",
                r"\b(python|go|golang|django).{0,40}\bflutter\b",
                r"\bflutter\b.{0,40}\b(python|go|golang|django)\b",
                r"across.{0,40}\bflutter\b",
                r"using.{0,40}\bflutter\b",
                r"\bmobile\s+(app\s+)?(developer|engineer)\b",
                r"\b(ios|android).{0,30}\bflutter\b",
                r"\bflutter\b.{0,30}\b(ios|android)\b",
                r"\bbloc\b",
                r"\bcubit\b",
                r"\briverpod\b",
                r"\bwidget\b",
            ],
        ):
            return True

    # Body: Flutter + clear mobile/SDK context
    body_tech = bool(
        _contains(
            full,
            [
                r"\bdart\b",
                r"\bflutter\s+sdk\b",
                r"\bbloc\b",
                r"\bcubit\b",
                r"\bprovider\b",
                r"\briverpod\b",
                r"\bwidget\b",
                r"react\s*native\s+or\s+flutter",
                r"flutter\s+or\s+react\s*native",
                r"\bmobile\s+(app\s+)?(developer|engineer)\b",
                r"\b(ios|android).{0,30}\bflutter\b",
                r"\bflutter\b.{0,30}\b(ios|android)\b",
            ],
        )
    )
    if body_tech:
        return True

    if re.search(r"\bflutter\b", title, flags=re.IGNORECASE) and _contains(
        title,
        [
            r"\bdeveloper\b",
            r"\bengineer\b",
            r"\bsoftware\b",
            r"\bmobile\b",
            r"\bprogrammer\b",
            r"\bdev\b",
        ],
    ):
        if _is_non_engineering_role(title, ""):
            return False
        return True

    return False


def _is_non_engineering_role(title: str, full: str) -> bool:
    return bool(
        _contains(
            f"{title} {full}",
            [
                r"talent acquisition",
                r"\brecruiter\b",
                r"people partner",
                r"human resources",
                r"\bhr\b",
                r"business development",
                r"account director",
                r"account manager",
                r"sales director",
                r"sales manager",
                r"media buyer",
                r"customer success",
                r"\bmarketing\b",
            ],
        )
    )


def score_job(
    title: str,
    description: str,
    extra_snippets: list[str] | None = None,
    url: str = "",
) -> ScoreResult:
    """Score a job listing from Brave title/snippet fields."""
    snippets = " ".join(extra_snippets or [])
    body = f"{description} {snippets}".strip()
    full = f"{title} {body} {url}".lower()
    title_l = title.lower()
    url_l = (url or "").lower()

    score = 0
    matched: list[str] = []

    flutter_in_title = bool(re.search(r"\bflutter\b", title_l))
    flutter_in_body = bool(re.search(r"\bflutter\b", body.lower()))
    flutter_anywhere = flutter_in_title or flutter_in_body
    flutter_relevant = _has_flutter_tech_signal(title, full)

    # Hard gate: Flutter (or clear Flutter tech role) must appear
    if not flutter_anywhere:
        score += NO_FLUTTER_PENALTY
        matched.append("no-flutter-in-title/body:-20")
    elif not flutter_relevant:
        score += NO_FLUTTER_PENALTY
        matched.append("flutter-not-tech-role:-20")
    elif flutter_in_title:
        score += 5
        matched.append("flutter@title:+5")
    else:
        score += 3
        matched.append("flutter@body:+3")

    if _is_flutter_company_noise(title, full):
        score += COMPANY_NOISE_PENALTY
        matched.append("flutter-company-noise:-20")
        flutter_relevant = False

    if _is_non_engineering_role(title, full):
        score += NON_ENG_ROLE_PENALTY
        matched.append("non-eng-role:-15")
        flutter_relevant = False

    # Local India / LatAm boards without EMEA/worldwide signal → usually wrong market
    geo_positive = bool(
        _contains(
            full,
            [
                r"\bworldwide\b",
                r"\banywhere\b",
                r"work from anywhere",
                r"\bemea\b",
                r"\bturkey\b",
                r"türkiye",
                r"turkiye",
                r"\beurope\b",
            ],
        )
    )
    geo_mismatch = bool(
        _contains(
            full,
            [
                r"\bindore\b",
                r"\bbengaluru\b",
                r"\bbangalore\b",
                r"madhya pradesh",
                r"greater bengaluru",
                r"latin america",
            ],
        )
        or "in.linkedin.com" in url_l
        or "in.linkedin.com" in full
    )
    if geo_mismatch and not geo_positive:
        score -= 10
        matched.append("geo-mismatch:-10")

    # Positive geo / engagement signals (only useful if Flutter-relevant)
    if _contains(full, [r"\bworldwide\b", r"\banywhere\b", r"work from anywhere"]):
        score += 4
        matched.append("worldwide/anywhere:+4")

    if _contains(full, [r"\bemea\b"]):
        score += 4
        matched.append("EMEA:+4")

    if _contains(full, [r"\bturkey\b", r"türkiye", r"turkiye"]):
        score += 3
        matched.append("Turkey:+3")

    if _contains(full, [r"\bcontractor\b", r"\bb2b\b", r"freelance", r"\bcontract\b"]):
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
            r"mobile (app )?developer",
            r"software engineer",
        ],
    ):
        score += 2
        matched.append("senior/lead/mobile:+2")

    if re.search(r"\bdart\b", full):
        score += 2
        matched.append("dart:+2")

    # Negative eligibility signals
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

    bucket = _bucket(full, score, flutter_relevant=flutter_relevant)
    return ScoreResult(
        score=score,
        bucket=bucket,
        matched=tuple(matched),
        flutter_relevant=flutter_relevant,
    )


def _bucket(full: str, score: int, *, flutter_relevant: bool) -> str:
    """Assign GREEN / YELLOW / RED for a Turkey-based remote seeker."""
    if not flutter_relevant or score < SCORE_THRESHOLD:
        return "RED"

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
            r"\bemea\b.*\b(contractor|b2b|freelance|contract)\b",
            r"\b(contractor|b2b|freelance|contract)\b.*\bemea\b",
        ],
    )
    if not green_signals and (
        _contains(full, [r"\bemea\b"])
        and _contains(full, [r"\bcontractor\b", r"\bb2b\b", r"freelance", r"\bcontract\b"])
    ):
        green_signals = ["emea+contractor"]

    if green_signals:
        return "GREEN"
    return "YELLOW"


def is_notifiable(result: ScoreResult) -> bool:
    return (
        result.flutter_relevant
        and result.score >= SCORE_THRESHOLD
        and result.bucket in {"GREEN", "YELLOW"}
    )
