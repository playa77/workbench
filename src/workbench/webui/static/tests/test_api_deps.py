"""Tests for workbench.api.deps."""

from workbench.api import deps
from workbench.core.auth import get_current_user
from workbench.core.db import get_session


def test_get_current_user_is_reexported():
    assert deps.get_current_user is get_current_user


def test_get_session_is_reexported():
    assert deps.get_session is get_session


def test_all_contains_exactly_two_names():
    assert deps.__all__ == ["get_current_user", "get_session"]
