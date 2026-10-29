"""GoodWork.ca RSS fetcher — environmental / sustainability / climate jobs."""

from __future__ import annotations

import logging
import re
from datetime import datetime
from email.utils import parsedate_to_datetime

import feedparser

from ..config import UserConfig
from ..models import JobPosting


log = logging.getLogger("jobhunt.fetch.goodwork")


FEED = "https://www.goodwork.ca/rss/"


class GoodWorkFetcher:
    name = "goodwork"

    def fetch(self, cfg: UserConfig) -> list[JobPosting]:
        try:
            feed = feedparser.parse(FEED)
        except Exception as e:
            log.warning("goodwork parse failed: %s", e)
            return []

        out: list[JobPosting] = []
        for entry in feed.entries:
            title_full = (entry.get("title") or "").strip()
            if not title_full:
                continue
            # Format: "Role, full-time, Org, Location"
            title, org, location = _split(title_full)
            link = entry.get("link") or entry.get("guid") or ""
            posted_at = None
            if entry.get("published"):
                try:
                    posted_at = parsedate_to_datetime(entry.published)
                except Exception:
                    posted_at = None
            out.append(JobPosting(
                source="goodwork",
                source_id=link or title_full[:120],
                title=title,
                org=org,
                location=location,
                url=link,
                description=(entry.get("summary") or title_full).strip(),
                posted_at=posted_at,
                sector="nonprofit",
                tags=["environment", "climate"],
            ))
        log.info("goodwork: %d postings", len(out))
        return out


def _split(title_full: str) -> tuple[str, str, str]:
    # Try to pull the trailing location (last comma-separated piece that
    # looks like a Canadian place: contains "BC", "ON", etc. or "Canada" or
    # "remote").
    parts = [p.strip() for p in title_full.split(",")]
    if len(parts) < 2:
        return (title_full, "", "")
    loc_hints = re.compile(r"\b(BC|AB|SK|MB|ON|QC|NB|NS|PE|NL|YT|NT|NU|Canada|Remote|Vancouver|Toronto|Ottawa|Montreal|Calgary|Winnipeg)\b", re.I)
    location = ""
    for i in range(len(parts) - 1, -1, -1):
        if loc_hints.search(parts[i]):
            location = ", ".join(parts[i:])
            parts = parts[:i]
            break
    # Remove trailing "full-time"/"part-time"/employment-type parts and merge
    # the remaining "role, org" split.
    emp_type = re.compile(r"^(full|part)[- ]?time\b|^contract\b|^permanent\b|^summer\b", re.I)
    cleaned = [p for p in parts if p and not emp_type.match(p)]
    if len(cleaned) == 0:
        return (title_full, "", location)
    role = cleaned[0]
    org = ", ".join(cleaned[1:]) if len(cleaned) > 1 else ""
    return (role, org, location)
