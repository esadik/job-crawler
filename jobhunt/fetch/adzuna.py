"""Adzuna API fetcher (free tier). Requires ADZUNA_APP_ID + ADZUNA_APP_KEY.

Docs: https://developer.adzuna.com/overview — free tier gives you ~1k calls/mo
which is plenty for daily job hunting.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any

import httpx

from ..config import UserConfig
from ..models import JobPosting

from .base import DEFAULT_HEADERS, http_get


log = logging.getLogger("jobhunt.fetch.adzuna")


BASE = "https://api.adzuna.com/v1/api/jobs/ca/search"
RESULTS_PER_PAGE = 50
PAGES_PER_QUERY = 2


class AdzunaFetcher:
    name = "adzuna"

    def fetch(self, cfg: UserConfig) -> list[JobPosting]:
        app_id = os.environ.get("ADZUNA_APP_ID", "").strip()
        app_key = os.environ.get("ADZUNA_APP_KEY", "").strip()
        if not app_id or not app_key:
            log.info("ADZUNA_APP_ID / ADZUNA_APP_KEY not set — skipping Adzuna")
            return []

        results: dict[str, JobPosting] = {}
        titles = cfg.job_titles[:8]        # cap: don't blow the free quota
        # Query at the province level; the pipeline's location filter will
        # drop anything that slipped in from outside BC.
        where = cfg.province or cfg.city or "British Columbia"

        for title in titles:
            for page in range(1, PAGES_PER_QUERY + 1):
                url = f"{BASE}/{page}"
                params = {
                    "app_id": app_id,
                    "app_key": app_key,
                    "results_per_page": RESULTS_PER_PAGE,
                    "what_phrase": title,
                    "where": where,
                    "max_days_old": cfg.max_age_days,
                    "sort_by": "date",
                }
                r = _get_json(url, params=params)
                if not r:
                    break
                items = r.get("results") or []
                if not items:
                    break
                for item in items:
                    j = _to_job(item)
                    if j and j.source_id not in results:
                        results[j.source_id] = j
                if len(items) < RESULTS_PER_PAGE:
                    break
        log.info("adzuna: %d unique postings", len(results))
        return list(results.values())


def _get_json(url: str, *, params: dict) -> dict[str, Any] | None:
    try:
        r = httpx.get(url, params=params, headers=DEFAULT_HEADERS, timeout=20.0)
        if r.status_code == 429:
            log.warning("adzuna: rate-limited")
            return None
        r.raise_for_status()
        return r.json()
    except Exception as e:
        log.warning("adzuna GET failed: %s", e)
        return None


def _to_job(item: dict[str, Any]) -> JobPosting | None:
    try:
        sid = str(item.get("id") or item.get("adref") or item.get("redirect_url", ""))[:120]
        if not sid:
            return None
        posted = item.get("created") or ""
        posted_at = None
        if posted:
            try:
                posted_at = datetime.fromisoformat(posted.replace("Z", "+00:00"))
            except ValueError:
                posted_at = None
        salary = ""
        if item.get("salary_min") or item.get("salary_max"):
            smin = item.get("salary_min", "")
            smax = item.get("salary_max", "")
            cur = item.get("salary_is_predicted") and " (est)" or ""
            salary = f"{smin}–{smax} CAD{cur}" if smin and smax else f"{smin or smax} CAD{cur}"
        return JobPosting(
            source="adzuna",
            source_id=sid,
            title=(item.get("title") or "").strip(),
            org=(item.get("company", {}) or {}).get("display_name", "").strip(),
            location=(item.get("location", {}) or {}).get("display_name", "").strip(),
            url=item.get("redirect_url", ""),
            description=(item.get("description") or "").strip(),
            posted_at=posted_at,
            salary=salary,
            sector="",
            raw=item,
        )
    except Exception as e:
        log.warning("adzuna parse error: %s", e)
        return None
