"""Configuration loading and validation for CAW."""

from __future__ import annotations

import json
import logging
import os
import tomllib
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from caw.errors import ConfigError

LOGGER = logging.getLogger(__name__)


class _BaseConfigModel(BaseModel):
    model_config = ConfigDict(extra="ignore")


class GeneralConfig(_BaseConfigModel):
    version: str = "1.0.0"
    log_level: str = "INFO"
    data_dir: str = "~/.local/share/caw"

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, value: str) -> str:
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR"}
        normalized = value.upper()
        if normalized not in allowed:
            raise ValueError(f"log_level must be one of {allowed}, got '{value}'")
        return normalized


class StorageConfig(_BaseConfigModel):
    db_path: str = "${data_dir}/caw.db"
    trace_dir: str = "${data_dir}/traces"
    artifact_dir: str = "${data_dir}/artifacts"


class ProviderConfig(_BaseConfigModel):
    type: str
    api_key_env: str = ""
    default_model: str
    max_tokens: int = 4096
    timeout_seconds: int = 120
    base_url: str | None = None

    @field_validator("type")
    @classmethod
    def validate_type(cls, value: str) -> str:
        allowed = {"anthropic", "openai", "openai_compatible"}
        if value not in allowed:
            raise ValueError(f"provider type must be one of {allowed}, got '{value}'")
        return value


class RoutingConfig(_BaseConfigModel):
    strategy: str = "config"
    fallback_chain: list[str] = Field(default_factory=list)

    @field_validator("strategy")
    @classmethod
    def validate_strategy(cls, value: str) -> str:
        allowed = {"config", "cost", "capability", "latency"}
        if value not in allowed:
            raise ValueError(f"routing strategy must be one of {allowed}, got '{value}'")
        return value


class SkillsConfig(_BaseConfigModel):
    builtin_dir: str = "skills/builtin"
    user_dir: str = "skills/user"
    packs_dir: str = "skills/packs"


class WorkspaceConfig(_BaseConfigModel):
    sandbox_mode: str = "permissive"
    allowed_paths: list[str] = Field(default_factory=lambda: ["~", "/tmp"])
    confirm_writes: bool = True
    confirm_deletes: bool = True
    confirm_executions: bool = True

    @field_validator("sandbox_mode")
    @classmethod
    def validate_sandbox_mode(cls, value: str) -> str:
        allowed = {"strict", "permissive", "none"}
        if value not in allowed:
            raise ValueError(f"sandbox_mode must be one of {allowed}, got '{value}'")
        return value


class EvaluationConfig(_BaseConfigModel):
    tasks_dir: str = "tasks"
    results_dir: str = "${data_dir}/eval_results"
    default_scorer: str = "composite"


class APIConfig(_BaseConfigModel):
    host: str = "127.0.0.1"
    port: int = 8420
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])


