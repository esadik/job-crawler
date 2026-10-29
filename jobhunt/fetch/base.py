"""Base class + helpers for all fetchers.

Every fetcher implements ``fetch(cfg) -> list[JobPosting]`` and is responsible
for being defensive: a broken source should log and return [], never raise
and kill the pipeline.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Protocol

import httpx

from ..config import UserConfig
from ..models import JobPosting


log = logging.getLogger("jobhunt.fetch")


DEFAULT_HEADERS = {
    "User-Agent": "jobhunt/0.1 (+https://github.com/esadik/job-crawler) python-httpx",
    "Accept": "text/html,application/xhtml+xml,application/xml,application/rss+xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-CA,en;q=0.9",
}


def http_get(url: str, *, timeout: float = 15.0, params: dict | None = None) -> httpx.Response | None:
    try:
        r = httpx.get(
            url,
            headers=DEFAULT_HEADERS,
            params=params,
            timeout=timeout,
            follow_redirects=True,
        )
        r.raise_for_status()
        return r
    except Exception as e:
        log.warning("GET failed %s: %s", url, e)
        return None


class Fetcher(Protocol):
    name: str

    def fetch(self, cfg: UserConfig) -> list[JobPosting]: ...


@dataclass
class FetchResult:
    source: str
    new: int
    duplicates: int
    error: str | None = None
