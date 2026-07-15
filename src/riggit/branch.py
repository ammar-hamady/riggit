"""Extract a ticket/issue key (e.g. Jira-style `PROJ-123`) from a branch name."""

from __future__ import annotations

import re

# Matches Jira/Linear-style ticket keys: one or more uppercase letters
# (optionally mixed with digits after the first) followed by a hyphen and a
# number, e.g. "DT-123", "PROJ-42". Case-insensitive so "feature/dt-123"
# still matches.
DEFAULT_TICKET_PATTERN = r"\b[A-Za-z][A-Za-z0-9]*-[0-9]+\b"


class TicketExtractionError(RuntimeError):
    """Raised when a custom extraction pattern is invalid."""


def extract_ticket(branch_name: str, pattern: str | None = None) -> str | None:
    """Return the first ticket key found in `branch_name`, or None.

    `pattern` overrides the default regex. If the pattern defines a group
    named `ticket`, that group's value is returned; otherwise the first
    capturing group is used if present, else the whole match.
    """
    try:
        regex = re.compile(pattern or DEFAULT_TICKET_PATTERN, re.IGNORECASE)
    except re.error as exc:
        raise TicketExtractionError(f"Invalid --format pattern: {exc}") from exc

    match = regex.search(branch_name)
    if not match:
        return None

    groups = match.groupdict()
    if "ticket" in groups and groups["ticket"] is not None:
        return groups["ticket"]
    if match.groups():
        return match.group(1)
    return match.group(0)
