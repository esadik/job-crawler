"""SQLite layer. One file, two tables (``jobs``, ``apps``), no ORM."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterator

from .config import DATA_DIR
from .models import (
    ALL_STATUSES,
    STATUS_NEW,
    JobPosting,
    StoredJob,
)


DB_PATH = DATA_DIR / "jobhunt.db"


SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    source            TEXT NOT NULL,
    source_id         TEXT NOT NULL,
    title             TEXT NOT NULL,
    org               TEXT NOT NULL,
    location          TEXT,
    url               TEXT,
    description       TEXT,
    posted_at         TEXT,
    salary            TEXT,
    sector            TEXT,
    tags_json         TEXT,
    raw_json          TEXT,
    fetched_at        TEXT NOT NULL,
    match_score       INTEGER DEFAULT 0,
    matched_titles    TEXT,
    matched_themes    TEXT,
    eligibility       TEXT,
    eligibility_evidence TEXT,
    status            TEXT NOT NULL DEFAULT 'new',
    notes             TEXT DEFAULT '',
    applied_at        TEXT,
    tailored_resume_path TEXT DEFAULT '',
    UNIQUE(source, source_id)
);

CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_match_score ON jobs(match_score);
CREATE INDEX IF NOT EXISTS idx_jobs_posted_at ON jobs(posted_at);
"""


def _dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _row_to_job(row: sqlite3.Row) -> StoredJob:
    return StoredJob(
        id=row["id"],
        source=row["source"],
        source_id=row["source_id"],
        title=row["title"],
        org=row["org"],
        location=row["location"] or "",
        url=row["url"] or "",
        description=row["description"] or "",
        posted_at=_dt(row["posted_at"]),
        salary=row["salary"] or "",
        sector=row["sector"] or "",
        tags=json.loads(row["tags_json"] or "[]"),
        raw=json.loads(row["raw_json"] or "{}"),
        fetched_at=_dt(row["fetched_at"]),
        match_score=row["match_score"] or 0,
        matched_titles=json.loads(row["matched_titles"] or "[]"),
        matched_themes=json.loads(row["matched_themes"] or "[]"),
        eligibility=row["eligibility"] or "unknown",
        eligibility_evidence=row["eligibility_evidence"] or "",
        status=row["status"] or STATUS_NEW,
        notes=row["notes"] or "",
        applied_at=_dt(row["applied_at"]),
        tailored_resume_path=row["tailored_resume_path"] or "",
    )


@contextmanager
def connect(path: Path | None = None) -> Iterator[sqlite3.Connection]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path or DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db(path: Path | None = None) -> None:
    with connect(path) as conn:
        conn.executescript(SCHEMA)


def upsert_jobs(jobs: list[JobPosting]) -> tuple[int, int]:
    """Insert new postings; skip ones already seen. Returns (new, duplicates)."""
    if not jobs:
        return (0, 0)
    now = datetime.utcnow().isoformat(timespec="seconds")
    new = 0
    dup = 0
    with connect() as conn:
        for j in jobs:
            try:
                conn.execute(
                    """
                    INSERT INTO jobs (
                        source, source_id, title, org, location, url, description,
                        posted_at, salary, sector, tags_json, raw_json, fetched_at,
                        match_score, matched_titles, matched_themes,
                        eligibility, eligibility_evidence
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        j.source,
                        j.source_id,
                        j.title,
                        j.org,
                        j.location,
                        j.url,
                        j.description,
                        j.posted_at.isoformat() if j.posted_at else None,
                        j.salary,
                        j.sector,
                        json.dumps(j.tags),
                        json.dumps(j.raw, default=str),
                        now,
                        j.match_score,
                        json.dumps(j.matched_titles),
                        json.dumps(j.matched_themes),
                        j.eligibility,
                        j.eligibility_evidence,
                    ),
                )
                new += 1
            except sqlite3.IntegrityError:
                dup += 1
    return (new, dup)


def list_jobs(
    *,
    statuses: list[str] | None = None,
    min_score: int | None = None,
    eligibility: list[str] | None = None,
    sources: list[str] | None = None,
    sector: str | None = None,
    search: str | None = None,
    limit: int = 500,
) -> list[StoredJob]:
    where = []
    params: list = []
    if statuses:
        where.append(f"status IN ({','.join(['?'] * len(statuses))})")
        params.extend(statuses)
    if min_score is not None:
        where.append("match_score >= ?")
        params.append(min_score)
    if eligibility:
        where.append(f"eligibility IN ({','.join(['?'] * len(eligibility))})")
        params.extend(eligibility)
    if sources:
        where.append(f"source IN ({','.join(['?'] * len(sources))})")
        params.extend(sources)
    if sector:
        where.append("sector = ?")
        params.append(sector)
    if search:
        where.append("(title LIKE ? OR org LIKE ? OR description LIKE ?)")
        s = f"%{search}%"
        params.extend([s, s, s])
    sql = "SELECT * FROM jobs"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY match_score DESC, COALESCE(posted_at, fetched_at) DESC LIMIT ?"
    params.append(limit)
    with connect() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [_row_to_job(r) for r in rows]


def get_job(job_id: int) -> StoredJob | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    return _row_to_job(row) if row else None


def set_status(job_id: int, status: str, notes: str | None = None) -> None:
    if status not in ALL_STATUSES:
        raise ValueError(f"Unknown status: {status}")
    now = datetime.utcnow().isoformat(timespec="seconds")
    with connect() as conn:
        if status == "applied":
            conn.execute(
                "UPDATE jobs SET status=?, applied_at=COALESCE(applied_at,?), notes=COALESCE(?, notes) WHERE id=?",
                (status, now, notes, job_id),
            )
        else:
            conn.execute(
                "UPDATE jobs SET status=?, notes=COALESCE(?, notes) WHERE id=?",
                (status, notes, job_id),
            )


def set_tailored_path(job_id: int, path: str) -> None:
    with connect() as conn:
        conn.execute("UPDATE jobs SET tailored_resume_path=? WHERE id=?", (path, job_id))


def counts_by_status() -> dict[str, int]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT status, COUNT(*) AS n FROM jobs GROUP BY status"
        ).fetchall()
    return {r["status"]: r["n"] for r in rows}


def recent_summary(hours: int = 24, strong_threshold: int = 40) -> dict[str, int]:
    cutoff = datetime.utcnow().timestamp() - hours * 3600
    with connect() as conn:
        rows = conn.execute("SELECT fetched_at, match_score FROM jobs").fetchall()
    fresh = [r for r in rows if r["fetched_at"] and datetime.fromisoformat(r["fetched_at"]).timestamp() >= cutoff]
    strong = [r for r in fresh if (r["match_score"] or 0) >= strong_threshold]
    return {"new": len(fresh), "strong": len(strong), "total": len(rows)}
