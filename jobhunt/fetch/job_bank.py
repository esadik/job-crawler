"""Government of Canada Job Bank (jobbank.gc.ca) HTML scraper.

The results page returns up to 25 job cards per request. We query once per
job title × once for the user's location. Descriptions are the snippet from
the search results, not the full posting (full page is lazy-fetched by the
UI when the user opens a job).
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from urllib.parse import urljoin, urlencode

from bs4 import BeautifulSoup
from dateutil import parser as dateparser

from ..config import UserConfig
from ..models import JobPosting

from .base import http_get


log = logging.getLogger("jobhunt.fetch.jobbank")


BASE = "https://www.jobbank.gc.ca"
SEARCH_URL = BASE + "/jobsearch/jobsearch"


class JobBankFetcher:
    name = "jobbank"

    def fetch(self, cfg: UserConfig) -> list[JobPosting]:
        results: dict[str, JobPosting] = {}
        where = cfg.city or "Vancouver"
        for title in cfg.job_titles[:10]:
            params = {
                "searchstring": title,
                "locationstring": where,
                "sort": "D",  # by date
            }
            r = http_get(f"{SEARCH_URL}?{urlencode(params)}", timeout=15.0)
            if r is None:
                continue
            for job in _parse(r.text):
                if job.source_id not in results:
                    results[job.source_id] = job
        log.info("jobbank: %d unique postings", len(results))
        return list(results.values())


def _parse(html: str) -> list[JobPosting]:
    s = BeautifulSoup(html, "lxml")
    out: list[JobPosting] = []
    for art in s.select("article[id^=article-]"):
        aid = (art.get("id") or "").removeprefix("article-")
        if not aid:
            continue
        link_el = art.select_one("a.resultJobItem") or art.select_one("a[href*='/jobsearch/jobposting/']")
        href = link_el.get("href") if link_el else ""
        url = urljoin(BASE, href.split(";")[0]) if href else f"{BASE}/jobsearch/jobposting/{aid}"

        title_el = art.select_one(".noctitle")
        title = title_el.get_text(" ", strip=True) if title_el else ""
        if not title:
            # Fallback: last <li> / last text block in the h3.
            h3 = art.select_one("h3")
            title = h3.get_text(" ", strip=True) if h3 else "(untitled)"

        biz_el = art.select_one(".business")
        org = biz_el.get_text(" ", strip=True) if biz_el else ""

        loc_el = art.select_one(".location")
        location = ""
        if loc_el:
            location = loc_el.get_text(" ", strip=True).removeprefix("Location").strip()

        salary_el = art.select_one(".salary")
        salary = salary_el.get_text(" ", strip=True).removeprefix("Salary").strip() if salary_el else ""

        date_el = art.select_one(".date")
        posted_at = None
        if date_el:
            try:
                posted_at = dateparser.parse(date_el.get_text(" ", strip=True))
            except (ValueError, TypeError):
                posted_at = None

        # Snippet: strip the control chrome.
        snippet = art.get_text(" ", strip=True)
        snippet = re.sub(r"\s+", " ", snippet)[:600]

        sector = "government" if "government" in org.lower() or "ministry" in org.lower() else ""

        out.append(JobPosting(
            source="jobbank",
            source_id=aid,
            title=title.strip(),
            org=org.strip(),
            location=location,
            url=url,
            description=snippet,
            posted_at=posted_at,
            salary=salary,
            sector=sector,
        ))
    return out
