"""Install/uninstall the riggit `commit-msg` git hook."""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

from .git import GitError, get_git_dir

HOOK_NAME = "commit-msg"
MARKER = "# managed-by: riggit"

HOOK_TEMPLATE = f"""#!/usr/bin/env bash
{MARKER}
# Installed by `riggit install`. Remove with `riggit uninstall`.
riggit lint --message-file "$1"
"""


class HookError(RuntimeError):
    """Raised when the commit-msg hook cannot be installed/uninstalled."""


def _hook_path(repo_path: str | Path) -> Path:
    try:
        git_dir = get_git_dir(repo_path)
    except GitError as exc:
        raise HookError(str(exc)) from exc
    return git_dir / "hooks" / HOOK_NAME


def install_hook(repo_path: str | Path = ".", *, force: bool = False) -> Path:
    """Write the commit-msg hook, returning its path. Refuses to clobber a
    pre-existing, non-riggit hook unless `force` is set."""
    hook_path = _hook_path(repo_path)
    hook_path.parent.mkdir(parents=True, exist_ok=True)

    if hook_path.exists():
        existing = hook_path.read_text()
        if MARKER not in existing and not force:
            raise HookError(
                f"A commit-msg hook already exists at {hook_path} and was not "
                "installed by riggit. Re-run with --force to overwrite it."
            )

    hook_path.write_text(HOOK_TEMPLATE)
    mode = hook_path.stat().st_mode
    hook_path.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return hook_path


def uninstall_hook(repo_path: str | Path = ".", *, force: bool = False) -> bool:
    """Remove the commit-msg hook if riggit installed it. Returns whether a
    file was removed. Refuses to remove a non-riggit hook unless `force` is
    set."""
    hook_path = _hook_path(repo_path)
    if not hook_path.exists():
        return False

    existing = hook_path.read_text()
    if MARKER not in existing and not force:
        raise HookError(
            f"The commit-msg hook at {hook_path} was not installed by riggit. "
            "Re-run with --force to remove it anyway."
        )

    hook_path.unlink()
    return True


# --- Global hook mechanisms -------------------------------------------------
#
# Two distinct, independent mechanisms for applying the hook beyond a single
# repo, mirroring git's own two ways of doing this:
#
# `--global` uses `core.hooksPath` (git >= 2.9): a single directory of hooks
# that git consults for *every* repository unless a repo sets its own
# `core.hooksPath` locally. Takes effect immediately, including for existing
# repos.
#
# `--template` uses `init.templateDir`: a directory whose contents git copies
# into `.git/` whenever `git init`/`git clone` runs. Only affects
# repositories created *after* this is configured.


def _global_hooks_dir() -> Path:
    override = os.environ.get("RIGGIT_GLOBAL_HOOKS_DIR")
    if override:
        return Path(override)
    return Path.home() / ".riggit" / "hooks"


def _template_dir() -> Path:
    override = os.environ.get("RIGGIT_GIT_TEMPLATE_DIR")
    if override:
        return Path(override)
    return Path.home() / ".git-templates"


def _write_hook(hook_path: Path, *, force: bool) -> None:
    hook_path.parent.mkdir(parents=True, exist_ok=True)
    if hook_path.exists():
        existing = hook_path.read_text()
        if MARKER not in existing and not force:
            raise HookError(
                f"A commit-msg hook already exists at {hook_path} and was not "
                "installed by riggit. Re-run with --force to overwrite it."
            )
    hook_path.write_text(HOOK_TEMPLATE)
    mode = hook_path.stat().st_mode
    hook_path.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def install_global_hook(*, force: bool = False) -> tuple[Path, Path]:
    """Install the hook via `core.hooksPath`, applying to all repositories
    immediately (unless a repo overrides `core.hooksPath` locally).

    Returns (hooks_dir, hook_path).
    """
    hooks_dir = _global_hooks_dir()
    hook_path = hooks_dir / HOOK_NAME
    _write_hook(hook_path, force=force)
    _run_git_config(["core.hooksPath", str(hooks_dir)])
    return hooks_dir, hook_path


def uninstall_global_hook(*, force: bool = False) -> bool:
    """Remove the global `core.hooksPath` hook and unset the config. Returns
    whether anything was removed."""
    hooks_dir = _global_hooks_dir()
    hook_path = hooks_dir / HOOK_NAME
    removed = False
    if hook_path.exists():
        existing = hook_path.read_text()
        if MARKER not in existing and not force:
            raise HookError(
                f"The hook at {hook_path} was not installed by riggit. Re-run with --force to remove it anyway."
            )
        hook_path.unlink()
        removed = True
    _run_git_config(["--unset", "core.hooksPath"], ignore_missing=True)
    return removed


def install_template_hook(*, force: bool = False) -> tuple[Path, Path]:
    """Install the hook into git's global template directory
    (`init.templateDir`), so it's copied into every repo created afterward
    via `git init`/`git clone`. Does not affect already-existing repos.

    Returns (template_dir, hook_path).
    """
    template_dir = _template_dir()
    hook_path = template_dir / "hooks" / HOOK_NAME
    _write_hook(hook_path, force=force)
    _run_git_config(["init.templateDir", str(template_dir)])
    return template_dir, hook_path


def uninstall_template_hook(*, force: bool = False) -> bool:
    """Remove the hook from git's global template directory and unset the
    config. Returns whether anything was removed."""
    template_dir = _template_dir()
    hook_path = template_dir / "hooks" / HOOK_NAME
    removed = False
    if hook_path.exists():
        existing = hook_path.read_text()
        if MARKER not in existing and not force:
            raise HookError(
                f"The hook at {hook_path} was not installed by riggit. Re-run with --force to remove it anyway."
            )
        hook_path.unlink()
        removed = True
    _run_git_config(["--unset", "init.templateDir"], ignore_missing=True)
    return removed


def _run_git_config(args: list[str], *, ignore_missing: bool = False) -> None:
    # RIGGIT_GIT_CONFIG_GLOBAL lets tests (and anything else that shouldn't
    # touch the real user's ~/.gitconfig) redirect these writes to a scratch
    # file via `git config --file <path>` instead of `--global`.
    override = os.environ.get("RIGGIT_GIT_CONFIG_GLOBAL")
    scope = ["--file", override] if override else ["--global"]
    result = subprocess.run(["git", "config", *scope, *args], capture_output=True, text=True, check=False)
    if result.returncode != 0 and not ignore_missing:
        raise HookError(result.stderr.strip() or f"git config {' '.join(args)} failed.")
