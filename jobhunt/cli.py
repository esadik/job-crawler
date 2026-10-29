"""Command-line interface. Mostly for the daily fetch cron + ad-hoc inspection."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import click
from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table

from . import db
from .config import load_user_config
from .eligibility import ELIGIBILITY_LABEL
from .models import ALL_STATUSES
from .pipeline import run_fetch
from .tailor import tailor


load_dotenv()


console = Console()


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


@click.group()
@click.option("--verbose", "-v", is_flag=True, help="Debug logging.")
def cli(verbose: bool) -> None:
    """Jobhunt — local job fetching + resume tailoring."""
    _setup_logging(verbose)


@cli.command()
def init() -> None:
    """Initialize the SQLite database."""
    db.init_db()
    console.print("[green]Database initialized at[/]", db.DB_PATH)


@cli.command()
@click.option("--only", multiple=True, help="Only run named fetchers.")
def fetch(only: tuple[str, ...]) -> None:
    """Run all fetchers once, score postings, and store new ones."""
    cfg = load_user_config()
    fetchers = None
    if only:
        from .fetch import ALL_FETCHERS
        fetchers = [f for f in ALL_FETCHERS if f.name in only]
        if not fetchers:
            console.print(f"[red]No fetchers matched {only}[/]")
            sys.exit(1)
    summary = run_fetch(cfg, fetchers=fetchers)
    t = Table(title="Fetch results")
    t.add_column("Source")
    t.add_column("New", justify="right")
    t.add_column("Duplicates", justify="right")
    t.add_column("Error")
    for r in summary.results:
        t.add_row(r.source, str(r.new), str(r.duplicates), (r.error or "")[:60])
    console.print(t)
    console.print(f"[bold]Total new: {summary.total_new}[/]  (dups: {summary.total_dups})")


@cli.command("list")
@click.option("--status", "statuses", multiple=True, type=click.Choice(ALL_STATUSES))
@click.option("--min-score", type=int, default=None)
@click.option("--eligibility", "elig", multiple=True)
@click.option("--source", "sources", multiple=True)
@click.option("--search", default=None)
@click.option("--limit", type=int, default=25)
def list_cmd(statuses, min_score, elig, sources, search, limit) -> None:
    """List postings matching filters."""
    jobs = db.list_jobs(
        statuses=list(statuses) or None,
        min_score=min_score,
        eligibility=list(elig) or None,
        sources=list(sources) or None,
        search=search,
        limit=limit,
    )
    t = Table(show_lines=False)
    t.add_column("ID", justify="right")
    t.add_column("Score", justify="right")
    t.add_column("Elig")
    t.add_column("Title", overflow="fold")
    t.add_column("Org", overflow="fold")
    t.add_column("Loc")
    t.add_column("Source")
    t.add_column("Status")
    for j in jobs:
        t.add_row(
            str(j.id),
            str(j.match_score),
            ELIGIBILITY_LABEL.get(j.eligibility, j.eligibility),
            j.title[:60],
            j.org[:30],
            (j.location or "")[:20],
            j.source,
            j.status,
        )
    console.print(t)
    console.print(f"[dim]{len(jobs)} rows[/]")


@cli.command()
@click.argument("job_id", type=int)
def view(job_id: int) -> None:
    """Show full details for one posting."""
    j = db.get_job(job_id)
    if not j:
        console.print(f"[red]Job {job_id} not found[/]")
        sys.exit(1)
    console.rule(f"[bold]{j.title}  @  {j.org}")
    console.print(f"Source:   {j.source}  ({j.source_id})")
    console.print(f"Location: {j.location}")
    console.print(f"Posted:   {j.posted_at}")
    console.print(f"Salary:   {j.salary}")
    console.print(f"URL:      {j.url}")
    console.print(f"Score:    {j.match_score}  "
                  f"titles={j.matched_titles}  themes={j.matched_themes}")
    console.print(f"Eligibility: {ELIGIBILITY_LABEL.get(j.eligibility, j.eligibility)}  "
                  f"→ {j.eligibility_evidence or '(no evidence sentence)'}")
    console.print(f"Status:   {j.status}")
    console.rule("Description")
    console.print(j.description or "(no description)")


@cli.command("tailor")
@click.argument("job_id", type=int)
@click.option("--no-pdf", is_flag=True, help="Only write resume.tex, don't compile.")
def tailor_cmd(job_id: int, no_pdf: bool) -> None:
    """Build a tailored resume for a specific job."""
    j = db.get_job(job_id)
    if not j:
        console.print(f"[red]Job {job_id} not found[/]")
        sys.exit(1)
    res = tailor(j, compile_pdf=not no_pdf)
    db.set_tailored_path(job_id, str(res.pdf_path or res.tex_path))
    console.print(f"[green]Tailored for {j.title} @ {j.org}[/]")
    console.print(f"  Sector:         {res.sector}  ({res.page_budget} page target)")
    console.print(f"  Policy picked:  {res.chosen_policy_keys}")
    console.print(f"  Comm. picked:   {res.chosen_community_keys}")
    console.print(f"  LaTeX:          {res.tex_path}")
    if res.pdf_path:
        console.print(f"  PDF:            {res.pdf_path}")
    else:
        console.print(f"[yellow]  No PDF built. Check {res.log_path or 'logs'} or install pdflatex.[/]")


@cli.command()
@click.argument("job_id", type=int)
@click.argument("status", type=click.Choice(ALL_STATUSES))
@click.option("--notes", default=None)
def mark(job_id: int, status: str, notes: str | None) -> None:
    """Change the status of a job (new/interested/applied/interview/offer/rejected/hidden)."""
    db.set_status(job_id, status, notes=notes)
    console.print(f"[green]Job {job_id} → {status}[/]")


@cli.command()
def status() -> None:
    """Pipeline summary."""
    cfg = load_user_config()
    counts = db.counts_by_status()
    recent = db.recent_summary(strong_threshold=cfg.strong_match_threshold)
    t = Table(title="Pipeline")
    t.add_column("Status")
    t.add_column("Count", justify="right")
    for s in ALL_STATUSES:
        t.add_row(s, str(counts.get(s, 0)))
    console.print(t)
    console.print(f"[bold]Last 24h:[/] {recent['new']} fetched, {recent['strong']} strong matches.")
    console.print(f"Total in DB: {recent['total']}")


def main() -> None:
    cli()


if __name__ == "__main__":
    main()
