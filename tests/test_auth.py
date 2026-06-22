"""Tests for workbench.core.auth."""

from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from workbench.core.auth import (
    generate_api_key,
    verify_api_key,
)
from workbench.core.encryption import init_encryption
from workbench.core.models import User, UserApiKey
from workbench.core.config import WorkbenchConfig


def test_generate_api_key_format():
    raw, hashed, lookup = generate_api_key()
    assert raw.startswith("wb-")
    assert len(raw) > 40
    assert raw != hashed
    assert lookup is not None


def test_generate_api_key_custom_prefix():
    raw, hashed, lookup = generate_api_key(prefix="xyz")
    assert raw.startswith("xyz-")
    assert verify_api_key(raw, hashed) is True


def test_generate_api_key_uniqueness():
    raw1, _, _ = generate_api_key()
    raw2, _, _ = generate_api_key()
    assert raw1 != raw2


def test_verify_correct_key():
    raw, hashed, lookup = generate_api_key()
    assert verify_api_key(raw, hashed) is True


def test_verify_wrong_key():
    raw, hashed, lookup = generate_api_key()
    wrong = "wb-wrong-key-value-that-doesnt-match"
    assert verify_api_key(wrong, hashed) is False


def test_verify_empty_key():
    _, hashed, _ = generate_api_key()
    assert verify_api_key("", hashed) is False


