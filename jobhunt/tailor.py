"""Resume tailoring.

Given a stored job, this module:
  1. loads the master resume (resume/experiences.yaml),
  2. scores each experience block for relevance to the JD,
  3. picks a subset that fits the per-sector page budget
     (private = 1 page, gov/nonprofit = 2 pages),
  4. renders a LaTeX file via resume/template.tex.j2,
  5. compiles it with pdflatex into applications/<slug>/.

If pdflatex isn't installed, we still write the .tex file so the user can
compile it elsewhere.
"""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader, select_autoescape

from .config import APPLICATIONS_DIR, RESUME_DIR
from .models import StoredJob


log = logging.getLogger("jobhunt.tailor")

RESUME_YAML = RESUME_DIR / "experiences.yaml"
TEMPLATE_NAME = "template.tex.j2"


# ---------------------------------------------------------------------------
# Loading


def load_resume() -> dict:
    with RESUME_YAML.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


# ---------------------------------------------------------------------------
# Experience selection


_TOKEN = re.compile(r"[a-z0-9+]+")


def _tokens(s: str) -> set[str]:
    return set(_TOKEN.findall((s or "").lower()))


PRIORITY_WEIGHTS = {"high": 10, "med": 5, "low": 2}


def score_experience(exp: dict, jd_text: str, sector: str) -> float:
    """Experience relevance to a specific JD."""
    jd_tokens = _tokens(jd_text)
    tags = [t.lower() for t in exp.get("tags", [])]
    sectors = [s.lower() for s in exp.get("sectors", ["all"])]

    # Baseline from priority.
    s = PRIORITY_WEIGHTS.get(exp.get("priority", "med"), 5)

    # Sector fit.
    if sector and (sector in sectors or "all" in sectors):
        s += 5

    # Tag ↔ JD text overlap.
    for tag in tags:
        if tag == "all":
            continue
        for part in tag.split("-"):
            if part in jd_tokens:
                s += 2
                break

    # Bullet ↔ JD overlap: lightly reward surface vocabulary matches.
    bullet_tokens: set[str] = set()
    for b in exp.get("bullets", []):
        bullet_tokens |= _tokens(b)
    overlap = len(bullet_tokens & jd_tokens)
    s += min(overlap / 4.0, 8)

    return s


def choose_experiences(
    resume: dict,
    jd_text: str,
    sector: str,
    *,
    page_budget: int,
) -> tuple[list[dict], list[dict]]:
    """Return (policy_experiences, community_experiences) kept for the output.

    Rough budget mapping:
      1 page  → max 3 policy + 1 community   (private)
      2 pages → max 5 policy + 3 community   (gov / nonprofit)
    """
    if page_budget <= 1:
        max_policy, max_community = 2, 1
    else:
        max_policy, max_community = 5, 3

    all_exps = resume.get("experiences", []) or []
    scored = sorted(
        ((e, score_experience(e, jd_text, sector)) for e in all_exps),
        key=lambda x: x[1],
        reverse=True,
    )

    policy = [e for e, _ in scored if (e.get("section") == "policy")]
    community = [e for e, _ in scored if (e.get("section") == "community")]

    # Keep the top-scoring ones in reverse-chronological order within each section.
    def _by_date(exps: list[dict]) -> list[dict]:
        def _key(e: dict) -> str:
            return (e.get("dates") or "")[-20:]
        return sorted(exps, key=_key, reverse=True)

    return (_by_date(policy[:max_policy]), _by_date(community[:max_community]))


# ---------------------------------------------------------------------------
# Qualifications & certifications filtering


def pick_qualifications(resume: dict, jd_text: str, max_items: int | None = None) -> list[str]:
    jd = jd_text.lower()
    scored: list[tuple[int, int, str]] = []  # (score, order, text)
    for idx, q in enumerate(resume.get("qualifications", []) or []):
        tags = [t.lower() for t in q.get("tags", [])]
        if "all" in tags:
            score = 1
        else:
            score = sum(1 for t in tags if t in jd)
        if score > 0:
            scored.append((score, -idx, q["text"]))
    scored.sort(reverse=True)
    out = [t for _, _, t in scored]
    if max_items is not None:
        out = out[:max_items]
    return out


