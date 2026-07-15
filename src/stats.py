"""Compute commit-quality statistics over a range of commits."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field

from .conventional_commits import ValidationResult


@dataclass
class RepoStats:
    total: int
    compliant: int
    violation_counts: Counter
    by_author: dict[str, "AuthorStats"] = field(default_factory=dict)

    @property
    def percent_compliant(self) -> float:
        if self.total == 0:
            return 100.0
        return round(100.0 * self.compliant / self.total, 1)


@dataclass
class AuthorStats:
    total: int = 0
    compliant: int = 0

    @property
    def percent_compliant(self) -> float:
        if self.total == 0:
            return 100.0
        return round(100.0 * self.compliant / self.total, 1)


def compute_stats(records: list[tuple[str, ValidationResult]]) -> RepoStats:
    """Compute aggregate stats from a list of (author, ValidationResult) pairs."""
    total = len(records)
    compliant = sum(1 for _, result in records if result.valid)
    violation_counts: Counter = Counter()
    by_author: dict[str, AuthorStats] = defaultdict(AuthorStats)

    for author, result in records:
        stats = by_author[author]
        stats.total += 1
        if result.valid:
            stats.compliant += 1
        else:
            for error in result.errors:
                violation_counts[_categorize(error)] += 1

    return RepoStats(
        total=total,
        compliant=compliant,
        violation_counts=violation_counts,
        by_author=dict(by_author),
    )


def _categorize(error_message: str) -> str:
    """Bucket a raw validation error string into a short, stable category label."""
    if "does not match the Conventional Commits format" in error_message:
        return "malformed header"
    if "Unknown commit type" in error_message:
        return "unknown type"
    if "must be lowercase" in error_message:
        return "uppercase type"
    if "Scope must not be empty" in error_message:
        return "empty scope parentheses"
    if "scope is required" in error_message:
        return "missing required scope"
    if "space is required after the colon" in error_message:
        return "bad separator spacing"
    if "Description must not be empty" in error_message:
        return "empty description"
    if "Commit message is empty" in error_message or "header (first line) is empty" in error_message:
        return "empty message"
    return "other"
