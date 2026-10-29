#!/usr/bin/env python3
"""Entry point for cron: fetch all sources once and exit."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

from jobhunt.config import load_user_config
from jobhunt.pipeline import run_fetch


def main() -> int:
    load_dotenv()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    cfg = load_user_config()
    summary = run_fetch(cfg)
    for r in summary.results:
        print(
            f"{r.source}: +{r.new} new, {r.duplicates} dup, {r.filtered} out-of-scope"
            f"{' ERR: ' + r.error if r.error else ''}"
        )
    print(
        f"TOTAL new: {summary.total_new}, dup: {summary.total_dups}, "
        f"filtered: {summary.total_filtered}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
