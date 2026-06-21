"""Tests for shared.config.loader — deep_merge, read_env, read_toml, expand_paths, etc."""

import json
import logging
import os
from pathlib import Path
from unittest.mock import patch

import pytest
from pydantic import BaseModel, ValidationError

from workbench.shared.config.loader import (
    _parse_env_value,
    deep_merge,
    expand_path,
    expand_paths,
    format_validation_error,
    read_env,
    read_toml,
    warn_unknown_keys,
)


# ---- deep_merge ----


def test_deep_merge_simple():
    result = deep_merge({"a": 1}, {"b": 2})
    assert result == {"a": 1, "b": 2}


def test_deep_merge_nested():
    result = deep_merge({"a": {"x": 1, "y": 2}}, {"a": {"y": 3, "z": 4}})
    assert result == {"a": {"x": 1, "y": 3, "z": 4}}


def test_deep_merge_override_replaces_non_dict():
    result = deep_merge({"a": "string"}, {"a": {"nested": True}})
    assert result == {"a": {"nested": True}}


def test_deep_merge_does_not_mutate():
    base = {"a": 1}
    override = {"b": 2}
    result = deep_merge(base, override)
    assert base == {"a": 1}
    assert override == {"b": 2}
    assert result == {"a": 1, "b": 2}


def test_deep_merge_empty_dicts():
    assert deep_merge({}, {}) == {}
    assert deep_merge({"a": 1}, {}) == {"a": 1}
    assert deep_merge({}, {"a": 1}) == {"a": 1}


# ---- _parse_env_value ----


def test_parse_env_value_json_int():
    assert _parse_env_value("42") == 42


def test_parse_env_value_json_bool():
    assert _parse_env_value("true") is True


def test_parse_env_value_json_list():
    assert _parse_env_value("[1, 2, 3]") == [1, 2, 3]


def test_parse_env_value_plain_string():
    assert _parse_env_value("hello world") == "hello world"


def test_parse_env_value_json_object():
    assert _parse_env_value('{"key": "val"}') == {"key": "val"}


# ---- read_env ----


def test_read_env_with_prefix():
    env = {"WORKBENCH_API__PORT": "8420", "WORKBENCH_AUTH__API_KEY_PREFIX": "custom"}
    with patch.dict(os.environ, env, clear=True):
        result = read_env("WORKBENCH_")
    assert result == {"api": {"port": 8420}, "auth": {"api_key_prefix": "custom"}}


def test_read_env_no_prefix():
    env = {"MY_VAR": "value"}
    with patch.dict(os.environ, env, clear=True):
        result = read_env("")
    assert "my_var" in result


def test_read_env_ignores_non_prefixed():
    env = {"OTHER_VAR": "value", "WORKBENCH_KEY": "val"}
    with patch.dict(os.environ, env, clear=True):
        result = read_env("WORKBENCH_")
    assert "other_var" not in result
    assert "key" in result


# ---- read_toml ----


def test_read_toml_existing_file(tmp_path):
    toml_file = tmp_path / "test.toml"
    toml_file.write_text('[section]\nkey = "value"\n')
    result = read_toml(toml_file)
    assert result == {"section": {"key": "value"}}


def test_read_toml_missing_file():
    result = read_toml(Path("/nonexistent/file.toml"))
    assert result == {}


# ---- expand_path ----


def test_expand_path_data_dir():
    result = expand_path("${data_dir}/subdir", "/opt/data")
    assert result == "/opt/data/subdir"


def test_expand_path_home():
    result = expand_path("~/test", "/opt/data")
    assert not result.startswith("~")


# ---- expand_paths ----


def test_expand_paths_default_targets():
    config = {
        "general": {"data_dir": "/tmp/wb"},
        "storage": {"db_path": "${data_dir}/db", "trace_dir": "${data_dir}/traces", "artifact_dir": "${data_dir}/artifacts"},
        "evaluation": {"results_dir": "${data_dir}/results"},
    }
    result = expand_paths(config)
    assert result["storage"]["db_path"] == "/tmp/wb/db"
    assert result["storage"]["trace_dir"] == "/tmp/wb/traces"
    assert result["evaluation"]["results_dir"] == "/tmp/wb/results"


def test_expand_paths_workspace_allowed_paths():
    config = {
        "general": {"data_dir": "/tmp/wb"},
        "workspace": {"allowed_paths": ["${data_dir}/ws1", "${data_dir}/ws2"]},
    }
    result = expand_paths(config)
    assert result["workspace"]["allowed_paths"] == ["/tmp/wb/ws1", "/tmp/wb/ws2"]


def test_expand_paths_custom_targets():
    config = {
        "general": {"data_dir": "/tmp/wb"},
        "custom": {"my_path": "${data_dir}/custom"},
    }
    result = expand_paths(config, paths=[("custom", "my_path")])
    assert result["custom"]["my_path"] == "/tmp/wb/custom"


# ---- warn_unknown_keys ----


def test_warn_unknown_keys_logs_warning(caplog):
    with caplog.at_level(logging.WARNING):
        warn_unknown_keys({"unknown_key": 1, "known_key": 2}, {"known_key"})
    assert any("unknown_key" in r.message for r in caplog.records)


def test_warn_unknown_keys_no_warning(caplog):
    with caplog.at_level(logging.WARNING):
        warn_unknown_keys({"known_key": 1}, {"known_key"})
    assert not any("unknown" in r.message for r in caplog.records)


# ---- format_validation_error ----


def test_format_validation_error():
    class TestModel(BaseModel):
        name: str

    with pytest.raises(ValidationError) as exc_info:
        TestModel()  # type: ignore[call-arg]

    result = format_validation_error(exc_info.value)
    assert isinstance(result, str)
    assert "name" in result
