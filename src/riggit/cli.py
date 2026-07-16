"""Command-line entry point for riggit."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from . import __version__
from .branch import DEFAULT_TICKET_PATTERN, TicketExtractionError, extract_ticket
from .config import (
    CONFIG_KEYS,
    ConfigError,
    effective_values_for_file,
    get_raw_config_value,
    global_config_path,
    load_config,
    set_config_value,
)
from .conventional_commits import validate_commit_message
from .git import GitError, get_current_branch, get_last_commit_message, list_commits, run_filter_branch
from .hooks import (
    HOOK_TEMPLATE,
    HookError,
    install_global_hook,
    install_hook,
    install_template_hook,
    uninstall_global_hook,
    uninstall_hook,
    uninstall_template_hook,
)
from .init import InitError, init_config_file
from .scan import apply_simple_fixes, scan_history
from .stats import compute_stats

_SOURCE_LABELS = {
    "commit": "last commit",
    "message": "message",
    "message-file": "message file",
}


def _read_message_source(args: argparse.Namespace) -> tuple[str, str]:
    """Return (message, source) where source is one of commit/message/message-file."""
    if args.message is not None:
        return args.message, "message"
    if args.message_file is not None:
        try:
            content = Path(args.message_file).read_text()
        except OSError as exc:
            raise GitError(f"Failed to read message file '{args.message_file}': {exc}") from exc
        return content, "message-file"
    message = get_last_commit_message(args.repo)
    return message, "commit"


def _emit_error(fmt: str, message: str) -> int:
    if fmt == "json":
        print(json.dumps({"valid": False, "error": message}, indent=2))
    else:
        print(f"riggit: error: {message}", file=sys.stderr)
    return 2


def _cmd_lint(args: argparse.Namespace) -> int:
    try:
        message, source = _read_message_source(args)
    except GitError as exc:
        return _emit_error(args.format, str(exc))

    try:
        config = load_config(args.repo)
    except ConfigError as exc:
        return _emit_error(args.format, str(exc))

    result = validate_commit_message(
        message,
        allowed_types=config.types,
        scope_required=config.scope_required,
        max_header_length=config.max_header_length,
        description_case=config.description_case,
        no_trailing_period=config.no_trailing_period,
    )
    header = message.splitlines()[0] if message else ""

    if args.format == "json":
        payload = {
            "valid": result.valid,
            "source": source,
            "header": header,
            "type": result.commit_type,
            "scope": result.scope,
            "breaking": result.breaking,
            "description": result.description,
            "errors": result.errors,
            "warnings": result.warnings,
            "config": config.source or "default (conventional commits)",
        }
        print(json.dumps(payload, indent=2))
        return 0 if result.valid else 1

    print(f'Checking {_SOURCE_LABELS[source]}: "{header}"')
    if config.source:
        print(f"Using config: {config.source}")

    if result.valid:
        print("✔ Commit message follows the configured convention.")
        details = f"  type: {result.commit_type}"
        if result.scope:
            details += f", scope: {result.scope}"
        if result.breaking:
            details += ", BREAKING CHANGE"
        print(details)
    else:
        print("✘ Commit message does NOT follow the configured convention.")
        for error in result.errors:
            print(f"  - {error}")

    for warning in result.warnings:
        print(f"  ! {warning}")

    return 0 if result.valid else 1


def _cmd_install(args: argparse.Namespace) -> int:
    try:
        hook_path = install_hook(args.repo, force=args.force)
    except HookError as exc:
        print(f"riggit: error: {exc}", file=sys.stderr)
        return 2
    print(f"Installed commit-msg hook at {hook_path}")
    return 0


def _cmd_uninstall(args: argparse.Namespace) -> int:
    try:
        removed = uninstall_hook(args.repo, force=args.force)
    except HookError as exc:
        print(f"riggit: error: {exc}", file=sys.stderr)
        return 2
    if removed:
        print("Removed riggit commit-msg hook.")
    else:
        print("No riggit commit-msg hook found; nothing to do.")
    return 0


def _cmd_init(args: argparse.Namespace) -> int:
    try:
        path = init_config_file(args.repo, force=args.force)
    except InitError as exc:
        print(f"riggit: error: {exc}", file=sys.stderr)
        return 2
    print(f"Created {path}")
    return 0


def _cmd_scan(args: argparse.Namespace) -> int:
    try:
        config = load_config(args.repo)
        records = list_commits(args.repo, since=args.since, until=args.until)
    except (GitError, ConfigError) as exc:
        return _emit_error(args.format, str(exc))

    entries = scan_history(records, config)
    errored = [e for e in entries if e.result.errors]
    warned_only = [e for e in entries if not e.result.errors and e.result.warnings]

    if args.fix:
        return _cmd_scan_fix(args, config, entries)

    if args.format == "json":
        payload = {
            "total": len(entries),
            "violations": len(errored),
            "with_warnings_only": len(warned_only),
            "commits": [
                {
                    "hash": e.commit.commit_hash,
                    "header": e.commit.header,
                    "author": e.commit.author,
                    "valid": e.result.valid,
                    "errors": e.result.errors,
                    "warnings": e.result.warnings,
                }
                for e in entries
            ],
        }
        print(json.dumps(payload, indent=2))
        return 0 if not errored else 1

    if not entries:
        print("No commits found in range.")
        return 0

    for entry in errored:
        print(f"✘ {entry.commit.short_hash}  {entry.commit.header!r}")
        for error in entry.result.errors:
            print(f"  - {error}")

    for entry in warned_only:
        print(f"⚠ {entry.commit.short_hash}  {entry.commit.header!r}")
        for warning in entry.result.warnings:
            print(f"  ! {warning}")

    print(
        f"\n{len(errored)} of {len(entries)} commit(s) violate the convention"
        f" ({len(warned_only)} more have warnings only)."
    )
    return 0 if not errored else 1


def _cmd_scan_fix(args: argparse.Namespace, config, entries) -> int:
    fixable = []
    for entry in entries:
        fixed_message, changes = apply_simple_fixes(entry.commit.message, config)
        if changes:
            fixable.append((entry.commit, changes))

    if not fixable:
        print("No auto-fixable violations found (only mechanical fixes are applied: "
              "lowercasing the description, removing a trailing period).")
        return 0

    print(f"{len(fixable)} commit(s) can be auto-fixed:")
    for commit, changes in fixable:
        print(f"  {commit.short_hash}  {commit.header!r}  -> {', '.join(changes)}")

    if not args.force:
        print(
            "\nThis rewrites git history (new commit hashes for these commits and "
            "everything after them). Re-run with --force to apply. A backup ref "
            "under refs/original/ is kept by git for recovery."
        )
        return 1

    from .git import resolve_range

    rev_range = resolve_range(args.since, args.until)
    repo_abspath = str(Path(args.repo).resolve())
    filter_cmd = f'RIGGIT_CONFIG_REPO="{repo_abspath}" riggit _fix-message'
    try:
        run_filter_branch(args.repo, rev_range, filter_cmd)
    except GitError as exc:
        print(f"riggit: error: {exc}", file=sys.stderr)
        return 2

    print(f"Rewrote {len(fixable)} commit message(s).")
    return 0


def _cmd_fix_message(args: argparse.Namespace) -> int:
    # Hidden command used internally as the `git filter-branch --msg-filter`
    # callback: reads the original message on stdin, writes the fixed
    # message to stdout. Not part of the public CLI surface.
    import os

    message = sys.stdin.read()
    repo = os.environ.get("RIGGIT_CONFIG_REPO", ".")
    try:
        config = load_config(repo)
    except ConfigError:
        sys.stdout.write(message)
        return 0
    fixed_message, _changes = apply_simple_fixes(message, config)
    sys.stdout.write(fixed_message)
    return 0


def _cmd_stats(args: argparse.Namespace) -> int:
    try:
        config = load_config(args.repo)
        records = list_commits(args.repo, since=args.since, until=args.until)
    except (GitError, ConfigError) as exc:
        return _emit_error(args.format, str(exc))

    entries = scan_history(records, config)
    stats = compute_stats([(e.commit.author, e.result) for e in entries])

    if args.format == "json":
        payload = {
            "total": stats.total,
            "compliant": stats.compliant,
            "percent_compliant": stats.percent_compliant,
            "violations_by_category": dict(stats.violation_counts),
            "by_author": {
                author: {
                    "total": s.total,
                    "compliant": s.compliant,
                    "percent_compliant": s.percent_compliant,
                }
                for author, s in stats.by_author.items()
            },
        }
        print(json.dumps(payload, indent=2))
        return 0

    print(f"Commits analyzed: {stats.total}")
    print(f"Compliant: {stats.compliant} ({stats.percent_compliant}%)")

    if stats.violation_counts:
        print("\nMost common violations:")
        for category, count in stats.violation_counts.most_common():
            print(f"  {count:>4}  {category}")

    if stats.by_author:
        print("\nBy author:")
        for author, s in sorted(stats.by_author.items(), key=lambda kv: kv[1].total, reverse=True):
            print(f"  {author}: {s.compliant}/{s.total} ({s.percent_compliant}%)")

    return 0


def _cmd_hook(args: argparse.Namespace) -> int:
    if not args.install and not args.uninstall:
        print(HOOK_TEMPLATE, end="")
        return 0

    if args.install and args.uninstall:
        print("riggit: error: --install and --uninstall are mutually exclusive.", file=sys.stderr)
        return 2

    if args.global_:
        action = install_global_hook if args.install else uninstall_global_hook
        label = "global (core.hooksPath)"
    elif args.template:
        action = install_template_hook if args.install else uninstall_template_hook
        label = "template (init.templateDir)"
    else:
        print("riggit: error: --install/--uninstall require --global or --template.", file=sys.stderr)
        return 2

    try:
        result = action(force=args.force)
    except HookError as exc:
        print(f"riggit: error: {exc}", file=sys.stderr)
        return 2

    if args.install:
        _, hook_path = result
        print(f"Installed {label} commit-msg hook at {hook_path}")
    else:
        if result:
            print(f"Removed {label} commit-msg hook.")
        else:
            print(f"No {label} commit-msg hook found; nothing to do.")
    return 0


def _cmd_config(args: argparse.Namespace) -> int:
    target_path = global_config_path() if args.global_ else Path(args.repo) / ".riggitrc"

    if args.list:
        if args.global_:
            values = effective_values_for_file(target_path)
        else:
            config = load_config(args.repo)
            values = {
                "types": list(config.types),
                "scope_required": config.scope_required,
                "max_header_length": config.max_header_length,
                "description_case": config.description_case,
                "no_trailing_period": config.no_trailing_period,
            }
        for key, value in values.items():
            display = ",".join(value) if isinstance(value, list) else value
            print(f"{key} = {display}")
        return 0

    if args.key is None:
        print("riggit: error: provide a key (and optionally a value), or use --list.", file=sys.stderr)
        return 2

    if args.value is None:
        if args.key not in CONFIG_KEYS:
            print(f"riggit: error: unknown config key '{args.key}'. Valid keys: {', '.join(CONFIG_KEYS)}.", file=sys.stderr)
            return 2
        if args.global_:
            value = get_raw_config_value(target_path, args.key)
        else:
            config = load_config(args.repo)
            value = getattr(config, args.key)
        if value is None:
            print("(unset)")
            return 1
        print(",".join(value) if isinstance(value, list) else value)
        return 0

    try:
        set_config_value(target_path, args.key, args.value)
    except ConfigError as exc:
        print(f"riggit: error: {exc}", file=sys.stderr)
        return 2
    print(f"Set {args.key} in {target_path}")
    return 0


def _cmd_branch(args: argparse.Namespace) -> int:
    try:
        branch = get_current_branch(args.repo)
    except GitError as exc:
        return _emit_error(args.format, str(exc))

    ticket = None
    if args.extract:
        try:
            ticket = extract_ticket(branch, args.format_pattern)
        except TicketExtractionError as exc:
            return _emit_error(args.format, str(exc))

    if args.format == "json":
        print(json.dumps({"branch": branch, "ticket": ticket}, indent=2))
        return 0 if (not args.extract or ticket) else 1

    if not args.extract:
        print(branch)
        return 0

    if ticket:
        print(ticket)
        return 0

    print(f"riggit: no ticket key found in branch '{branch}'.", file=sys.stderr)
    return 1


def _cmd_commit(args: argparse.Namespace) -> int:
    message = args.message
    ticket = None

    if args.auto:
        try:
            branch = get_current_branch(args.repo)
        except GitError as exc:
            print(f"riggit: error: {exc}", file=sys.stderr)
            return 2
        ticket = extract_ticket(branch, args.format_pattern)
        if ticket and ticket not in message:
            message = f"{message}\n\nRefs: {ticket}"

    try:
        config = load_config(args.repo)
    except ConfigError as exc:
        print(f"riggit: error: {exc}", file=sys.stderr)
        return 2

    result = validate_commit_message(
        message,
        allowed_types=config.types,
        scope_required=config.scope_required,
        max_header_length=config.max_header_length,
        description_case=config.description_case,
        no_trailing_period=config.no_trailing_period,
    )
    if not result.valid:
        print("riggit: refusing to commit; message does not follow the configured convention:", file=sys.stderr)
        for error in result.errors:
            print(f"  - {error}", file=sys.stderr)
        return 1

    if args.auto and ticket:
        print(f"Injected ticket '{ticket}' from branch into commit message.")

    proc = subprocess.run(["git", "-C", args.repo, "commit", "-m", message])
    return proc.returncode


def build_parser() -> argparse.ArgumentParser:
    # Shared option groups, added as `parents` to both the top-level parser
    # and relevant subparsers. --format is only defined on the subparsers
    # (not the top-level parser) since argparse subparser defaults would
    # otherwise clobber a value already parsed at the top level -- i.e.
    # `riggit --format json lint` does NOT reliably propagate `format` to
    # the `lint` subcommand. `riggit lint --format json` is the supported form.
    format_parent = argparse.ArgumentParser(add_help=False)
    format_parent.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Output format for the command's results (default: text).",
    )

    repo_parent = argparse.ArgumentParser(add_help=False)
    repo_parent.add_argument(
        "--repo",
        default=".",
        help="Path to the git repository / directory to operate on (defaults to the current directory).",
    )

    parser = argparse.ArgumentParser(
        prog="riggit",
        description="A git convention checker: validates commit messages against Conventional Commits (or your own .riggitrc).",
    )
    parser.add_argument("-v", "--version", action="version", version=f"riggit {__version__}")

    subparsers = parser.add_subparsers(dest="command", required=True)

    lint_parser = subparsers.add_parser(
        "lint",
        parents=[format_parent, repo_parent],
        help="Lint a commit message against the active convention.",
    )
    message_group = lint_parser.add_mutually_exclusive_group()
    message_group.add_argument(
        "-m",
        "--message",
        default=None,
        help='Lint this message directly instead of the last commit, e.g. riggit lint -m "fix: description".',
    )
    message_group.add_argument(
        "--message-file",
        default=None,
        # Used internally by the installed commit-msg hook (git passes the
        # commit message as a file path); hidden from --help to keep the
        # user-facing surface to -m/--message.
        help=argparse.SUPPRESS,
    )
    lint_parser.set_defaults(func=_cmd_lint)

    install_parser = subparsers.add_parser(
        "install",
        parents=[repo_parent],
        help="Install a git commit-msg hook that runs riggit lint automatically.",
    )
    install_parser.add_argument("--force", action="store_true", help="Overwrite an existing commit-msg hook.")
    install_parser.set_defaults(func=_cmd_install)

    uninstall_parser = subparsers.add_parser(
        "uninstall",
        parents=[repo_parent],
        help="Remove the riggit commit-msg hook.",
    )
    uninstall_parser.add_argument(
        "--force",
        action="store_true",
        help="Remove the hook file even if it was not installed by riggit.",
    )
    uninstall_parser.set_defaults(func=_cmd_uninstall)

    init_parser = subparsers.add_parser(
        "init",
        parents=[repo_parent],
        help="Create a default .riggitrc file describing the conventions to follow.",
    )
    init_parser.add_argument("--force", action="store_true", help="Overwrite an existing .riggitrc file.")
    init_parser.set_defaults(func=_cmd_init)

    range_parent = argparse.ArgumentParser(add_help=False)
    range_parent.add_argument("--since", default=None, help="Start of the commit range (a git ref/revision).")
    range_parent.add_argument("--until", default=None, help="End of the commit range (a git ref/revision, default HEAD).")

    scan_parser = subparsers.add_parser(
        "scan",
        parents=[format_parent, repo_parent, range_parent],
        help="Scan git history and report which commits violate the convention.",
    )
    scan_parser.add_argument(
        "--fix",
        action="store_true",
        help="Attempt to auto-correct simple violations (lowercase subject, remove trailing period).",
    )
    scan_parser.add_argument(
        "--force",
        action="store_true",
        help="With --fix, actually rewrite history (requires confirming the dry-run first).",
    )
    scan_parser.set_defaults(func=_cmd_scan)

    fix_message_parser = subparsers.add_parser("_fix-message", help=argparse.SUPPRESS)
    fix_message_parser.set_defaults(func=_cmd_fix_message)

    stats_parser = subparsers.add_parser(
        "stats",
        parents=[format_parent, repo_parent, range_parent],
        help="Report on commit quality: percent compliant, common violations, breakdown by author.",
    )
    stats_parser.set_defaults(func=_cmd_stats)

    hook_parser = subparsers.add_parser(
        "hook",
        parents=[repo_parent],
        help="Print the commit-msg hook script, or install/uninstall it globally or via git's template dir.",
    )
    hook_parser.add_argument("--install", action="store_true", help="Install the hook (requires --global or --template).")
    hook_parser.add_argument("--uninstall", action="store_true", help="Remove the hook (requires --global or --template).")
    hook_parser.add_argument(
        "--global",
        dest="global_",
        action="store_true",
        help="Target git's core.hooksPath, applying to all repositories immediately.",
    )
    hook_parser.add_argument(
        "--template",
        action="store_true",
        help="Target git's init.templateDir, applying to repositories created afterward.",
    )
    hook_parser.add_argument("--force", action="store_true", help="Overwrite/remove a non-riggit hook.")
    hook_parser.set_defaults(func=_cmd_hook)

    config_parser = subparsers.add_parser(
        "config",
        parents=[repo_parent],
        help="View or set configuration values (local .riggitrc by default, or --global).",
    )
    config_parser.add_argument(
        "--global",
        dest="global_",
        action="store_true",
        help="Operate on the global config (~/.config/riggit/config.yaml) instead of the local .riggitrc.",
    )
    config_parser.add_argument("--list", action="store_true", help="List all current configuration values.")
    config_parser.add_argument("key", nargs="?", default=None, help="Config key, e.g. types, scope_required.")
    config_parser.add_argument("value", nargs="?", default=None, help="Value to set. Omit to view the current value.")
    config_parser.set_defaults(func=_cmd_config)

    branch_format_parent = argparse.ArgumentParser(add_help=False)
    branch_format_parent.add_argument(
        "--format",
        dest="format_pattern",
        default=None,
        help="Custom regex for --extract instead of the default ticket-key pattern "
        f"({DEFAULT_TICKET_PATTERN!r}).",
    )

    branch_parser = subparsers.add_parser(
        "branch",
        parents=[repo_parent, branch_format_parent],
        help="Show the current branch, optionally extracting a ticket/issue key from it.",
    )
    branch_parser.add_argument("--extract", action="store_true", help="Extract a ticket/issue key from the branch name.")
    branch_parser.add_argument(
        "--json",
        dest="format",
        action="store_const",
        const="json",
        default="text",
        help="Output as JSON.",
    )
    branch_parser.set_defaults(func=_cmd_branch)

    commit_parser = subparsers.add_parser(
        "commit",
        parents=[repo_parent, branch_format_parent],
        help="A thin wrapper around `git commit` that lints the message and can auto-inject a ticket key.",
    )
    commit_parser.add_argument("-m", "--message", required=True, help="The commit message.")
    commit_parser.add_argument(
        "--auto",
        action="store_true",
        help="Extract a ticket key from the current branch and append it to the message if not already present.",
    )
    commit_parser.set_defaults(func=_cmd_commit)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
