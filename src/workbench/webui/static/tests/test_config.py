"""Tests for workbench.core.config."""

import os
import tomllib
from pathlib import Path
from tempfile import NamedTemporaryFile

import pytest

from workbench.core.config import WorkbenchConfig, load_config


def test_default_config_values():
    cfg = WorkbenchConfig()
    assert cfg.log_level == "INFO"
    assert cfg.api_port == 8420
    assert cfg.auth_api_key_prefix == "wb"
    assert cfg.openrouter_default_model == "deepseek/deepseek-v4-pro"
    assert cfg.auth_max_keys_per_user == 5
    assert cfg.openrouter_max_retries == 2


def test_log_level_validation():
    assert WorkbenchConfig(log_level="DEBUG").log_level == "DEBUG"
    assert WorkbenchConfig(log_level="error").log_level == "ERROR"

    with pytest.raises(ValueError):
        WorkbenchConfig(log_level="INVALID")


def test_extra_fields_ignored():
    cfg = WorkbenchConfig(unknown_field="should be ignored")  # type: ignore[call-arg]
    assert not hasattr(cfg, "unknown_field")


def test_load_config_from_toml():
    toml_content = b"""
[general]
log_level = "DEBUG"

[api]
port = 9999

[auth]
api_key_prefix = "custom"
"""
    with NamedTemporaryFile(suffix=".toml", delete=False) as f:
        f.write(toml_content)
        f.flush()
        cfg = load_config(default_path=Path(f.name))

    assert cfg.log_level == "DEBUG"
    assert cfg.api_port == 9999
    assert cfg.auth_api_key_prefix == "custom"
    Path(f.name).unlink()


def test_load_config_env_override(monkeypatch):
    monkeypatch.setenv("WORKBENCH_GENERAL__LOG_LEVEL", '"WARNING"')
    monkeypatch.setenv("WORKBENCH_API__PORT", "12345")
    monkeypatch.setenv("WORKBENCH_AUTH__API_KEY_PREFIX", '"env-prefix"')

    cfg = load_config(default_path=Path("/nonexistent/path.toml"))
    assert cfg.log_level == "WARNING"
    assert cfg.api_port == 12345
    assert cfg.auth_api_key_prefix == "env-prefix"


def test_load_config_database_url_from_env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
    monkeypatch.delenv("WORKBENCH_DATABASE__URL_ENV", raising=False)

    cfg = load_config(default_path=Path("/nonexistent/path.toml"))
    assert cfg.database_url == "postgresql+asyncpg://test:test@localhost/test"


def test_load_config_encryption_key_from_env(monkeypatch):
    test_key = "deadbeef" * 8
    monkeypatch.setenv("ENCRYPTION_KEY", test_key)

    cfg = load_config(
        default_path=Path(__file__).resolve().parent.parent / "config" / "default.toml"
    )
    assert cfg.encryption_key == test_key


def test_config_round_trip():
    cfg = WorkbenchConfig(
        log_level="WARNING",
        api_host="127.0.0.1",
        api_port=9876,
        openrouter_timeout_seconds=60,
        auth_max_keys_per_user=10,
        encryption_key="ab" * 32,
    )
    assert cfg.api_host == "127.0.0.1"
    assert cfg.api_port == 9876
    assert cfg.openrouter_timeout_seconds == 60
    assert cfg.auth_max_keys_per_user == 10
