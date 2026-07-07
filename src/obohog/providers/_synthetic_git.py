"""Shared helpers for providers that materialize snapshots into a synthetic git repo.

Two provider families use the same "git init + one commit per snapshot"
shape: :mod:`.github_release` and :mod:`.bioportal`. The mechanical bits
of driving git subprocesses — building the right env, checking for
empty diffs, tagging existing commits when a snapshot has the same
bytes as its predecessor — live here so both providers get consistent
behavior and neither has to re-derive the details.
"""

import os
import subprocess
from pathlib import Path

from rich.console import Console


class GitCommandError(RuntimeError):
    """Raised when a git subprocess exits non-zero. Preserves captured
    stdout/stderr in the message so failures aren't silent."""

    def __init__(self, args: tuple, returncode: int, stdout: str, stderr: str):
        super().__init__(
            f"git {' '.join(args)} failed (exit {returncode})\n"
            f"stdout: {stdout.strip()}\n"
            f"stderr: {stderr.strip()}"
        )


def system_path() -> str:
    """Preserve PATH so subprocess.run finds ``git`` when we override env."""
    return os.environ.get("PATH", "")


def run_git(clone_dir: Path, *args: str, env: dict | None = None) -> str:
    """Run a git subcommand in ``clone_dir``, capture output, return stdout.

    Raises :class:`GitCommandError` on non-zero exit, surfacing stderr so
    failures aren't silent.
    """
    result = subprocess.run(
        ["git", "-C", str(clone_dir), *args],
        capture_output=True, text=True, env=env,
    )
    if result.returncode != 0:
        raise GitCommandError(args, result.returncode, result.stdout, result.stderr)
    return result.stdout


def git_init(clone_dir: Path) -> None:
    """Initialize an empty repo at ``clone_dir`` with ``main`` as the default
    branch. Creates the directory first if needed."""
    clone_dir.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        ["git", "init", "--initial-branch=main", "--quiet", str(clone_dir)],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise GitCommandError(
            ("init", str(clone_dir)),
            result.returncode, result.stdout, result.stderr,
        )


def list_local_tags(clone_dir: Path) -> set[str]:
    """Every tag currently in the repo, as a set. Empty on a fresh clone."""
    stdout = run_git(clone_dir, "tag", "--list")
    return {line.strip() for line in stdout.splitlines() if line.strip()}


def head_sha(clone_dir: Path) -> str | None:
    """Current HEAD sha, or ``None`` if the repo has no commits yet."""
    result = subprocess.run(
        ["git", "-C", str(clone_dir), "rev-parse", "--verify", "HEAD"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def nothing_to_commit(clone_dir: Path) -> bool:
    """True if ``git add`` staged no changes vs. the current HEAD.

    Used to detect rolling / republished snapshots whose content is
    byte-identical to what's already committed: instead of failing on an
    empty commit, callers can tag the existing HEAD and move on.
    """
    result = subprocess.run(
        ["git", "-C", str(clone_dir), "diff", "--cached", "--quiet"],
        env={"PATH": system_path()},
    )
    # `diff --quiet` exits 0 for no diff, 1 for diff, >1 for real errors.
    return result.returncode == 0


def commit_or_tag_head(
    clone_dir: Path,
    tag: str,
    *,
    author_name: str,
    author_email: str,
    committed_date: str,
    message: str,
    console: Console,
) -> None:
    """Commit whatever ``git add`` staged as a tagged snapshot.

    If nothing was staged (byte-identical content), tag the existing
    HEAD instead — this preserves the tag-to-content association without
    an empty commit. Log a one-liner so the user sees why.
    """
    if nothing_to_commit(clone_dir):
        console.print(
            f"  [dim]· {tag} matches previous snapshot content; "
            "tagging existing commit instead of adding an empty one[/]"
        )
        sha = head_sha(clone_dir)
        if sha is not None:
            run_git(clone_dir, "tag", tag, sha)
        # If HEAD doesn't exist yet (would only happen if the first
        # snapshot we saw was itself empty against an empty repo,
        # which is nonsensical), silently drop it.
        return

    env = {
        "GIT_AUTHOR_NAME": author_name,
        "GIT_AUTHOR_EMAIL": author_email,
        "GIT_COMMITTER_NAME": author_name,
        "GIT_COMMITTER_EMAIL": author_email,
        "GIT_AUTHOR_DATE": committed_date,
        "GIT_COMMITTER_DATE": committed_date,
        "PATH": system_path(),
    }
    run_git(clone_dir, "commit", "--quiet", "-m", message, env=env)
    run_git(clone_dir, "tag", tag)
