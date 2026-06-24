"""Tests for core.encryption — report content encryption/decryption toggle."""

import pytest

from workbench.core.encryption import (
    decrypt_report_content,
    encrypt_report_content,
    init_encryption,
    set_encrypt_reports,
)


@pytest.fixture(autouse=True)
def _reset_encrypt_reports():
    """Reset the encrypt_reports flag between tests."""
    set_encrypt_reports(False)
    yield
    set_encrypt_reports(False)


def test_encrypt_report_content_disabled(setup_encryption):
    set_encrypt_reports(False)
    result = encrypt_report_content("hello world")
    assert result == "hello world"


def test_encrypt_report_content_enabled(setup_encryption):
    set_encrypt_reports(True)
    result = encrypt_report_content("hello world")
    assert result != "hello world"
    # Should be base64-encoded ciphertext
    assert isinstance(result, str)


def test_decrypt_report_content_disabled(setup_encryption):
    set_encrypt_reports(False)
    result = decrypt_report_content("hello world")
    assert result == "hello world"


def test_decrypt_report_content_enabled(setup_encryption):
    set_encrypt_reports(True)
    encrypted = encrypt_report_content("hello world")
    decrypted = decrypt_report_content(encrypted)
    assert decrypted == "hello world"


def test_encrypt_decrypt_report_round_trip(setup_encryption):
    set_encrypt_reports(True)
    original = "Sensitive report content with special chars: <>&\"'"
    encrypted = encrypt_report_content(original)
    decrypted = decrypt_report_content(encrypted)
    assert decrypted == original


def test_set_encrypt_reports_toggle(setup_encryption):
    set_encrypt_reports(True)
    assert encrypt_report_content("test") != "test"

    set_encrypt_reports(False)
    assert encrypt_report_content("test") == "test"
