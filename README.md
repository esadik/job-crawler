# jobhunt

A tiny, local-first job finder + LaTeX resume tailoring tool. Built for
policy / research / community-engagement roles in Canada, but easy to retarget.

**v0.1 does only these things:**

1. Fetches job postings every day from several Canadian sources into a local
   SQLite database.
2. Scores each posting against your target titles, themes, and location.
3. Flags citizenship / clearance restrictions in government postings
   (important for PGWP holders).
4. Lets you browse postings and change their pipeline status
   (`new → interested → applied → interview → offer / rejected`) in a
   lightweight local dashboard.
5. For any posting, selects which of your LaTeX experience blocks best fit
   the JD, respects a per-sector page budget (1 page for private, 2 pages
   for government / nonprofit), and compiles a tailored PDF.

No cloud, no login, no AI yet — just keyword matching. All data lives in
`data/jobhunt.db` on your laptop.

---

## Quickstart

### 1. Install

Requires Python 3.11+ and `pdflatex`.

```bash
# macOS
brew install --cask mactex-no-gui          # or basictex (smaller)

# Ubuntu / Debian
sudo apt-get install -y texlive-latex-base texlive-latex-recommended \
    texlive-latex-extra texlive-fonts-recommended lmodern

# Windows: install MiKTeX from https://miktex.org/

# Then, in this repo:
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure

- Open `config/user.yaml` and tweak target titles, themes, locations.
- Open `config/watchlist.yaml` to add/remove the orgs whose careers pages
  are scraped directly.
- Open `resume/experiences.yaml` and update it with your experiences
  (tags, bullets, priorities). This is your "master" resume — the tailor
  picks a subset of these per job.
- Copy `.env.example` to `.env`. Optional: get a free Adzuna API key
  from https://developer.adzuna.com/ (used to pull LinkedIn/Indeed-like
  aggregated listings) and paste it in.

### 3. Run

```bash
# Initialize the DB (once).
python -m jobhunt.cli init

# Fetch jobs now.
python -m jobhunt.cli fetch

# Launch the dashboard in your browser.
./scripts/run_ui.sh
# or:  streamlit run jobhunt/ui.py
```

The dashboard opens at http://localhost:8501. From there you can
filter postings, tailor a resume for any one of them, and move jobs
through your pipeline.

### 4. Schedule the daily fetch (optional)

Cron (macOS / Linux):

```bash
# Every day at 7am local time.
crontab -e
# Add:
0 7 * * * cd /path/to/this/repo && .venv/bin/python scripts/fetch_all.py >> data/fetch.log 2>&1
```

Windows: use Task Scheduler to run `python scripts\fetch_all.py` daily.

---

## Sources in v0.1

| Source | What it covers | Needs key |
|---|---|---|
| **Government of Canada Job Bank** | federal + provincial + many private | no |
| **BC Public Service** | BC provincial roles | no |
| **GoodWork.ca** | environment / climate / sustainability | no |
| **Adzuna** | aggregator including Indeed/LinkedIn-like listings | yes (free) |
| **Org watchlist** | careers pages of orgs you follow (see `config/watchlist.yaml`) | no |

Everything else (CharityVillage, DevEx, UN Careers, Chrome extension, email
forwarding) is on the v0.2 roadmap.

---

## Project layout

```
.
├── config/              → user config: target titles, themes, orgs
├── jobhunt/
│   ├── cli.py           → `python -m jobhunt.cli …`
│   ├── config.py        → load user.yaml / watchlist.yaml
│   ├── db.py            → SQLite schema + queries
│   ├── eligibility.py   → citizenship / clearance regex detector
│   ├── fetch/           → one module per source
│   ├── models.py        → shared dataclasses (JobPosting, StoredJob)
│   ├── pipeline.py      → fetch + score + eligibility + upsert
│   ├── scoring.py       → keyword relevance score (0-100)
│   ├── tailor.py        → pick experiences + render LaTeX + compile PDF
│   └── ui.py            → Streamlit dashboard
├── resume/
│   ├── experiences.yaml → the master resume (tagged bullets by sector)
│   └── template.tex.j2  → Jinja2 → LaTeX template
├── scripts/
│   ├── fetch_all.py     → cron entry
│   └── run_ui.sh        → launch Streamlit
├── applications/        → per-job output folders (gitignored)
└── data/jobhunt.db      → the SQLite file (gitignored)
```

---

## Location scope

By default jobhunt filters postings down to the configured province (BC
out of the box). This happens in `jobhunt/location_filter.py` and is
driven by:

```yaml
# config/user.yaml
location:
  province: British Columbia
  province_code: BC
  strict_location_filter: true
