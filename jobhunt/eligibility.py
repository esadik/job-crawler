"""Lightweight citizenship/clearance detector for job descriptions.

v0.1 is intentionally rule-based so it's fast and inspectable. We err on the
side of surfacing the triggering sentence so the user can judge borderline
cases.
"""

from __future__ import annotations

import re

from .models import (
    ELIGIBILITY_OPEN,
    ELIGIBILITY_RESTRICTED,
    ELIGIBILITY_UNKNOWN,
    ELIGIBILITY_VERIFY,
)


RESTRICTED_PATTERNS = [
    r"must be a canadian citizen",
    r"canadian citizens? only",
    r"open (only )?to canadian citizens",
    r"restricted to canadian citizens",
    r"preference (is )?given to canadian citizens and permanent residents",
    r"canadian citizens and permanent residents only",
    r"must be a permanent resident",
    r"must hold (an )?enhanced reliability",
    r"must (be able to )?obtain (a )?(secret|top secret) (security )?clearance",
    r"security clearance.{0,30}(required|is required|must)",
    r"citizenship.{0,20}required",
    r"not eligible.{0,40}work permit",
    r"work permit holders are not eligible",
]

VERIFY_PATTERNS = [
    r"preference (will be )?given to canadian citizens",
    r"preference.{0,30}permanent residents",
    r"security clearance",            # mentioned but not clearly required
    r"reliability (status|screening)",
    r"background check",
    r"citizenship status",
]

OPEN_PATTERNS = [
    r"legally entitled to work in canada",
    r"legally authorized to work in canada",
    r"authorized to work in canada",
    r"eligible to work in canada",
    r"must have the right to work in canada",
    r"open work permit holders? (are )?welcome",
    r"welcome.{0,20}work permit",
    r"all applicants.{0,30}eligible to work",
]


_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")


def _find(patterns: list[str], text_lower: str) -> tuple[str, str] | None:
    for pat in patterns:
        m = re.search(pat, text_lower)
        if m:
            # Try to grab the containing sentence for evidence.
            start = text_lower.rfind(".", 0, m.start()) + 1
            end = text_lower.find(".", m.end())
            if end == -1:
                end = min(len(text_lower), m.end() + 160)
            sentence = text_lower[start:end].strip().strip(". ")
            return (pat, sentence[:280])
    return None


def classify(description: str, sector: str = "") -> tuple[str, str]:
    """Return (eligibility_level, evidence_sentence)."""
    if not description:
        # Default per sector when we have no text at all.
        if sector == "government":
            return (ELIGIBILITY_VERIFY, "")
        if sector in ("nonprofit", "private"):
            return (ELIGIBILITY_OPEN, "")
        return (ELIGIBILITY_UNKNOWN, "")

    text = description.lower()

    hit = _find(RESTRICTED_PATTERNS, text)
    if hit:
        return (ELIGIBILITY_RESTRICTED, hit[1])

    hit = _find(OPEN_PATTERNS, text)
    if hit:
        return (ELIGIBILITY_OPEN, hit[1])

    hit = _find(VERIFY_PATTERNS, text)
    if hit:
        return (ELIGIBILITY_VERIFY, hit[1])

    # No signal — fall back to sector default.
    if sector == "government":
        return (ELIGIBILITY_VERIFY, "")
    if sector in ("nonprofit", "private"):
        return (ELIGIBILITY_OPEN, "")
    return (ELIGIBILITY_UNKNOWN, "")


ELIGIBILITY_LABEL = {
    ELIGIBILITY_OPEN: "🟢 Open",
    ELIGIBILITY_VERIFY: "🟡 Verify",
    ELIGIBILITY_RESTRICTED: "🔴 Restricted",
    ELIGIBILITY_UNKNOWN: "❔ Unknown",
}
