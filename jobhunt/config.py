"""Load user config + org watchlist from the ``config/`` folder."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = REPO_ROOT / "config"
DATA_DIR = REPO_ROOT / "data"
APPLICATIONS_DIR = REPO_ROOT / "applications"
RESUME_DIR = REPO_ROOT / "resume"


@dataclass
class UserConfig:
    name: str
    city: str
    province: str
    province_code: str
    country: str
    work_auth_status: str
    can_work_in_canada: bool
    needs_sponsorship: bool
    job_titles: list[str] = field(default_factory=list)
    soft_titles: list[str] = field(default_factory=list)
    themes: list[str] = field(default_factory=list)
    locations_allowed: list[str] = field(default_factory=list)
    strict_location_filter: bool = True
    strong_match_threshold: int = 55
    max_age_days: int = 21

    @property
    def all_titles(self) -> list[str]:
        return self.job_titles + self.soft_titles


@dataclass
class WatchedOrg:
    name: str
    url: str
    tags: list[str] = field(default_factory=list)


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def load_user_config(path: Path | None = None) -> UserConfig:
    data = _load_yaml(path or CONFIG_DIR / "user.yaml")
    loc = data.get("location", {}) or {}
    auth = data.get("work_authorization", {}) or {}
    return UserConfig(
        name=data.get("name", ""),
        city=loc.get("city", ""),
        province=loc.get("province", ""),
        province_code=loc.get("province_code", ""),
        country=loc.get("country", ""),
        work_auth_status=auth.get("status", "other"),
        can_work_in_canada=bool(auth.get("can_work_in_canada", True)),
        needs_sponsorship=bool(auth.get("needs_sponsorship", False)),
        job_titles=list(data.get("job_titles") or []),
        soft_titles=list(data.get("soft_titles") or []),
        themes=list(data.get("themes") or []),
        locations_allowed=list(data.get("locations_allowed") or []),
        strict_location_filter=bool(loc.get("strict_location_filter", True)),
        strong_match_threshold=int(data.get("strong_match_threshold", 55)),
        max_age_days=int(data.get("max_age_days", 21)),
    )


def load_watchlist(path: Path | None = None) -> list[WatchedOrg]:
    data = _load_yaml(path or CONFIG_DIR / "watchlist.yaml")
    return [
        WatchedOrg(
            name=o.get("name", ""),
            url=o.get("url", ""),
            tags=list(o.get("tags") or []),
        )
        for o in (data.get("orgs") or [])
        if o.get("url")
    ]