def pick_certifications(resume: dict, jd_text: str, max_items: int | None = None) -> list[str]:
    jd = jd_text.lower()
    scored: list[tuple[int, int, str]] = []
    for idx, c in enumerate(resume.get("certifications", []) or []):
        tags = [t.lower() for t in c.get("tags", [])]
        if "all" in tags:
            score = 1
        else:
            score = sum(1 for t in tags if t in jd)
        if score > 0:
            scored.append((score, -idx, c["text"]))
    scored.sort(reverse=True)
    out = [t for _, _, t in scored]
    if max_items is not None:
        out = out[:max_items]
    return out


# ---------------------------------------------------------------------------
# Rendering


@dataclass
class TailorResult:
    tex_path: Path
    pdf_path: Path | None
    sector: str
    page_budget: int
    chosen_policy_keys: list[str]
    chosen_community_keys: list[str]
    log_path: Path | None = None


def _sector_for_tailoring(job: StoredJob) -> tuple[str, int]:
    """Return (sector_label, page_budget)."""
    s = (job.sector or "").lower().strip()
    org = (job.org or "").lower()
    text = f"{org} {job.description or ''}".lower()
    if s == "government" or re.search(r"\b(ministry|government|public service|municipal|city of|regional district|authority)\b", text):
        return ("government", 2)
    if s == "nonprofit" or re.search(r"\b(non.?profit|charity|society|foundation|united way|coalition)\b", text):
        return ("nonprofit", 2)
    return ("private", 1)


def _slugify(s: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", (s or "")).strip("-").lower()
    return s[:60] or "untitled"


def tailor(job: StoredJob, *, compile_pdf: bool = True) -> TailorResult:
    resume = load_resume()
    sector, page_budget = _sector_for_tailoring(job)
    jd_text = f"{job.title}\n{job.description}"

    policy, community = choose_experiences(resume, jd_text, sector, page_budget=page_budget)
    max_quals = 3 if page_budget <= 1 else 7
    max_certs = 2 if page_budget <= 1 else 3
    qualifications = pick_qualifications(resume, jd_text, max_items=max_quals)
    certifications = pick_certifications(resume, jd_text, max_items=max_certs)
    education = resume.get("education", []) or []
    headlines = resume.get("headlines", {}) or {}
    headline = headlines.get(sector, "")

    # 2-page uses roomier margins/fonts; 1-page gets tighter.
    if page_budget >= 2:
        font_size, margin, sec_above, sec_below = 11, 0.70, 1.4, 0.4
    else:
        font_size, margin, sec_above, sec_below = 10, 0.50, 0.8, 0.2

    env = Environment(
        loader=FileSystemLoader(str(RESUME_DIR)),
        autoescape=select_autoescape(default=False),
        trim_blocks=True,
        lstrip_blocks=True,
        # Use LaTeX-safe delimiters so {} in templates stays {}.
        variable_start_string="<<",
        variable_end_string=">>",
        block_start_string="<%",
        block_end_string="%>",
        comment_start_string="<#",
        comment_end_string="#>",
    )
    template = env.get_template(TEMPLATE_NAME)
    tex = template.render(
        header=resume["header"],
        headline=headline,
        qualifications=qualifications,
        education=education,
        policy_experiences=policy,
        community_experiences=community,
        certifications=certifications,
        font_size=font_size,
        margin=margin,
        sec_above=sec_above,
        sec_below=sec_below,
    )

    out_dir = APPLICATIONS_DIR / f"{job.id:04d}-{_slugify(job.org)}-{_slugify(job.title)}"
    out_dir.mkdir(parents=True, exist_ok=True)
    tex_path = out_dir / "resume.tex"
    tex_path.write_text(tex, encoding="utf-8")

    pdf_path = None
    log_path = None
    if compile_pdf and shutil.which("pdflatex"):
        try:
            res = subprocess.run(
                ["pdflatex", "-interaction=nonstopmode", "-halt-on-error", "resume.tex"],
                cwd=out_dir,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=60,
            )
            log_path = out_dir / "pdflatex.log"
            log_path.write_text(res.stdout + "\n" + res.stderr, encoding="utf-8")
            candidate = out_dir / "resume.pdf"
            if candidate.exists():
                pdf_path = candidate
            else:
                log.warning("pdflatex finished but no PDF produced; see %s", log_path)
        except Exception as e:
            log.warning("pdflatex failed: %s", e)

    return TailorResult(
        tex_path=tex_path,
        pdf_path=pdf_path,
        sector=sector,
        page_budget=page_budget,
        chosen_policy_keys=[e["key"] for e in policy],
        chosen_community_keys=[e["key"] for e in community],
        log_path=log_path,
    )
