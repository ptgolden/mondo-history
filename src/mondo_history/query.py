"""Query helpers over a history artifact, backed by DuckDB.

Every interface (CLI, future API, hosted app) goes through :class:`HistoryDB` so
they all answer from the same Parquet files. DuckDB reads the Parquet lazily and
can point at local paths or HTTP URLs, so a hosted artifact needs no server.
"""

from dataclasses import dataclass
from pathlib import Path

import duckdb


@dataclass(frozen=True)
class Change:
    """One clause add/remove, joined to the commit that made it."""

    commit_seq: int
    committed_date: object
    sha: str
    pr_number: int | None
    message: str
    operation: str
    predicate: str
    value: str


class HistoryDB:
    def __init__(self, artifact_dir: Path | str):
        self.dir = Path(artifact_dir)
        self.con = duckdb.connect(":memory:")
        for name in ("commits", "term_snapshots", "events"):
            # read_parquet needs a literal path (CREATE VIEW can't bind params);
            # escape single quotes in the path we control.
            literal = str(self.dir / f"{name}.parquet").replace("'", "''")
            self.con.execute(
                f"CREATE VIEW {name} AS SELECT * FROM read_parquet('{literal}')"
            )

    def term_timeline(self, mondo_id: str, predicate: str | None = None) -> list[Change]:
        """All changes to a term, oldest first, optionally one clause kind only."""
        where = "e.mondo_id = ?"
        params: list[object] = [mondo_id]
        if predicate is not None:
            where += " AND e.predicate = ?"
            params.append(predicate)
        rows = self.con.execute(
            f"""
            SELECT c.commit_seq, c.committed_date, c.sha, c.pr_number, c.message,
                   e.operation, e.predicate, e.value
            FROM events e
            JOIN commits c USING (commit_seq)
            WHERE {where}
            ORDER BY c.commit_seq, e.operation, e.predicate, e.value
            """,
            params,
        ).fetchall()
        return [Change(*row) for row in rows]

    def term_at(self, mondo_id: str, commit_seq: int) -> list[tuple[str, str]]:
        """Reconstruct a term's clauses as of ``commit_seq`` (latest snapshot <=)."""
        row = self.con.execute(
            """
            SELECT clauses FROM term_snapshots
            WHERE mondo_id = ? AND commit_seq <= ?
            ORDER BY commit_seq DESC LIMIT 1
            """,
            [mondo_id, commit_seq],
        ).fetchone()
        if row is None:
            return []
        return [(c["predicate"], c["value"]) for c in row[0]]

    def commit_terms(self, sha_prefix: str) -> list[tuple[str, str | None]]:
        """Terms changed together in a commit (matched by sha prefix)."""
        return self.con.execute(
            """
            SELECT DISTINCT e.mondo_id, s.name
            FROM events e
            LEFT JOIN term_snapshots s
              ON s.mondo_id = e.mondo_id AND s.commit_seq = e.commit_seq
            WHERE e.sha LIKE ? || '%'
            ORDER BY e.mondo_id
            """,
            [sha_prefix],
        ).fetchall()

    def close(self) -> None:
        self.con.close()
