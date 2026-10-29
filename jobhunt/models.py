"""Shared dataclasses used across fetchers, DB layer, and UI."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


# One of: 🟢 open | 🟡 verify | 🔴 restricted | ❔ unknown
ELIGIBILITY_OPEN = "open"
ELIGIBILITY_VERIFY = "verify"
ELIGIBILITY_RESTRICTED = "restricted"
ELIGIBILITY_UNKNOWN = "unknown"

# Application pipeline statuses.
STATUS_NEW = "new"
STATUS_INTERESTED = "interested"
STATUS_APPLIED = "applied"
STATUS_INTERVIEW = "interview"
STATUS_OFFER = "offer"
STATUS_REJECTED = "rejected"
STATUS_HIDDEN = "hidden"

ALL_STATUSES = [
    STATUS_NEW,
    STATUS_INTERESTED,
    STATUS_APPLIED,
    STATUS_INTERVIEW,
    STATUS_OFFER,
    STATUS_REJECTED,
    STATUS_HIDDEN,
]


@dataclass
class JobPosting:
    """A raw posting as returned by a fetcher. ``id`` is assigned by the DB."""

    source: str
    source_id: str                     # stable id within the source (used for dedupe)
    title: str
    org: str
    location: str = ""
    url: str = ""
    description: str = ""
    posted_at: datetime | None = None
    salary: str = ""
    sector: str = ""                    # "government" | "nonprofit" | "private" | ""
    tags: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)

    # Derived (filled in by scoring/eligibility):
    match_score: int = 0
    matched_titles: list[str] = field(default_factory=list)
    matched_themes: list[str] = field(default_factory=list)
    eligibility: str = ELIGIBILITY_UNKNOWN
    eligibility_evidence: str = ""


@dataclass
class StoredJob(JobPosting):
    """Posting + DB-managed fields."""

    id: int = 0
    fetched_at: datetime | None = None
    status: str = STATUS_NEW
    notes: str = ""
    applied_at: datetime | None = None
    tailored_resume_path: str = ""
