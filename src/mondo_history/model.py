"""Typed vocabulary and Parquet schemas for the history artifact.

The artifact is a small set of Parquet files sharing ``commit_seq`` as their time
axis: ``commits`` (git metadata), ``term_snapshots`` (a term's full normalized
state, written only where it changed), and ``events`` (clause-level add/remove
deltas derived by diffing adjacent snapshots). ``build_meta`` records provenance.
"""

import enum
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

SCHEMA_VERSION = "1"


class Operation(enum.StrEnum):
    ADD = "add"
    REMOVE = "remove"


_CLAUSE = pa.struct([("predicate", pa.string()), ("value", pa.string())])

COMMITS = pa.schema(
    [
        ("commit_seq", pa.int32()),
        ("sha", pa.string()),
        ("author_name", pa.string()),
        ("author_email", pa.string()),
        ("committed_date", pa.timestamp("us")),  # naive UTC
        ("message", pa.string()),
        ("pr_number", pa.int32()),  # nullable
        ("parent_sha", pa.string()),  # nullable
    ]
)

TERM_SNAPSHOTS = pa.schema(
    [
        ("mondo_id", pa.string()),
        ("commit_seq", pa.int32()),
        ("sha", pa.string()),
        ("name", pa.string()),  # nullable convenience column
        ("is_obsolete", pa.bool_()),
        ("content_hash", pa.string()),
        ("clauses", pa.list_(_CLAUSE)),
    ]
)

EVENTS = pa.schema(
    [
        ("mondo_id", pa.string()),
        ("commit_seq", pa.int32()),
        ("sha", pa.string()),
        ("predicate", pa.string()),
        ("value", pa.string()),
        ("operation", pa.string()),  # Operation value
    ]
)

BUILD_META = pa.schema(
    [
        ("schema_version", pa.string()),
        ("generator_version", pa.string()),
        ("source_path", pa.string()),
        ("first_commit_seq", pa.int32()),
        ("last_commit_seq", pa.int32()),
        ("n_commits", pa.int32()),
    ]
)

# Filenames within an artifact directory.
FILES = {
    "commits": COMMITS,
    "term_snapshots": TERM_SNAPSHOTS,
    "events": EVENTS,
    "build_meta": BUILD_META,
}


def write_table(rows: list[dict], schema: pa.Schema, out_dir: Path, name: str) -> Path:
    """Write ``rows`` as ``<out_dir>/<name>.parquet`` using ``schema``."""
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{name}.parquet"
    table = pa.Table.from_pylist(rows, schema=schema)
    pq.write_table(table, path, compression="zstd")
    return path
