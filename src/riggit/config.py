"""Loading, merging, and editing riggit configuration.

Three layers of precedence, lowest to highest:

  built-in defaults  <  global config (~/.config/riggit/config.yaml)  <  local .riggitrc

If neither a global nor a local config file exists, riggit falls back to
standard Conventional Commits behavior.
"""

from __future__ import annotations

import copy
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .conventional_commits import DEFAULT_TYPES

CONFIG_FILENAME = ".riggitrc"


def global_config_path() -> Path:
    """Path to the per-user global config file.

    Overridable via RIGGIT_GLOBAL_CONFIG (mainly so tests don't touch the
    real user home directory).
    """
    override = os.environ.get("RIGGIT_GLOBAL_CONFIG")
    if override:
        return Path(override)
    return Path.home() / ".config" / "riggit" / "config.yaml"


DEFAULT_CONFIG: dict[str, Any] = {
    "types": list(DEFAULT_TYPES),
    "scope_required": False,
    "max_header_length": 100,
    # "lower" warns if the description doesn't start with a lowercase
    # letter; "any" disables the check.
    "description_case": "lower",
    "no_trailing_period": True,
}

_VALID_DESCRIPTION_CASES = ("lower", "any")
_BOOL_KEYS = ("scope_required", "no_trailing_period")
CONFIG_KEYS = tuple(DEFAULT_CONFIG.keys())


class ConfigError(RuntimeError):
    """Raised when a config file or value is malformed."""


def _load_yaml_mapping(path: Path) -> dict[str, Any]:
    try:
        raw_text = path.read_text()
    except OSError as exc:
        raise ConfigError(f"Failed to read {path}: {exc}") from exc

    try:
        raw = yaml.safe_load(raw_text) or {}
    except yaml.YAMLError as exc:
        raise ConfigError(f"Failed to parse {path}: {exc}") from exc

    if not isinstance(raw, dict):
        raise ConfigError(f"{path} must contain a YAML mapping at the top level.")
    return raw


def _validate_and_coerce(merged: dict[str, Any], path_label: str) -> dict[str, Any]:
    if not isinstance(merged["types"], list) or not all(
        isinstance(t, str) and t for t in merged["types"]
    ):
        raise ConfigError(f"{path_label}: 'types' must be a list of non-empty strings.")
    if not merged["types"]:
        raise ConfigError(f"{path_label}: 'types' must not be empty.")

    if merged["max_header_length"] is not None:
        try:
            merged["max_header_length"] = int(merged["max_header_length"])
        except (TypeError, ValueError):
            raise ConfigError(f"{path_label}: 'max_header_length' must be an integer or null.") from None

    if merged["description_case"] not in _VALID_DESCRIPTION_CASES:
        raise ConfigError(
            f"{path_label}: 'description_case' must be one of {_VALID_DESCRIPTION_CASES}."
        )

    merged["scope_required"] = bool(merged["scope_required"])
    merged["no_trailing_period"] = bool(merged["no_trailing_period"])
    merged["types"] = list(merged["types"])
    return merged


@dataclass
class RiggitConfig:
    types: tuple[str, ...]
    scope_required: bool
    max_header_length: int | None
    description_case: str
    no_trailing_period: bool
    source: str | None = None  # highest-precedence config file used, None for built-in defaults

    @classmethod
    def defaults(cls) -> "RiggitConfig":
        d = DEFAULT_CONFIG
        return cls(
            types=tuple(d["types"]),
            scope_required=d["scope_required"],
            max_header_length=d["max_header_length"],
            description_case=d["description_case"],
            no_trailing_period=d["no_trailing_period"],
            source=None,
        )

    @classmethod
    def from_file(cls, path: Path) -> "RiggitConfig":
        raw = _load_yaml_mapping(path)
        merged = copy.deepcopy(DEFAULT_CONFIG)
        for key in DEFAULT_CONFIG:
            if key in raw and raw[key] is not None:
                merged[key] = raw[key]
        merged = _validate_and_coerce(merged, str(path))
        return cls(
            types=tuple(merged["types"]),
            scope_required=merged["scope_required"],
            max_header_length=merged["max_header_length"],
            description_case=str(merged["description_case"]),
            no_trailing_period=merged["no_trailing_period"],
            source=str(path),
        )


def find_config_file(start: str | Path) -> Path | None:
    """Search `start` and its parent directories for a local `.riggitrc` file."""
    current = Path(start).resolve()
    search_roots = [current, *current.parents] if current.is_dir() else [current.parent, *current.parent.parents]
    for directory in search_roots:
        candidate = directory / CONFIG_FILENAME
        if candidate.is_file():
            return candidate
    return None


