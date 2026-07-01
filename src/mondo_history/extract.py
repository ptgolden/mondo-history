"""Turn a stream of file versions into the history artifact.

Walks one file's versions oldest-first, parses each into per-term state, and:

* writes a ``term_snapshots`` row for every term that changed at that commit;
* writes ``events`` rows for the clause-level adds/removes that changed it.

The first version in the stream is a **baseline**: every term is snapshotted but
no events are emitted, because a term's clauses were added *before* the window and
dating those additions to the window's start would be a lie. Terms that first
appear *after* the baseline are diffed against nothing, so their creation shows up
as clause additions. Term creation/removal times are recoverable from snapshot
presence, so they need no dedicated event kind.
"""

import re
from collections.abc import Iterable
from datetime import timezone
from pathlib import Path

from . import model
from .gitsource import CommitInfo, FileVersion, GitSource, TagRef
from .obo import Clause, TermState, clause_delta, parse_terms

_PR = re.compile(r"\(#(\d+)\)")
_EMPTY: tuple[Clause, ...] = ()


def extract(
    src: GitSource, path: str, out_dir: Path, *, limit: int | None = None
) -> dict[str, int]:
    """Build an artifact under ``out_dir`` from ``path``'s history in ``src``.

    ``limit`` keeps only the most recent ``limit`` versions (the oldest kept one
    becomes the baseline) — useful for iterating on a recent slice.
    """
    versions = list(src.iter_file_history(path))
    if limit is not None:
        versions = versions[-limit:]
    return build(versions, src.read_blob, out_dir, source_path=path, tags=src.read_tags())


def build(
    versions: Iterable[FileVersion],
    read_blob,
    out_dir: Path,
    *,
    source_path: str,
    tags: Iterable[TagRef] = (),
) -> dict[str, int]:
    commits: list[dict] = []
    snapshots: list[dict] = []
    events: list[dict] = []

    prev: dict[str, TermState] = {}
    seqs: list[int] = []
    seq_dates: list[tuple[int, object]] = []  # (seq, naive-UTC date) for tag mapping
    for i, version in enumerate(versions):
        current = parse_terms(read_blob(version.blob_oid))
        row = _commit_row(version.commit)
        commits.append(row)
        seqs.append(version.commit.seq)
        seq_dates.append((version.commit.seq, row["committed_date"]))

        if i == 0:
            for term in current.values():
                snapshots.append(_snapshot_row(version, term))
        else:
            for mondo_id, term in current.items():
                before = prev.get(mondo_id)
                if before is not None and before.content_hash == term.content_hash:
                    continue
                snapshots.append(_snapshot_row(version, term))
                added, removed = clause_delta(
                    before.clauses if before else _EMPTY, term.clauses
                )
                events.extend(_event_rows(version, mondo_id, added, model.Operation.ADD))
                events.extend(_event_rows(version, mondo_id, removed, model.Operation.REMOVE))
            for mondo_id in prev.keys() - current.keys():
                events.extend(
                    _event_rows(version, mondo_id, prev[mondo_id].clauses, model.Operation.REMOVE)
                )
        prev = current

    meta = [
        {
            "schema_version": model.SCHEMA_VERSION,
            "generator_version": _version(),
            "source_path": source_path,
            "first_commit_seq": seqs[0] if seqs else None,
            "last_commit_seq": seqs[-1] if seqs else None,
            "n_commits": len(seqs),
        }
    ]

    releases = _release_rows(tags, seq_dates)

    model.write_table(commits, model.COMMITS, out_dir, "commits")
    model.write_table(snapshots, model.TERM_SNAPSHOTS, out_dir, "term_snapshots")
    model.write_table(events, model.EVENTS, out_dir, "events")
    model.write_table(releases, model.RELEASES, out_dir, "releases")
    model.write_table(meta, model.BUILD_META, out_dir, "build_meta")

    return {
        "commits": len(commits),
        "snapshots": len(snapshots),
        "events": len(events),
        "releases": len(releases),
    }


def _release_rows(
    tags: Iterable[TagRef], seq_dates: list[tuple[int, object]]
) -> list[dict]:
    """Map each tag to the latest file-history commit at or before its date.

    A release's file state is whatever the last commit touching the file left it
    as of the tag; tags predating the window map to no commit and are dropped.
    """
    rows: list[dict] = []
    for tag in tags:
        tag_date = tag.date.astimezone(timezone.utc).replace(tzinfo=None)
        seq = None
        for candidate_seq, date in seq_dates:
            if date <= tag_date:
                seq = candidate_seq
            else:
                break
        if seq is None:
            continue
        rows.append(
            {"tag": tag.name, "sha": tag.sha, "date": tag_date, "commit_seq": seq}
        )
    return rows


def _commit_row(commit: CommitInfo) -> dict:
    match = _PR.search(commit.message)
    return {
        "commit_seq": commit.seq,
        "sha": commit.sha,
        "author_name": commit.author_name,
        "author_email": commit.author_email,
        "committed_date": commit.committed_date.astimezone(timezone.utc).replace(tzinfo=None),
        "message": commit.message,
        "pr_number": int(match.group(1)) if match else None,
        "parent_sha": commit.parent_sha,
    }


def _snapshot_row(version: FileVersion, term: TermState) -> dict:
    name = next((c.value for c in term.clauses if c.predicate == "name"), None)
    is_obsolete = any(
        c.predicate == "is_obsolete" and c.value == "true" for c in term.clauses
    )
    return {
        "mondo_id": term.mondo_id,
        "commit_seq": version.commit.seq,
        "sha": version.commit.sha,
        "name": name,
        "is_obsolete": is_obsolete,
        "content_hash": term.content_hash,
        "clauses": [{"predicate": c.predicate, "value": c.value} for c in term.clauses],
    }


def _event_rows(
    version: FileVersion,
    mondo_id: str,
    clauses: Iterable[Clause],
    operation: model.Operation,
) -> list[dict]:
    return [
        {
            "mondo_id": mondo_id,
            "commit_seq": version.commit.seq,
            "sha": version.commit.sha,
            "predicate": clause.predicate,
            "value": clause.value,
            "operation": str(operation),
        }
        for clause in clauses
    ]


def _version() -> str:
    from . import __version__

    return __version__
