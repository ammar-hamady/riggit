"""Scan git history for convention violations, and auto-fix simple ones."""

from __future__ import annotations

from dataclasses import dataclass

from .config import RiggitConfig
from .conventional_commits import ValidationResult, _HEADER_RE, validate_commit_message
from .git import CommitRecord


@dataclass
class ScanEntry:
    commit: CommitRecord
    result: ValidationResult


def scan_history(records: list[CommitRecord], config: RiggitConfig) -> list[ScanEntry]:
    """Validate every commit's message against `config`, newest first."""
    entries = []
    for record in records:
        result = validate_commit_message(
            record.message,
            allowed_types=config.types,
            scope_required=config.scope_required,
            max_header_length=config.max_header_length,
            description_case=config.description_case,
            no_trailing_period=config.no_trailing_period,
        )
        entries.append(ScanEntry(commit=record, result=result))
    return entries


def apply_simple_fixes(message: str, config: RiggitConfig) -> tuple[str, list[str]]:
    """Apply only "safe", mechanical fixes to a commit message header:

    - lowercase the first letter of the description (if `description_case == "lower"`)
    - strip a single trailing period from the description (if `no_trailing_period`)

    Structural problems (unknown type, missing scope, malformed header, ...)
    require human judgement and are left untouched. Returns the possibly
    modified message and a list of human-readable descriptions of what changed.
    """
    if not message or not message.strip():
        return message, []

    lines = message.splitlines()
    header = lines[0]
    match = _HEADER_RE.match(header.rstrip())
    if not match:
        return message, []

    commit_type = match.group("type")
    scope = match.group("scope")
    breaking_bang = match.group("breaking_bang") or ""
    description = match.group("description")
    changes: list[str] = []

    fixed_description = description
    if (
        config.description_case == "lower"
        and fixed_description
        and fixed_description[0].isupper()
    ):
        fixed_description = fixed_description[0].lower() + fixed_description[1:]
        changes.append("lowercased description")

    if config.no_trailing_period and fixed_description.rstrip().endswith("."):
        stripped = fixed_description.rstrip()
        fixed_description = stripped[:-1]
        changes.append("removed trailing period")

    if not changes:
        return message, []

    scope_part = f"({scope})" if scope else ""
    fixed_header = f"{commit_type}{scope_part}{breaking_bang}: {fixed_description}"
    lines[0] = fixed_header
    return "\n".join(lines), changes
