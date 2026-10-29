"""Fetcher registry."""

from __future__ import annotations

from .adzuna import AdzunaFetcher
from .bc_public_service import BCPublicServiceFetcher
from .goodwork import GoodWorkFetcher
from .job_bank import JobBankFetcher
from .org_watchlist import OrgWatchlistFetcher


ALL_FETCHERS = [
    JobBankFetcher(),
    BCPublicServiceFetcher(),
    GoodWorkFetcher(),
    OrgWatchlistFetcher(),
    AdzunaFetcher(),
]
