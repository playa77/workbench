"""Tests for core.rate_limiter — Limiter singleton."""

from slowapi import Limiter

from workbench.core.rate_limiter import limiter


def test_limiter_is_instance():
    assert isinstance(limiter, Limiter)


def test_limiter_has_key_func():
    assert limiter._key_func is not None


def test_limiter_default_limits_empty():
    assert limiter._default_limits == []
