"""Thin wrapper around the `git` executable.

Kept isolated so the rest of the tool doesn't need to know how commit data is
fetched — this is the seam to swap out if riggit ever needs to support
another VCS or a non-CLI backend.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


class GitError(RuntimeError):
    """Raised when a git operation fails or git/the repo is unavailable."""


def ensure_git_available() -> None:
    if shutil.which("git") is None:
        raise GitError(
            "git executable not found on PATH. Install git to use riggit."
        )


def get_last_commit_message(repo_path: str | Path = ".") -> str:
    """Return the full message (subject + body) of the most recent commit."""
    ensure_git_available()
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_path), "log", "-1", "--pretty=%B"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:  # pragma: no cover - defensive
        raise GitError(f"Failed to run git: {exc}") from exc

    if result.returncode != 0:
        stderr = result.stderr.strip()
        if "does not have any commits yet" in stderr or "unknown revision" in stderr:
            raise GitError("The repository has no commits yet.")
        if "not a git repository" in stderr:
            raise GitError(f"'{repo_path}' is not a git repository.")
        raise GitError(stderr or "git log failed for an unknown reason.")

    return result.stdout.rstrip("\n")


def get_git_dir(repo_path: str | Path = ".") -> Path:
    """Return the absolute path to the repo's `.git` directory.

    Uses `git rev-parse --git-dir` rather than assuming `<repo>/.git` so it
    also works correctly for worktrees and submodules, where `.git` is a
    file pointing elsewhere.
    """
    ensure_git_available()
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_path), "rev-parse", "--git-dir"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:  # pragma: no cover - defensive
        raise GitError(f"Failed to run git: {exc}") from exc

    if result.returncode != 0:
        stderr = result.stderr.strip()
        if "not a git repository" in stderr:
            raise GitError(f"'{repo_path}' is not a git repository.")
        raise GitError(stderr or "git rev-parse --git-dir failed for an unknown reason.")

    git_dir = Path(result.stdout.strip())
    if not git_dir.is_absolute():
        git_dir = Path(repo_path).resolve() / git_dir
    return git_dir


def get_current_branch(repo_path: str | Path = ".") -> str:
    """Return the current branch name (e.g. 'feature/DT-123')."""
    ensure_git_available()
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_path), "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:  # pragma: no cover - defensive
        raise GitError(f"Failed to run git: {exc}") from exc

    if result.returncode != 0:
        stderr = result.stderr.strip()
        if "not a git repository" in stderr:
            raise GitError(f"'{repo_path}' is not a git repository.")
        raise GitError(stderr or "git rev-parse --abbrev-ref HEAD failed for an unknown reason.")

    branch = result.stdout.strip()
    if branch == "HEAD":
        raise GitError("Not currently on a branch (detached HEAD).")
    return branch


_RECORD_SEP = "\x1e"
_FIELD_SEP = "\x1f"


@dataclass
class CommitRecord:
    commit_hash: str
    author: str
    message: str

    @property
    def short_hash(self) -> str:
        return self.commit_hash[:7]

    @property
    def header(self) -> str:
        return self.message.splitlines()[0] if self.message else ""


def resolve_range(since: str | None, until: str | None) -> str | None:
    """Build a git revision range from --since/--until refs.

    Returns None to mean "default history reachable from HEAD".
    """
    if since and until:
        return f"{since}..{until}"
    if since:
        return f"{since}..HEAD"
    if until:
        return until
    return None


def list_commits(
    repo_path: str | Path = ".",
    *,
    since: str | None = None,
    until: str | None = None,
) -> list[CommitRecord]:
    """List commits (newest first) in the given range, with hash/author/message."""
    ensure_git_available()
    rev_range = resolve_range(since, until)
    cmd = ["git", "-C", str(repo_path), "log", f"--pretty=format:{_RECORD_SEP}%H{_FIELD_SEP}%an{_FIELD_SEP}%B"]
    if rev_range:
        cmd.append(rev_range)

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    except OSError as exc:  # pragma: no cover - defensive
        raise GitError(f"Failed to run git: {exc}") from exc

    if result.returncode != 0:
        stderr = result.stderr.strip()
        if "not a git repository" in stderr:
            raise GitError(f"'{repo_path}' is not a git repository.")
        if "unknown revision" in stderr or "bad revision" in stderr:
            raise GitError(f"Unknown revision in range '{rev_range}': {stderr}")
        raise GitError(stderr or "git log failed for an unknown reason.")

    records: list[CommitRecord] = []
    for chunk in result.stdout.split(_RECORD_SEP):
        if not chunk:
            continue
        parts = chunk.split(_FIELD_SEP, 2)
        if len(parts) != 3:
            continue
        commit_hash, author, message = parts
        records.append(CommitRecord(commit_hash=commit_hash, author=author, message=message.rstrip("\n")))
    return records


def run_filter_branch(repo_path: str | Path, rev_range: str | None, msg_filter_cmd: str) -> None:
    """Rewrite commit messages in `rev_range` using `git filter-branch --msg-filter`.

    This rewrites commit history (new SHAs for every rewritten commit and its
    descendants) and is inherently destructive/irreversible without the
    `refs/original/` backup git filter-branch leaves behind. Callers must gate
    this behind an explicit user confirmation.
    """
    ensure_git_available()
    cmd = [
        "git",
        "-C",
        str(repo_path),
        "filter-branch",
        "-f",
        "--msg-filter",
        msg_filter_cmd,
        "--",
        rev_range or "HEAD",
    ]
    env = {**os.environ, "FILTER_BRANCH_SQUELCH_WARNING": "1"}
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False, env=env)
    except OSError as exc:  # pragma: no cover - defensive
        raise GitError(f"Failed to run git filter-branch: {exc}") from exc

    if result.returncode != 0:
        raise GitError(result.stderr.strip() or "git filter-branch failed for an unknown reason.")
