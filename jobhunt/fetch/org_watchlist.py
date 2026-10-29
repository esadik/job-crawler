"""Direct scraping of specific org careers pages (from config/watchlist.yaml).

For each org we just fetch the HTML, pull all anchor text + hrefs, and
surface anchors whose visible text contains one of the user's target titles
(primary or soft). We don't try to extract descriptions; the UI link takes
them to the real page.
"""

from __future__ import annotations

import hashlib
import logging
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ..config import UserConfig, load_watchlist
from ..models import JobPosting

from .base import http_get


log = logging.getLogger("jobhunt.fetch.watchlist")


# Avoid raising false positives from nav/footer links.
BLACKLIST_WORDS = {
    "home", "about", "contact", "privacy", "terms", "donate", "login",
    "search", "news", "events", "shop", "newsletter", "subscribe",
}


class OrgWatchlistFetcher:
    name = "watchlist"

    def __init__(self) -> None:
        self.orgs = load_watchlist()

    def fetch(self, cfg: UserConfig) -> list[JobPosting]:
        titles = [t.lower() for t in cfg.all_titles]
        out: list[JobPosting] = []
        for org in self.orgs:
            r = http_get(org.url, timeout=20.0)
            if r is None:
                continue
            try:
                soup = BeautifulSoup(r.text, "lxml")
            except Exception:
                continue
            seen: set[str] = set()
            for a in soup.find_all("a", href=True):
                text = a.get_text(" ", strip=True)
                if not text or len(text) < 6 or text.lower() in BLACKLIST_WORDS:
                    continue
                text_l = text.lower()
                if not any(t in text_l for t in titles):
                    continue
                href = a.get("href", "")
                url = urljoin(org.url, href)
                if url in seen:
                    continue
                seen.add(url)
                sid = hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]
                out.append(JobPosting(
                    source=f"watchlist:{org.name}",
                    source_id=sid,
                    title=text[:200],
                    org=org.name,
                    location="",
                    url=url,
                    description=f"Posting on {org.name} careers page. Follow link for details.",
                    sector="nonprofit" if "nonprofit" in org.tags else ("government" if "government" in org.tags else ""),
                    tags=list(org.tags),
                ))
        log.info("watchlist: %d matched postings across %d orgs", len(out), len(self.orgs))
        return out
