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
        for name in ("commits", "term_snapshots", "events", "releases"):
            parquet = self.dir / f"{name}.parquet"
            if not parquet.exists():
                continue  # older artifacts may lack newer tables (e.g. releases)
            # read_parquet needs a literal path (CREATE VIEW can't bind params);
            # escape single quotes in the path we control.
            literal = str(parquet).replace("'", "''")
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

    def pr_terms(self, pr_number: int) -> list[tuple[str, str | None]]:
        """Terms changed by any commit belonging to a pull request."""
        return self.con.execute(
            """
            SELECT DISTINCT e.mondo_id, s.name
            FROM events e
            JOIN commits c USING (commit_seq)
            LEFT JOIN term_snapshots s
              ON s.mondo_id = e.mondo_id AND s.commit_seq = e.commit_seq
            WHERE c.pr_number = ?
            ORDER BY e.mondo_id
            """,
            [pr_number],
        ).fetchall()

    def resolve_ref(self, ref: str) -> int:
        """Resolve HEAD, a release tag, a commit_seq, or a sha prefix to a seq."""
        if ref.upper() == "HEAD":
            return self.con.execute("SELECT max(commit_seq) FROM commits").fetchone()[0]
        row = self.con.execute(
            "SELECT commit_seq FROM releases WHERE tag = ?", [ref]
        ).fetchone() if self._has_releases() else None
        if row is not None:
            return row[0]
        if ref.isdigit():
            return int(ref)
        row = self.con.execute(
            "SELECT commit_seq FROM commits WHERE sha LIKE ? || '%' ORDER BY commit_seq LIMIT 1",
            [ref],
        ).fetchone()
        if row is None:
            raise KeyError(f"could not resolve ref {ref!r} to a commit")
        return row[0]

    def changes_between(
        self, ref_a: str, ref_b: str, mondo_id: str | None = None
    ) -> list[tuple[str, str, str, str, int, int | None]]:
        """Clause changes in ``(lo, hi]`` where lo/hi are the two refs, ordered.

        Returns ``(mondo_id, operation, predicate, value, commit_seq, pr_number)``.
        """
        lo, hi = sorted((self.resolve_ref(ref_a), self.resolve_ref(ref_b)))
        where = "e.commit_seq > ? AND e.commit_seq <= ?"
        params: list[object] = [lo, hi]
        if mondo_id is not None:
            where += " AND e.mondo_id = ?"
            params.append(mondo_id)
        return self.con.execute(
            f"""
            SELECT e.mondo_id, e.operation, e.predicate, e.value, e.commit_seq, c.pr_number
            FROM events e
            JOIN commits c USING (commit_seq)
            WHERE {where}
            ORDER BY e.mondo_id, e.commit_seq, e.operation, e.predicate
            """,
            params,
        ).fetchall()

    def releases(self) -> list[tuple[str, int, object]]:
        if not self._has_releases():
            return []
        return self.con.execute(
            "SELECT tag, commit_seq, date FROM releases ORDER BY commit_seq"
        ).fetchall()

    def _has_releases(self) -> bool:
        return (self.dir / "releases.parquet").exists()

    def close(self) -> None:
        self.con.close()
