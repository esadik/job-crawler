"""Glue the fetch → score → eligibility → upsert flow."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from .config import UserConfig, load_user_config
from .db import init_db, upsert_jobs
from .eligibility import classify
from .fetch import ALL_FETCHERS
from .fetch.base import Fetcher, FetchResult
from .scoring import score_job


log = logging.getLogger("jobhunt.pipeline")


@dataclass
class RunSummary:
    results: list[FetchResult]

    @property
    def total_new(self) -> int:
        return sum(r.new for r in self.results)

    @property
    def total_dups(self) -> int:
        return sum(r.duplicates for r in self.results)


def run_fetch(cfg: UserConfig | None = None, fetchers: list[Fetcher] | None = None) -> RunSummary:
    cfg = cfg or load_user_config()
    init_db()

    results: list[FetchResult] = []
    for fetcher in fetchers or ALL_FETCHERS:
        try:
            raw = fetcher.fetch(cfg) or []
        except Exception as e:
            log.exception("fetcher %s failed", fetcher.name)
            results.append(FetchResult(source=fetcher.name, new=0, duplicates=0, error=str(e)))
            continue

        for job in raw:
            score_job(job, cfg)
            elig, evidence = classify(job.description, job.sector)
            job.eligibility = elig
            job.eligibility_evidence = evidence

        new, dup = upsert_jobs(raw)
        results.append(FetchResult(source=fetcher.name, new=new, duplicates=dup))
        log.info("%s: %d new, %d dups", fetcher.name, new, dup)
    return RunSummary(results=results)