def load_config(start: str | Path = ".") -> RiggitConfig:
    """Load the effective config: defaults, overlaid by the global config
    (if present), overlaid by the local `.riggitrc` found from `start` or its
    parents (if present)."""
    merged = copy.deepcopy(DEFAULT_CONFIG)
    source: str | None = None

    global_path = global_config_path()
    if global_path.is_file():
        raw = _load_yaml_mapping(global_path)
        for key in DEFAULT_CONFIG:
            if key in raw and raw[key] is not None:
                merged[key] = raw[key]
        source = str(global_path)

    local_path = find_config_file(start)
    if local_path is not None:
        raw = _load_yaml_mapping(local_path)
        for key in DEFAULT_CONFIG:
            if key in raw and raw[key] is not None:
                merged[key] = raw[key]
        source = str(local_path)

    if source is None:
        return RiggitConfig.defaults()

    merged = _validate_and_coerce(merged, source)
    return RiggitConfig(
        types=tuple(merged["types"]),
        scope_required=merged["scope_required"],
        max_header_length=merged["max_header_length"],
        description_case=str(merged["description_case"]),
        no_trailing_period=merged["no_trailing_period"],
        source=source,
    )


def parse_config_value(key: str, raw_value: str) -> Any:
    """Parse a CLI-supplied string value for `key` into its YAML-ready form."""
    if key not in CONFIG_KEYS:
        raise ConfigError(f"Unknown config key '{key}'. Valid keys: {', '.join(CONFIG_KEYS)}.")

    if key == "types":
        items = [item.strip() for item in raw_value.split(",") if item.strip()]
        if not items:
            raise ConfigError("'types' must be a non-empty comma-separated list, e.g. 'feat,fix,docs'.")
        return items

    if key in _BOOL_KEYS:
        normalized = raw_value.strip().lower()
        if normalized in ("true", "yes", "1", "on"):
            return True
        if normalized in ("false", "no", "0", "off"):
            return False
        raise ConfigError(f"'{key}' must be a boolean (true/false), got {raw_value!r}.")

    if key == "max_header_length":
        normalized = raw_value.strip().lower()
        if normalized in ("null", "none", ""):
            return None
        try:
            return int(raw_value)
        except ValueError:
            raise ConfigError(f"'max_header_length' must be an integer or 'null', got {raw_value!r}.") from None

    if key == "description_case":
        if raw_value not in _VALID_DESCRIPTION_CASES:
            raise ConfigError(f"'description_case' must be one of {_VALID_DESCRIPTION_CASES}.")
        return raw_value

    raise ConfigError(f"Unknown config key '{key}'.")  # pragma: no cover - defensive, unreachable


def effective_values_for_file(path: str | Path) -> dict[str, Any]:
    """Return defaults overlaid by `path` alone (ignoring any other config
    layer), validated. Used to show what a single scope (e.g. just the
    global config) currently contains."""
    path = Path(path)
    merged = copy.deepcopy(DEFAULT_CONFIG)
    if path.is_file():
        raw = _load_yaml_mapping(path)
        for key in DEFAULT_CONFIG:
            if key in raw and raw[key] is not None:
                merged[key] = raw[key]
        merged = _validate_and_coerce(merged, str(path))
    return merged


def _format_scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    if isinstance(value, int):
        return str(value)
    # Strings: reuse yaml's quoting rules but strip the "key: " wrapper and
    # the trailing "\n...\n" document-end marker safe_dump always adds for
    # bare scalars.
    dumped = yaml.safe_dump({"v": value})[len("v: "):].strip()
    if dumped.endswith("..."):
        dumped = dumped[: -len("...")].rstrip("\n")
    return dumped


def _format_yaml_value(value: Any) -> str:
    if isinstance(value, list):
        return "[" + ", ".join(_format_scalar(v) for v in value) + "]"
    return _format_scalar(value)


def set_config_value(path: str | Path, key: str, raw_value: str) -> Any:
    """Set `key` to `raw_value` (parsed per its type) in the YAML file at `path`.

    Edits the file line-by-line so any existing comments/formatting for
    *other* keys are preserved; the edited key's own line(s) are replaced
    wholesale. Creates the file (and parent directories) if it doesn't exist.
    """
    value = parse_config_value(key, raw_value)
    path = Path(path)
    new_line = f"{key}: {_format_yaml_value(value)}"

    lines = path.read_text().splitlines() if path.is_file() else []

    start_idx = None
    for i, line in enumerate(lines):
        if line.startswith(f"{key}:"):
            start_idx = i
            break

    if start_idx is None:
        if lines and lines[-1].strip() != "":
            lines.append("")
        lines.append(new_line)
    else:
        end_idx = start_idx + 1
        while end_idx < len(lines) and (lines[end_idx].startswith((" ", "\t")) or lines[end_idx].strip() == "" and end_idx + 1 < len(lines) and lines[end_idx + 1].startswith((" ", "\t"))):
            end_idx += 1
        lines[start_idx:end_idx] = [new_line]

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n")
    return value


def get_raw_config_value(path: str | Path, key: str) -> Any | None:
    """Return the raw value of `key` as set in the YAML file at `path`, or
    None if the file doesn't exist or doesn't set that key."""
    path = Path(path)
    if not path.is_file():
        return None
    raw = _load_yaml_mapping(path)
    return raw.get(key)