class CAWConfig(_BaseConfigModel):
    general: GeneralConfig = Field(default_factory=GeneralConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)
    providers: dict[str, ProviderConfig] = Field(default_factory=dict)
    routing: RoutingConfig = Field(default_factory=RoutingConfig)
    skills: SkillsConfig = Field(default_factory=SkillsConfig)
    workspace: WorkspaceConfig = Field(default_factory=WorkspaceConfig)
    evaluation: EvaluationConfig = Field(default_factory=EvaluationConfig)
    api: APIConfig = Field(default_factory=APIConfig)

    @model_validator(mode="before")
    @classmethod
    def normalize_provider_defaults(cls, data: Any) -> Any:
        """Normalize legacy ``[providers] default = \"...\"`` shape.

        Provider definitions are modeled as ``dict[str, ProviderConfig]``. Some
        config files (including examples) also place ``default = "provider_key"``
        under ``[providers]``. We currently do not consume that default key for
        routing, but we should ignore it instead of failing validation.
        """
        if not isinstance(data, dict):
            return data

        providers = data.get("providers")
        if not isinstance(providers, dict):
            return data

        default_provider = providers.get("default") if isinstance(providers.get("default"), str) else None
        provider_entries = {
            key: value for key, value in providers.items() if isinstance(value, dict)
        }

        if default_provider in provider_entries:
            reordered = {default_provider: provider_entries[default_provider]}
            reordered.update(
                {key: value for key, value in provider_entries.items() if key != default_provider}
            )
            data["providers"] = reordered
            return data

        data["providers"] = provider_entries
        return data


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = dict(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _read_toml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return tomllib.loads(path.read_text())


def _parse_env_value(raw: str) -> object:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def _read_env() -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for key, value in os.environ.items():
        if not key.startswith("CAW_"):
            continue
        nested = key[4:].lower().split("__")
        cursor: dict[str, Any] = merged
        for part in nested[:-1]:
            next_value = cursor.get(part)
            if not isinstance(next_value, dict):
                next_value = {}
                cursor[part] = next_value
            cursor = next_value
        cursor[nested[-1]] = _parse_env_value(value)
    return merged


def _expand_path(path_value: str, data_dir: str) -> str:
    expanded = path_value.replace("${data_dir}", data_dir)
    return str(Path(expanded).expanduser())


def _expand_paths(config: dict[str, Any]) -> dict[str, Any]:
    general = config.get("general", {})
    data_dir_raw = str(general.get("data_dir", "~/.local/share/caw"))
    data_dir = str(Path(data_dir_raw).expanduser())
    general["data_dir"] = data_dir
    config["general"] = general

    for section, key in [
        ("storage", "db_path"),
        ("storage", "trace_dir"),
        ("storage", "artifact_dir"),
        ("evaluation", "results_dir"),
    ]:
        section_values = config.get(section)
        if isinstance(section_values, dict) and key in section_values:
            section_values[key] = _expand_path(str(section_values[key]), data_dir)

    workspace = config.get("workspace")
    if isinstance(workspace, dict):
        allowed = workspace.get("allowed_paths")
        if isinstance(allowed, list):
            workspace["allowed_paths"] = [_expand_path(str(item), data_dir) for item in allowed]

    return config


def _warn_unknown_keys(config_data: dict[str, Any]) -> None:
    valid_top = set(CAWConfig.model_fields.keys())
    for key in config_data.keys() - valid_top:
        LOGGER.warning("Unknown config key ignored: %s", key)


def _format_validation_error(error: ValidationError) -> str:
    messages = []
    for issue in error.errors():
        location = ".".join(str(part) for part in issue["loc"])
        messages.append(f"{location}: {issue['msg']}")
    return "Configuration validation failed:\n" + "\n".join(messages)


def load_config(
    overrides: dict[str, object] | None = None,
    user_config_path: Path | None = None,
    project_config_path: Path | None = None,
    default_config_path: Path | None = None,
) -> CAWConfig:
    """Load and validate configuration from precedence layers."""
    resolved_default = default_config_path or (
        Path(__file__).resolve().parents[3] / "config/default.toml"
    )
    resolved_project = project_config_path or Path.cwd() / "caw.toml"
    resolved_project_legacy = Path.cwd() / "config/local.toml"
    resolved_user = user_config_path or Path("~/.config/caw/config.toml").expanduser()

    merged = _read_toml(resolved_default)
    merged = _deep_merge(merged, _read_toml(resolved_project_legacy))
    merged = _deep_merge(merged, _read_toml(resolved_project))
    merged = _deep_merge(merged, _read_toml(resolved_user))
    merged = _deep_merge(merged, _read_env())
    if overrides is not None:
        merged = _deep_merge(merged, dict(overrides))

    _warn_unknown_keys(merged)
    expanded = _expand_paths(merged)

    try:
        return CAWConfig.model_validate(expanded)
    except ValidationError as exc:
        message = _format_validation_error(exc)
        raise ConfigError(message=message, code="config_validation_error") from exc
