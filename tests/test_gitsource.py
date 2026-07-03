"""Tests for the single-file git history walk."""

from pathlib import Path

from obohist.gitsource import GitSource

OBO = "src/onto.obo"


def test_walk_is_ordered_oldest_first(obo_repo: Path):
    with GitSource(obo_repo) as src:
        versions = list(src.iter_file_history(OBO))

    assert [v.commit.seq for v in versions] == [0, 1, 2, 3, 4]
    dates = [v.commit.committed_date for v in versions]
    assert dates == sorted(dates)
    assert versions[0].commit.message == "c0 create"
    assert versions[4].commit.message == "c4 add term"


def test_follow_tracks_rename(obo_repo: Path):
    with GitSource(obo_repo) as src:
        paths = [v.path for v in src.iter_file_history(OBO)]

    # File was created as onto.obo, renamed to src/onto.obo at c2.
    assert paths == ["onto.obo", "onto.obo", "src/onto.obo", "src/onto.obo", "src/onto.obo"]


def test_pure_rename_keeps_same_blob(obo_repo: Path):
    with GitSource(obo_repo) as src:
        versions = list(src.iter_file_history(OBO))
        # c1 -> c2 is a content-free rename, so the blob is byte-identical.
        assert versions[1].blob_oid == versions[2].blob_oid
        assert src.read_blob(versions[1].blob_oid) == src.read_blob(versions[2].blob_oid)


def test_read_blob_matches_committed_content(obo_repo: Path):
    with GitSource(obo_repo) as src:
        versions = list(src.iter_file_history(OBO))
        first = src.read_blob(versions[0].blob_oid).decode()
        last = src.read_blob(versions[-1].blob_oid).decode()

    assert "MONDO:0000001" in first
    assert "MONDO:0000002" not in first  # second term added only at c4
    assert "MONDO:0000002" in last
    assert "xref: DOID:4" in last


def test_first_commit_has_no_parent(obo_repo: Path):
    with GitSource(obo_repo) as src:
        versions = list(src.iter_file_history(OBO))
    assert versions[0].commit.parent_sha is None
    assert versions[1].commit.parent_sha == versions[0].commit.sha
