"""Scaffold a `.riggitrc` file describing the active conventions."""

from __future__ import annotations

from pathlib import Path

from .config import CONFIG_FILENAME, DEFAULT_CONFIG

_TYPES_YAML = "\n".join(f"  - {t}" for t in DEFAULT_CONFIG["types"])

TEMPLATE = f"""# .riggitrc — riggit commit-message conventions for this directory/repo.
#
# riggit searches this directory and its parents for a `.riggitrc` file.
# If none is found, it falls back to standard Conventional Commits rules —
# which is exactly what this generated file encodes by default. Edit any
# field below to change the convention, or delete the file to go back to
# the default.

# Commit types allowed as the `<type>` in `<type>(scope): description`.
types:
{_TYPES_YAML}

# Require a `(scope)` on every commit, e.g. `feat(api): add endpoint`.
scope_required: {str(DEFAULT_CONFIG["scope_required"]).lower()}

# Warn when the header (first line) is longer than this many characters.
# Set to `null` to disable the check.
max_header_length: {DEFAULT_CONFIG["max_header_length"]}

# "lower" warns when the description doesn't start with a lowercase letter.
# "any" disables the check.
description_case: {DEFAULT_CONFIG["description_case"]}

# Warn when the description ends with a trailing period.
no_trailing_period: {str(DEFAULT_CONFIG["no_trailing_period"]).lower()}
"""


class InitError(RuntimeError):
    """Raised when `.riggitrc` cannot be created."""


def init_config_file(repo_path: str | Path = ".", *, force: bool = False) -> Path:
    directory = Path(repo_path)
    if not directory.exists():
        raise InitError(f"'{repo_path}' does not exist.")
    if not directory.is_dir():
        raise InitError(f"'{repo_path}' is not a directory.")

    path = directory / CONFIG_FILENAME
    if path.exists() and not force:
        raise InitError(f"{path} already exists. Re-run with --force to overwrite it.")

    path.write_text(TEMPLATE)
    return path
