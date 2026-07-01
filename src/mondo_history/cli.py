"""Command-line interface for building and querying the history artifact."""

from itertools import groupby
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.text import Text

from .extract import extract as run_extract
from .gitsource import GitSource
from .query import Change, HistoryDB

DEFAULT_PATH = "src/ontology/mondo-edit.obo"
DEFAULT_ARTIFACT = Path("artifact")

app = typer.Typer(add_completion=False, help="Build and query the Mondo history index.")
console = Console()


@app.command()
def build(
    repo: str = typer.Option("../mondo", help="Path to a Mondo clone to read history from."),
    path: str = typer.Option(DEFAULT_PATH, help="File whose history to index."),
    out: Path = typer.Option(DEFAULT_ARTIFACT, help="Output artifact directory."),
    limit: Optional[int] = typer.Option(None, help="Index only the most recent N versions."),
):
    """Extract history into a Parquet artifact."""
    with GitSource(repo) as src:
        counts = run_extract(src, path, out, limit=limit)
    console.print(
        f"[green]Built[/] {out} — "
        f"{counts['commits']} commits, {counts['snapshots']} snapshots, "
        f"{counts['events']} events."
    )


@app.command()
def term(
    mondo_id: str = typer.Argument(..., help="e.g. MONDO:0007739"),
    artifact: Path = typer.Option(DEFAULT_ARTIFACT, help="Artifact directory."),
    only: Optional[str] = typer.Option(None, help="Restrict to one clause kind, e.g. synonym."),
    at: Optional[int] = typer.Option(None, help="Reconstruct state as of this commit_seq."),
):
    """Show a term's change history, or its reconstructed state at a point."""
    db = HistoryDB(artifact)
    if at is not None:
        _render_state(mondo_id, at, db.term_at(mondo_id, at))
    else:
        _render_timeline(mondo_id, db.term_timeline(mondo_id, predicate=only))
    db.close()


@app.command()
def commit(
    sha: str = typer.Argument(..., help="Commit sha or unique prefix."),
    artifact: Path = typer.Option(DEFAULT_ARTIFACT, help="Artifact directory."),
):
    """List the terms changed together in one commit."""
    db = HistoryDB(artifact)
    terms = db.commit_terms(sha)
    if not terms:
        console.print(f"[yellow]No indexed changes for commit[/] {sha}")
    else:
        console.print(f"[bold]{len(terms)}[/] terms changed in {sha}:")
        for mondo_id, name in terms:
            line = Text("  ")
            line.append(mondo_id, style="cyan")
            if name:
                line.append(f"  {name}", style="dim")
            console.print(line)
    db.close()


def _render_timeline(mondo_id: str, changes: list[Change]) -> None:
    if not changes:
        console.print(f"[yellow]No history for[/] {mondo_id}")
        return
    console.print(f"[bold cyan]{mondo_id}[/] — {len(changes)} changes")
    for _, group in groupby(changes, key=lambda c: c.commit_seq):
        rows = list(group)
        head = rows[0]
        header = Text("\n● ")
        header.append(f"commit {head.commit_seq}", style="bold")
        header.append(f"  {_date(head.committed_date)}  ")
        if head.pr_number is not None:
            header.append(f"PR #{head.pr_number}  ", style="cyan")
        header.append(head.message.splitlines()[0], style="dim")
        console.print(header)
        for change in rows:
            line = Text("    ")
            if change.operation == "add":
                line.append("+ ", style="bold green")
            else:
                line.append("- ", style="bold red")
            line.append(f"{change.predicate}: {change.value}")
            console.print(line)


def _render_state(mondo_id: str, at: int, clauses: list[tuple[str, str]]) -> None:
    if not clauses:
        console.print(f"[yellow]{mondo_id} has no snapshot at or before commit {at}[/]")
        return
    console.print(f"[bold cyan]{mondo_id}[/] as of commit {at}:")
    console.print(Text(f"  id: {mondo_id}"))
    for predicate, value in clauses:
        console.print(Text(f"  {predicate}: {value}"))


def _date(value: object) -> str:
    return str(value)[:10]


if __name__ == "__main__":
    app()
