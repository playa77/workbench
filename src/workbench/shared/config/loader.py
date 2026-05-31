"""Shared configuration loading utilities.

Extracted from stoa's config framework and generalized for reuse across
all workbench agents and services.

Key primitives:
- deep_merge: Recursive dict merge for layered config
- read_toml: Load a TOML file, returning empty dict if missing
- read_env: Parse env vars with a configurable prefix + ``__`` nesting
- expand_paths: Replace ``${data_dir}`` template variables
- warn_unknown_keys: Log unknown top-level config keys
- format_validation_error: Pretty-print Pydantic validation errors
"""

from __future__ import annotations

import json
import logging
import os
import tomllib
from pathlib import Path
from typing import Any

LOGGER = logging.getLogger(__name__)


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge *override* into *base*. Dict values are merged
    recursively; all other values are replaced.

    Returns a new dict — neither argument is mutated.
    """
    result: dict[str, Any] = dict(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _parse_env_value(raw: str) -> Any:
    """Parse a single env-var value as JSON if possible; otherwise return raw string."""
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return raw


def read_env(prefix: str = "") -> dict[str, Any]:
    """Read environment variables into a nested dict.

    Variables that start with *prefix* are ingested. The key after the
    prefix is split on ``__`` to build nesting. Values are JSON-parsed
    when possible.

    Example::

        WORKBENCH_API__PORT=8420
        WORKBENCH_AUTH__API_KEY_PREFIX="custom"

    yields::

        {"api": {"port": 8420}, "auth": {"api_key_prefix": "custom"}}
    """
    merged: dict[str, Any] = {}
    for key, value in os.environ.items():
        if prefix and not key.startswith(prefix):
            continue
        nested = key[len(prefix):].lower().split("__")
        if not nested or not nested[0]:
            continue
        cursor: dict[str, Any] = merged
        for part in nested[:-1]:
            next_value = cursor.get(part)
            if not isinstance(next_value, dict):
                next_value = {}
                cursor[part] = next_value
            cursor = next_value
        cursor[nested[-1]] = _parse_env_value(value)
    return merged


def read_toml(path: Path) -> dict[str, Any]:
    """Read a TOML file; return empty dict if the file is missing."""
    if not path.exists():
        return {}
    return tomllib.loads(path.read_text())


def expand_path(
    path_value: str,
    data_dir: str,
) -> str:
    """Replace ``${data_dir}`` and expand ``~`` in a path string."""
    expanded = path_value.replace("${data_dir}", data_dir)
    return str(Path(expanded).expanduser())


def expand_paths(
    config: dict[str, Any],
    *,
    paths: list[tuple[str, str]] | None = None,
) -> dict[str, Any]:
    """Expand ``${data_dir}`` and ``~`` in config values.

    By default expands well-known path keys under [storage] and [evaluation].
    Pass explicit *paths* as ``[(section, key), ...]`` for additional targets.
    """
    general = config.get("general", {})
    data_dir_raw = str(general.get("data_dir", "~/.local/share/workbench"))
    data_dir = str(Path(data_dir_raw).expanduser())
    general["data_dir"] = data_dir
    config["general"] = general

    default_targets: list[tuple[str, str]] = [
        ("storage", "db_path"),
        ("storage", "trace_dir"),
        ("storage", "artifact_dir"),
        ("evaluation", "results_dir"),
    ]
    for section, key in (default_targets + (paths or [])):
        section_values = config.get(section)
        if isinstance(section_values, dict) and key in section_values:
            section_values[key] = expand_path(str(section_values[key]), data_dir)

    workspace = config.get("workspace")
    if isinstance(workspace, dict):
        allowed = workspace.get("allowed_paths")
        if isinstance(allowed, list):
            workspace["allowed_paths"] = [
                expand_path(str(item), data_dir) for item in allowed
            ]

    return config


def warn_unknown_keys(
    config_data: dict[str, Any],
    known_keys: set[str],
) -> None:
    """Log warnings for top-level config keys not in *known_keys*."""
    unknown = config_data.keys() - known_keys
    for key in unknown:
        LOGGER.warning("Unknown config key ignored: %s", key)


def format_validation_error(error: Exception) -> str:
    """Pretty-print a Pydantic ``ValidationError``."""
    try:
        from pydantic import ValidationError
        if not isinstance(error, ValidationError):
            return str(error)
        messages = []
        for issue in error.errors():
            location = ".".join(str(part) for part in issue["loc"])
            messages.append(f"{location}: {issue['msg']}")
        return "Configuration validation failed:\n" + "\n".join(messages)
    except ImportError:
        return str(error)
