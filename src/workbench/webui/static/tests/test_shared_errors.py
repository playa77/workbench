"""Tests for shared.errors — exception hierarchy."""

from workbench.shared.errors import (
    ConfigError,
    DatabaseError,
    EmbeddingError,
    RouterExhaustedError,
)


def test_router_exhausted_error():
    err = RouterExhaustedError("all models failed")
    assert str(err) == "all models failed"
    assert isinstance(err, Exception)


def test_embedding_error():
    err = EmbeddingError("embedding failed")
    assert str(err) == "embedding failed"
    assert isinstance(err, Exception)


def test_config_error_with_code():
    err = ConfigError("bad config", code="invalid_key")
    assert err.message == "bad config"
    assert err.code == "invalid_key"
    assert str(err) == "bad config"
    assert isinstance(err, Exception)


def test_config_error_default_code():
    err = ConfigError("bad config")
    assert err.code == "config_error"


def test_database_error():
    err = DatabaseError("connection failed")
    assert str(err) == "connection failed"
    assert isinstance(err, Exception)
