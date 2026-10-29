"""Simple keyword-based relevance scoring. No AI, deterministic.

Score (0-100) = weighted sum of:
  * exact title match          (up to 50)
  * soft/partial title overlap (up to 20)
  * theme matches              (up to 20)
  * location match             (up to 10)

The score caps at 100. Matched titles/themes are returned so the UI can show
*why* a job scored high.
"""

from __future__ import annotations

import re
from dataclasses import replace

from .config import UserConfig
from .models import JobPosting


_TOKEN = re.compile(r"[a-z0-9+]+")


def _tokens(s: str) -> set[str]:
    return set(_TOKEN.findall(s.lower()))


def _phrase_in(phrase: str, text_lower: str) -> bool:
    """Match a multi-word phrase ignoring extra whitespace. Case-insensitive
    on the caller's end: ``text_lower`` must already be lowercased."""
    tokens = re.split(r"\s+", phrase.lower().strip())
    if not tokens:
        return False
    pattern = r"\s+".join(re.escape(t) for t in tokens if t)
    if not pattern:
        return False
    return re.search(rf"\b{pattern}\b", text_lower) is not None


def score_job(job: JobPosting, cfg: UserConfig) -> JobPosting:
    """Returns a *new* JobPosting-like with scoring fields set."""
    title_lower = job.title.lower()
    desc_lower = (job.description or "").lower()
    loc_lower = (job.location or "").lower()
    hay = f"{title_lower}\n{desc_lower}"

    matched_titles: list[str] = []
    matched_themes: list[str] = []
    score = 0.0

    # 1. Primary title matches (strongest signal — look at job TITLE first).
    for t in cfg.job_titles:
        if _phrase_in(t, title_lower):
            matched_titles.append(t)
    if matched_titles:
        # One hit = 40, two hits = 50 (cap).
        score += min(50, 40 + 10 * (len(matched_titles) - 1))

    # 2. Soft titles (fuzzy "foot-in-door" matches).
    soft_hits = []
    for t in cfg.soft_titles:
        if _phrase_in(t, title_lower):
            soft_hits.append(t)
    if soft_hits:
        score += min(20, 10 + 5 * (len(soft_hits) - 1))
        matched_titles.extend(soft_hits)

    # 3. If no title match in the title, check in the description with less weight.
    if not matched_titles:
        desc_title_hits = []
        for t in cfg.job_titles + cfg.soft_titles:
            if _phrase_in(t, desc_lower):
                desc_title_hits.append(t)
        if desc_title_hits:
            score += 10
            matched_titles.extend(desc_title_hits[:3])

    # 4. Themes.
    for theme in cfg.themes:
        if _phrase_in(theme, hay):
            matched_themes.append(theme)
    if matched_themes:
        # Diminishing returns, cap 20.
        score += min(20, 7 + 3 * (len(matched_themes) - 1))

    # 5. Location.
    if any(_phrase_in(loc, loc_lower) or _phrase_in(loc, desc_lower) for loc in cfg.locations_allowed):
        score += 10

    final = int(round(min(score, 100)))
    # dedupe
    matched_titles = sorted(set(matched_titles))
    matched_themes = sorted(set(matched_themes))

    # Mutate (JobPosting is a dataclass, keep it simple).
    job.match_score = final
    job.matched_titles = matched_titles
    job.matched_themes = matched_themes
    return job
