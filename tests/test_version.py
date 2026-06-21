"""Tests for __version__."""

from workbench.__version__ import __version__


def test_version_string():
    assert __version__ == "0.1.0"


def test_version_is_str():
    assert isinstance(__version__, str)
