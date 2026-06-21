"""Tests for core.config — uncovered lines: CORS warning, flatten overrides, section-to-flat, STS."""

import logging
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from workbench.core.config import WorkbenchConfig, _flatten_env_overrides, load_config


def test_cors_origins_wildcard_warning(caplog):
    with caplog.at_level(logging.WARNING, logger="workbench.core.config"):
        config = WorkbenchConfig(api_cors_origins=["*"])
    assert config.api_cors_origins == ["*"]
    assert any("CORS" in r.message for r in caplog.records)


def test_flatten_env_overrides_unknown_key_warning(caplog):
    with caplog.at_level(logging.WARNING, logger="workbench.core.config"):
        env_overrides = {
            "unknown_section": {"weird_key": "value"},
        }
        result = _flatten_env_overrides(env_overrides)
    assert result == {}
    assert any("Unknown" in r.message for r in caplog.records)


def test_flatten_env_overrides_known_keys():
    env_overrides = {
        "api": {"host": "0.0.0.0", "port": 9090},
        "general": {"log_level": "DEBUG"},
        "openrouter": {"base_url": "https://custom.api/v1"},
    }
    result = _flatten_env_overrides(env_overrides)
    assert result["api_host"] == "0.0.0.0"
    assert result["api_port"] == 9090
    assert result["log_level"] == "DEBUG"
    assert result["openrouter_base_url"] == "https://custom.api/v1"


def test_flatten_env_overrides_non_dict_section():
    env_overrides = {
        "general": "not_a_dict",
    }
    result = _flatten_env_overrides(env_overrides)
    assert result == {}


def test_load_config_section_to_flat_mapping(tmp_path):
    toml_content = """
[general]
log_level = "DEBUG"
data_dir = "/tmp/wb"

[api]
host = "0.0.0.0"
port = 9999

[openrouter]
base_url = "https://test.api/v1"
default_model = "test-model"

[auth]
api_key_prefix = "test"
max_keys_per_user = 10
session_expiry_hours = 48

[rate_limit]
enabled = false
auth = "10/minute"
agents = "100/minute"
general = "200/minute"

[smtp]
host = "smtp.test.com"
port = 25
user = "testuser"
password = "testpass"
from_address = "test@test.com"
use_tls = false
"""
    toml_file = tmp_path / "default.toml"
    toml_file.write_text(toml_content)

    with patch.dict(os.environ, {"ENCRYPTION_KEY": "aa" * 32, "DATABASE_URL": "sqlite:///test.db"}, clear=False):
        config = load_config(default_path=Path(str(toml_file)))

    assert config.log_level == "DEBUG"
    assert config.data_dir == "/tmp/wb"
    assert config.api_host == "0.0.0.0"
    assert config.api_port == 9999
    assert config.openrouter_base_url == "https://test.api/v1"
    assert config.openrouter_default_model == "test-model"
    assert config.auth_api_key_prefix == "test"
    assert config.auth_max_keys_per_user == 10
    assert config.auth_session_expiry_hours == 48
    assert config.rate_limit_enabled is False
    assert config.smtp_host == "smtp.test.com"
    assert config.smtp_port == 25


def test_strict_transport_security_field():
    config = WorkbenchConfig(api_strict_transport_security="max-age=31536000")
    assert config.api_strict_transport_security == "max-age=31536000"
