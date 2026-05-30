from pathlib import Path

import pytest

from caw.core.config import _deep_merge, load_config
from caw.errors import ConfigError

FIXTURE_DIR = Path(__file__).resolve().parents[2] / "fixtures/config"


def test_load_defaults() -> None:
    config = load_config(
        project_config_path=Path("/does/not/exist"), user_config_path=Path("/does/not/exist")
    )
    assert config.general.log_level == "INFO"
    assert config.storage.db_path.endswith("caw.db")


def test_load_from_file() -> None:
    config = load_config(
        default_config_path=FIXTURE_DIR / "valid_minimal.toml",
        project_config_path=Path("/does/not/exist"),
        user_config_path=Path("/does/not/exist"),
    )
    assert config.general.log_level == "DEBUG"


def test_precedence_env_over_file(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CAW_GENERAL__LOG_LEVEL", "ERROR")
    config = load_config(
        default_config_path=FIXTURE_DIR / "valid_minimal.toml",
        project_config_path=Path("/does/not/exist"),
        user_config_path=Path("/does/not/exist"),
    )
    assert config.general.log_level == "ERROR"


def test_precedence_override_over_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CAW_GENERAL__LOG_LEVEL", "ERROR")
    config = load_config(
        overrides={"general": {"log_level": "WARNING"}},
        default_config_path=FIXTURE_DIR / "valid_minimal.toml",
        project_config_path=Path("/does/not/exist"),
        user_config_path=Path("/does/not/exist"),
    )
    assert config.general.log_level == "WARNING"


def test_path_expansion_data_dir() -> None:
    config = load_config(
        default_config_path=FIXTURE_DIR / "valid_full.toml",
        project_config_path=Path("/does/not/exist"),
        user_config_path=Path("/does/not/exist"),
    )
    assert "${data_dir}" not in config.storage.db_path


def test_path_expansion_tilde() -> None:
    config = load_config(
        default_config_path=FIXTURE_DIR / "valid_full.toml",
        project_config_path=Path("/does/not/exist"),
        user_config_path=Path("/does/not/exist"),
    )
    assert not config.general.data_dir.startswith("~")


def test_invalid_sandbox_mode() -> None:
    with pytest.raises(ConfigError):
        load_config(
            default_config_path=FIXTURE_DIR / "invalid_sandbox_mode.toml",
            project_config_path=Path("/does/not/exist"),
            user_config_path=Path("/does/not/exist"),
        )


def test_invalid_log_level() -> None:
    with pytest.raises(ConfigError):
        load_config(
            overrides={"general": {"log_level": "LOUD"}},
            default_config_path=FIXTURE_DIR / "valid_minimal.toml",
            project_config_path=Path("/does/not/exist"),
            user_config_path=Path("/does/not/exist"),
        )


def test_invalid_provider_type() -> None:
    with pytest.raises(ConfigError):
        load_config(
            overrides={"providers": {"x": {"type": "bad", "default_model": "m"}}},
            default_config_path=FIXTURE_DIR / "valid_minimal.toml",
            project_config_path=Path("/does/not/exist"),
            user_config_path=Path("/does/not/exist"),
        )


def test_deep_merge_dicts() -> None:
    merged = _deep_merge({"a": {"b": 1, "c": 2}}, {"a": {"d": 3}})
    assert merged == {"a": {"b": 1, "c": 2, "d": 3}}


def test_deep_merge_lists_replace() -> None:
    merged = _deep_merge({"a": [1, 2]}, {"a": [3]})
    assert merged == {"a": [3]}


def test_unknown_keys_no_crash() -> None:
    config = load_config(
        overrides={"unknown": {"x": 1}},
        default_config_path=FIXTURE_DIR / "valid_minimal.toml",
        project_config_path=Path("/does/not/exist"),
        user_config_path=Path("/does/not/exist"),
    )
    assert config.general.log_level == "DEBUG"


def test_providers_default_string_is_ignored() -> None:
    config = load_config(
        overrides={
            "providers": {
                "default": "openrouter",
                "openrouter": {
                    "type": "openai_compatible",
                    "api_key_env": "OPENROUTER_API_KEY",
                    "default_model": "bytedance-seed/seed-2.0-lite",
                },
            }
        },
        default_config_path=FIXTURE_DIR / "valid_minimal.toml",
        project_config_path=Path("/does/not/exist"),
        user_config_path=Path("/does/not/exist"),
    )
    assert "openrouter" in config.providers
    assert "default" not in config.providers


def test_load_from_legacy_config_local_toml(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project = tmp_path / "project"
    (project / "config").mkdir(parents=True)
    (project / "config/local.toml").write_text('[general]\nlog_level = "ERROR"\n')
    monkeypatch.chdir(project)

    config = load_config(
        default_config_path=FIXTURE_DIR / "valid_minimal.toml",
        project_config_path=Path("/does/not/exist"),
        user_config_path=Path("/does/not/exist"),
    )

    assert config.general.log_level == "ERROR"