locations_allowed:
  - Vancouver
  - BC
  - British Columbia
  - Burnaby
  - …
```

Rules in short: an explicit same-province signal (``(BC)``, "Victoria",
etc.) keeps the posting. An explicit other-province signal (``(ON)``,
"Alberta", "remote in Southern Ontario") drops it, even if the posting
also says "remote". Postings with no location text, or just "Remote
(Canada)" / "anywhere in Canada", are kept so you can judge them.

To turn the filter off globally, set
``location.strict_location_filter: false``.

If you already have an older DB with out-of-province postings in it, run:

```bash
python -m jobhunt.cli purge-out-of-scope --dry-run   # preview
python -m jobhunt.cli purge-out-of-scope             # actually delete
```

## Eligibility flags

Every posting is tagged with one of:

- 🟢 **Open** — the description explicitly says you need the right to work in
  Canada (any permit OK), or the job is clearly in a sector with no citizen
  requirement.
- 🟡 **Verify** — a government posting with no explicit restriction, or a
  phrase like "preference given to Canadian citizens". Still worth applying,
  but check.
- 🔴 **Restricted** — the description explicitly requires Canadian
  citizenship / permanent residency, or a secret / top-secret clearance.
- ❔ **Unknown** — no signal detected.

The exact triggering sentence is shown next to the flag in the UI so you
can judge for yourself. The detector is in `jobhunt/eligibility.py`
and is just regexes — if it misses something, add a pattern there.

---

## Resume tailoring: how it picks what to include

For each posting, the tailor:

1. Reads your `resume/experiences.yaml`.
2. Scores each experience against the JD (priority tag + sector fit +
   tag overlap with JD text + bullet-vocabulary overlap).
3. Picks the top experiences within the page budget:
   - 1 page (private): 2 policy + 1 community.
   - 2 pages (gov/nonprofit): up to 5 policy + 3 community.
4. Filters qualifications and certifications to those whose tags match the JD.
5. Renders `resume/template.tex.j2` → `applications/<slug>/resume.tex`.
6. Compiles with `pdflatex` → `applications/<slug>/resume.pdf`.

**It never fabricates content.** Every bullet comes from your YAML.

---

## Adding your own experiences

Each experience block in `resume/experiences.yaml` looks like:

```yaml
- key: unique-slug
  priority: high            # high | med | low
  sectors: [all]            # or e.g. [government, nonprofit]
  tags: [policy, climate]   # drives relevance to a JD
  title: "Policy Analyst"
  org: "Some Ministry"
  location: "Victoria, BC"
  dates: "September 2024 -- April 2025"
  section: policy           # "policy" or "community"
  bullets:
    - "A single bullet. LaTeX special chars like & must be \\&."
```

Tags matter: `policy, climate, agriculture` makes this experience get picked
when the JD mentions those words. Priority breaks ties when many experiences
are relevant.

---

## Known limitations in v0.1 (planned for v0.2)

- No AI scoring yet. Keyword-only means some semantically relevant jobs
  score low. Fix: wire an LLM for a semantic match score.
- No cover letters.
- No bullet-level reordering within an experience — only experience-level
  pick/drop.
- CharityVillage not yet integrated (it's a JS SPA; needs their API).
- No Chrome extension, no email ingestion.
- Scrapers break if sites change their HTML. If a fetcher stops working,
  open an issue (or read its module — they're each ~50 lines).

---

## License

MIT.
