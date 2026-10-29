"""Streamlit dashboard. Run with:  streamlit run jobhunt/ui.py

Streamlit executes this file as a standalone script, not as a submodule of
the ``jobhunt`` package, so we add the repo root to ``sys.path`` and use
absolute imports.
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import streamlit as st
from dotenv import load_dotenv

from jobhunt import db
from jobhunt.config import load_user_config
from jobhunt.eligibility import ELIGIBILITY_LABEL
from jobhunt.models import ALL_STATUSES, STATUS_NEW
from jobhunt.pipeline import run_fetch
from jobhunt.tailor import tailor


load_dotenv()


st.set_page_config(page_title="Jobhunt", layout="wide")
cfg = load_user_config()
db.init_db()


# -------------------- Sidebar --------------------

with st.sidebar:
    st.header("Jobhunt")
    st.caption(f"Hi {cfg.name} — PGWP: {cfg.can_work_in_canada}")

    if st.button("↻ Fetch now", type="primary", use_container_width=True):
        with st.spinner("Fetching jobs from all sources…"):
            summary = run_fetch(cfg)
        st.success(f"Fetched {summary.total_new} new postings ({summary.total_dups} already in DB).")
        for r in summary.results:
            icon = "✓" if not r.error else "✗"
            st.text(f"{icon} {r.source}: +{r.new} new ({r.duplicates} dup){' — ' + r.error if r.error else ''}")

    st.divider()
    st.subheader("Filters")
    status_sel = st.multiselect(
        "Status",
        ALL_STATUSES,
        default=["new", "interested"],
    )
    elig_sel = st.multiselect(
        "Eligibility",
        ["open", "verify", "restricted", "unknown"],
        default=["open", "verify", "unknown"],
    )
    min_score = st.slider("Min match score", 0, 100, cfg.strong_match_threshold)
    search = st.text_input("Search title / org / description", "")
    sort = st.selectbox("Sort by", ["Match score", "Date posted", "Date fetched"])

    st.divider()
    counts = db.counts_by_status()
    recent = db.recent_summary(strong_threshold=cfg.strong_match_threshold)
    st.metric("Last 24h", recent["new"])
    st.metric("Strong matches", recent["strong"])
    st.caption(f"Total in DB: {recent['total']}")


# -------------------- Main --------------------

st.title("Today's postings")
jobs = db.list_jobs(
    statuses=status_sel or None,
    min_score=min_score or None,
    eligibility=elig_sel or None,
    search=search or None,
    limit=500,
)

if sort == "Date posted":
    jobs.sort(key=lambda j: (j.posted_at or datetime.min), reverse=True)
elif sort == "Date fetched":
    jobs.sort(key=lambda j: (j.fetched_at or datetime.min), reverse=True)

st.caption(f"Showing {len(jobs)} postings.")

tab_browse, tab_board = st.tabs(["Browse", "Pipeline board"])

# -------------------- Browse tab --------------------

with tab_browse:
    for j in jobs:
        container = st.container(border=True)
        with container:
            top1, top2 = st.columns([5, 1])
            with top1:
                st.subheader(j.title)
                st.caption(
                    f"**{j.org}** · {j.location or '—'} · "
                    f"{j.source} · "
                    f"posted {j.posted_at.date() if j.posted_at else '?'}"
                )
            with top2:
                st.metric("Match", j.match_score)

            cols = st.columns([2, 1, 1, 1])
            with cols[0]:
                st.write(f"**Eligibility:** {ELIGIBILITY_LABEL.get(j.eligibility, j.eligibility)}")
                if j.eligibility_evidence:
                    st.caption(f"↳ _“{j.eligibility_evidence}”_")
                if j.matched_titles:
                    st.caption(f"Matched titles: {', '.join(j.matched_titles)}")
                if j.matched_themes:
                    st.caption(f"Themes: {', '.join(j.matched_themes)}")
            with cols[1]:
                st.markdown(f"[Open posting ↗]({j.url})" if j.url else "_No URL_")
            with cols[2]:
                new_status = st.selectbox(
                    "Status",
                    ALL_STATUSES,
                    index=ALL_STATUSES.index(j.status) if j.status in ALL_STATUSES else 0,
                    key=f"status-{j.id}",
                )
                if new_status != j.status:
                    db.set_status(j.id, new_status)
                    st.rerun()
            with cols[3]:
                if st.button("Tailor resume", key=f"tailor-{j.id}"):
                    with st.spinner("Picking experiences and compiling LaTeX…"):
                        res = tailor(j)
                    db.set_tailored_path(j.id, str(res.pdf_path or res.tex_path))
                    st.success(f"Tailored → {res.sector}, {res.page_budget} page target.")
                    st.caption(f"Policy: {res.chosen_policy_keys}")
                    st.caption(f"Community: {res.chosen_community_keys}")
                    if res.pdf_path:
                        with open(res.pdf_path, "rb") as fh:
                            st.download_button(
                                "Download PDF",
                                data=fh.read(),
                                file_name=res.pdf_path.name,
                                mime="application/pdf",
                                key=f"dl-{j.id}",
                            )
                    else:
                        st.warning("No PDF built. Install pdflatex to compile locally.")

            with st.expander("Description"):
                st.write(j.description or "(no description)")


# -------------------- Board tab --------------------

with tab_board:
    board_cols = st.columns(len(ALL_STATUSES[:-1]))  # skip "hidden"
    for col, status in zip(board_cols, ALL_STATUSES[:-1]):
        with col:
            st.subheader(status.title())
            rows = [j for j in db.list_jobs(statuses=[status], limit=100)]
            st.caption(f"{len(rows)}")
            for j in rows:
                st.markdown(
                    f"**[{j.title}]({j.url or '#'})**  \n"
                    f"<small>{j.org} · score {j.match_score}</small>",
                    unsafe_allow_html=True,
                )
                st.divider()
