"""Validation logic for the Conventional Commits specification.

Spec reference: https://www.conventionalcommits.org/en/v1.0.0/
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# Standard set of types recognized out of the box. "feat" and "fix" are
# mandated by the spec; the rest come from the widely-used Angular convention
# that most tooling (commitlint, semantic-release, etc.) also ships with.
DEFAULT_TYPES = (
    "feat",
    "fix",
    "build",
    "chore",
    "ci",
    "docs",
    "perf",
    "refactor",
    "revert",
    "style",
    "test",
)

# <type>[optional scope][optional !]: <description>
_HEADER_RE = re.compile(
    r"^(?P<type>[a-zA-Z]+)"
    r"(?:\((?P<scope>[^()\s]+)\))?"
    r"(?P<breaking_bang>!)?"
    r":(?P<sep>\s*)(?P<description>.*)$"
)

_BREAKING_FOOTER_RE = re.compile(r"^BREAKING[ -]CHANGE:\s*.+", re.MULTILINE)


@dataclass
class ValidationResult:
    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    commit_type: str | None = None
    scope: str | None = None
    breaking: bool = False
    description: str | None = None


def validate_commit_message(
    message: str,
    *,
    allowed_types: tuple[str, ...] = DEFAULT_TYPES,
    scope_required: bool = False,
    max_header_length: int | None = 100,
    description_case: str = "lower",
    no_trailing_period: bool = True,
) -> ValidationResult:
    """Validate a full commit message against a Conventional-Commits-shaped convention.

    Only the header (first line) is required to carry the
    `<type>[(scope)][!]: <description>` structure. Later lines are treated as
    body/footer and are scanned for a `BREAKING CHANGE:` footer.

    The structural rules (type/scope/separator syntax) are always enforced.
    `allowed_types`, `scope_required`, `max_header_length`, `description_case`,
    and `no_trailing_period` are configurable so a `.riggitrc` file can adapt
    the convention; they default to standard Conventional Commits behavior.
    """
    errors: list[str] = []
    warnings: list[str] = []

    if message is None or message.strip() == "":
        return ValidationResult(valid=False, errors=["Commit message is empty."])

    lines = message.splitlines()
    header = lines[0].rstrip()

    if not header:
        return ValidationResult(
            valid=False, errors=["Commit message header (first line) is empty."]
        )

    if max_header_length is not None and len(header) > max_header_length:
        warnings.append(
            f"Header is {len(header)} characters long; conventionally kept under {max_header_length}."
        )

    match = _HEADER_RE.match(header)
    if not match:
        return ValidationResult(
            valid=False,
            errors=[
                "Header does not match the Conventional Commits format: "
                "'<type>[(scope)][!]: <description>'. "
                f"Got: {header!r}"
            ],
        )

    commit_type = match.group("type")
    scope = match.group("scope")
    breaking_bang = bool(match.group("breaking_bang"))
    sep = match.group("sep")
    description = match.group("description")

    if commit_type not in allowed_types:
        errors.append(
            f"Unknown commit type '{commit_type}'. Allowed types: "
            f"{', '.join(allowed_types)}."
        )

    if commit_type != commit_type.lower():
        errors.append(f"Commit type '{commit_type}' must be lowercase.")

    if scope is not None and scope.strip() == "":
        errors.append(
            "Scope must not be empty when parentheses are present, e.g. '(api)'."
        )

    if scope_required and not scope:
        errors.append(
            "A scope is required by the current configuration, e.g. 'type(scope): description'."
        )

    if sep != " ":
        errors.append(
            "Exactly one space is required after the colon separating the "
            "type/scope from the description."
        )

    if not description or not description.strip():
        errors.append("Description must not be empty.")
    elif description_case == "lower" and description[0].isupper():
        warnings.append("Description conventionally starts with a lowercase letter.")

    if no_trailing_period and description and description.rstrip().endswith("."):
        warnings.append("Description conventionally does not end with a period.")

    breaking = breaking_bang or bool(_BREAKING_FOOTER_RE.search(message))

    return ValidationResult(
        valid=len(errors) == 0,
        errors=errors,
        warnings=warnings,
        commit_type=commit_type,
        scope=scope,
        breaking=breaking,
        description=description,
    )
