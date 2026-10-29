"""BC Public Service careers scraper (bcpublicservice.hua.hrsmart.com).

The Hua/Deltek Talent Management search form uses GET with keyword params.
This fetcher queries each target title and parses the results table.
"""

from __future__ import annotations

import logging
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from dateutil import parser as dateparser

from ..config import UserConfig
from ..models import JobPosting

from .base import http_get


log = logging.getLogger("jobhunt.fetch.bc")


BASE = "https://bcpublicservice.hua.hrsmart.com"
SEARCH = BASE + "/hr/ats/JobSearch/searchResults"


class BCPublicServiceFetcher:
    name = "bc_public_service"

    def fetch(self, cfg: UserConfig) -> list[JobPosting]:
        results: dict[str, JobPosting] = {}
        for title in cfg.job_titles[:10]:
            params = {"searchString": title}
            r = http_get(SEARCH, params=params, timeout=20.0)
            if r is None:
                continue
            for job in _parse(r.text):
                if job.source_id not in results:
                    results[job.source_id] = job
        log.info("bc_public_service: %d unique postings", len(results))
        return list(results.values())


def _parse(html: str) -> list[JobPosting]:
    s = BeautifulSoup(html, "lxml")
    out: list[JobPosting] = []
    # Hua renders job rows as <tr> or <li class="job-item"> — try both.
    rows = s.select("tr.ats-row") or s.select("li.job-item") or s.select("table tr")
    for row in rows:
        link_el = row.find("a", href=re.compile(r"viewJob|JobDetails|jobDetails|viewJob\?job"))
        if not link_el:
            continue
        href = link_el.get("href", "")
        url = urljoin(BASE, href)
        m = re.search(r"(?:job(?:Id)?=|/)(\d{4,})", href)
        sid = m.group(1) if m else href[-60:]
        title = link_el.get_text(" ", strip=True)
        if not title:
            continue
        tds = row.find_all("td")
        location = ""
        close_date = ""
        ministry = ""
        for td in tds:
            txt = td.get_text(" ", strip=True)
            if re.search(r"\bBC|British Columbia|Victoria|Vancouver|Burnaby|Surrey\b", txt):
                location = location or txt
            if re.search(r"\d{4}-\d{2}-\d{2}", txt):
                close_date = close_date or txt
            if "Ministry" in txt or "Service" in txt or "Authority" in txt:
                ministry = ministry or txt
        posted_at = None
        if close_date:
            try:
                posted_at = dateparser.parse(close_date, fuzzy=True)
            except Exception:
                posted_at = None
        out.append(JobPosting(
            source="bc_public_service",
            source_id=sid,
            title=title,
            org=ministry or "BC Public Service",
            location=location or "British Columbia",
            url=url,
            description=f"BC Public Service posting. Closing: {close_date}" if close_date else "BC Public Service posting.",
            posted_at=posted_at,
            sector="government",
        ))
    return out
