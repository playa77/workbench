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


def test_load_config_no_config_file_fallback(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ENCRYPTION_KEY", "aa" * 32)

    config = load_config()
    assert config.log_level == "INFO"
    assert config.api_host == "127.0.0.1"
    assert config.api_port == 8420
    assert config.database_url == ""


def test_load_config_flat_override_already_set(tmp_path, monkeypatch):
    toml_content = """
[inference]
provider_url = "https://custom.ai/v1"
"""
    toml_file = tmp_path / "default.toml"
    toml_file.write_text(toml_content)

    monkeypatch.setenv("ENCRYPTION_KEY", "aa" * 32)

    config = load_config(default_path=Path(str(toml_file)))
    assert config.inference_provider_url == "https://custom.ai/v1"


def test_load_config_fallback_cwd_config(tmp_path, monkeypatch):
    """Lines 157-158: fallback to cwd/config/default.toml when source tree path doesn't exist."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    toml_file = config_dir / "default.toml"
    toml_file.write_text("""[general]\nlog_level = "DEBUG"\n""")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ENCRYPTION_KEY", "aa" * 32)

    actual_path_exists = Path.exists

    def patched_exists(self):
        s = str(self.absolute())
        # Return False for the source tree config path to force cwd fallback
        if "config/default.toml" in s and s != str(toml_file.absolute()):
            return False
        return actual_path_exists(self)

    monkeypatch.setattr(Path, "exists", patched_exists)
    config = load_config()
    assert config.log_level == "DEBUG"


def test_load_config_env_override_beats_section_field(tmp_path, monkeypatch):
    """Line 215: dst not in flat guard — env override prevents section-tp-flat mapping from overriding."""
    toml_content = """
[inference]
provider_url = "https://from-file.ai/v1"
"""
    toml_file = tmp_path / "default.toml"
    toml_file.write_text(toml_content)

    monkeypatch.setenv("ENCRYPTION_KEY", "aa" * 32)
    monkeypatch.setenv("WORKBENCH_INFERENCE__PROVIDER_URL", "https://from-env.ai/v1")

    config = load_config(default_path=Path(str(toml_file)))
    # Env override takes precedence because dst is already in flat
    assert config.inference_provider_url == "https://from-env.ai/v1"


def test_load_config_invalid_log_level_raises():
    """Line 89: invalid log_level raises ValueError."""
    with pytest.raises(ValueError, match="Invalid log_level"):
        WorkbenchConfig(log_level="invalid")


def test_load_config_no_config_file_neither_exists(tmp_path, monkeypatch):
    """Line 160: when neither source tree nor cwd config exists, fallback uses source_tree path."""
    monkeypatch.setenv("ENCRYPTION_KEY", "aa" * 32)
    actual_path_exists = Path.exists

    def patched_exists(self):
        s = str(self.absolute())
        if "default.toml" in s:
            return False
        return actual_path_exists(self)

    monkeypatch.setattr(Path, "exists", patched_exists)
    config = load_config()
    # Falls back to defaults
    assert config.log_level == "INFO"


def test_load_config_section_body_via_mocked_flatten(tmp_path, monkeypatch):
    """Line 215: flat[dst] = section[src] executes when _flatten_env_overrides skips a key."""
    from unittest.mock import patch
    import workbench.core.config as cfg

    toml_content = """
[inference]
provider_url = "https://from-section.ai/v1"
"""
    toml_file = tmp_path / "default.toml"
    toml_file.write_text(toml_content)

    monkeypatch.setenv("ENCRYPTION_KEY", "aa" * 32)

    original_flatten = cfg._flatten_env_overrides

    def patched_flatten(raw):
        result = original_flatten(raw)
        # Remove inference_provider_url so it's NOT in flat after raw.update,
        # forcing the section-to-flat mapping body at line 215 to set it
        result.pop("inference_provider_url", None)
        return result

    with patch.object(cfg, "_flatten_env_overrides", side_effect=patched_flatten):
        config = load_config(default_path=Path(str(toml_file)))

    assert config.inference_provider_url == "https://from-section.ai/v1"
