"""End-to-end: build an artifact from the fixture repo and query it."""

from pathlib import Path

import duckdb
import pytest

from mondo_history.extract import extract
from mondo_history.gitsource import GitSource
from mondo_history.query import HistoryDB

OBO = "src/onto.obo"


@pytest.fixture
def artifact(obo_repo: Path, tmp_path: Path) -> Path:
    out = tmp_path / "artifact"
    with GitSource(obo_repo) as src:
        extract(src, OBO, out)
    return out


def test_term_events_are_clause_deltas(artifact: Path):
    db = HistoryDB(artifact)
    kinds = [(c.operation, c.predicate) for c in db.term_timeline("MONDO:0000001")]
    db.close()

    # synonym added at c1, xref added at c3.
    assert ("add", "synonym") in kinds
    assert ("add", "xref") in kinds
    # The baseline 'name: disease' predates the window, so it is NOT an event.
    assert ("add", "name") not in kinds


def test_pure_rename_emits_no_events(artifact: Path):
    # c2 (commit_seq 2) is a content-free rename.
    n = duckdb.connect().execute(
        f"SELECT count(*) FROM read_parquet('{artifact}/events.parquet') WHERE commit_seq = 2"
    ).fetchone()[0]
    assert n == 0


def test_reconstruct_state_at_commit(artifact: Path):
    db = HistoryDB(artifact)
    clauses = dict(db.term_at("MONDO:0000001", 4))
    db.close()

    assert clauses["name"] == "disease"
    assert clauses["synonym"] == '"illness" EXACT []'
    assert clauses["xref"] == "DOID:4"


def test_new_term_appears_as_creation(artifact: Path):
    db = HistoryDB(artifact)
    # MONDO:0000002 is created at c4 with just a name.
    changes = [(c.operation, c.predicate) for c in db.term_timeline("MONDO:0000002")]
    before = db.term_at("MONDO:0000002", 0)
    after = dict(db.term_at("MONDO:0000002", 4))
    db.close()

    assert changes == [("add", "name")]
    assert before == []  # did not exist at the baseline
    assert after["name"] == "cancer"


def test_pr_number_parsed_from_message(artifact: Path):
    pr = duckdb.connect().execute(
        f"SELECT pr_number FROM read_parquet('{artifact}/commits.parquet') "
        "WHERE message LIKE 'c2%'"
    ).fetchone()[0]
    assert pr == 42


def test_releases_map_tag_to_commit(artifact: Path):
    db = HistoryDB(artifact)
    rels = db.releases()
    db.close()
    # v1.0 was tagged on c3 (commit_seq 3).
    assert [(tag, seq) for tag, seq, _date in rels] == [("v1.0", 3)]


def test_diff_between_release_and_head(artifact: Path):
    db = HistoryDB(artifact)
    # Between v1.0 (seq 3) and HEAD (seq 4): only the new term created at c4.
    rows = db.changes_between("v1.0", "4")
    db.close()
    assert [(r[0], r[1], r[2]) for r in rows] == [("MONDO:0000002", "add", "name")]


def test_diff_resolves_sha_and_seq_symmetrically(artifact: Path):
    db = HistoryDB(artifact)
    a = db.changes_between("3", "4")
    b = db.changes_between("4", "3")  # order shouldn't matter
    db.close()
    assert a == b


def test_diff_accepts_head(artifact: Path):
    db = HistoryDB(artifact)
    by_head = db.changes_between("v1.0", "HEAD")
    by_seq = db.changes_between("v1.0", "4")
    db.close()
    assert by_head == by_seq


def test_pr_terms_from_message(artifact: Path):
    db = HistoryDB(artifact)
    # c2 "c2 rename (#42)" is a pure rename → no term events → PR touches nothing.
    assert db.pr_terms(42) == []
    db.close()


def test_commit_terms_lists_co_changed(artifact: Path):
    db = HistoryDB(artifact)
    # find c4's sha, then ask what changed in it.
    sha = duckdb.connect().execute(
        f"SELECT sha FROM read_parquet('{artifact}/commits.parquet') WHERE commit_seq = 4"
    ).fetchone()[0]
    terms = dict(db.commit_terms(sha))
    db.close()

    assert "MONDO:0000002" in terms
