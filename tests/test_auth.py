"""Tests for workbench.core.auth."""

from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from workbench.core.auth import (
    generate_api_key,
    get_user_openrouter_key,
    set_user_openrouter_key,
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


@pytest.mark.asyncio
async def test_set_and_get_openrouter_key(db_session: AsyncSession, test_config: WorkbenchConfig):
    import secrets
    test_config.encryption_key = secrets.token_hex(32)
    init_encryption(test_config)

    user = User(id=uuid4(), username="keyuser")
    db_session.add(user)
    await db_session.flush()
    await db_session.commit()

    key_value = "sk-or-v1-test-key-12345"
    await set_user_openrouter_key(user, key_value, db_session)

    result = await get_user_openrouter_key(user, db_session)
    assert result == key_value


@pytest.mark.asyncio
async def test_set_openrouter_key_updates_existing(db_session: AsyncSession, test_config: WorkbenchConfig):
    import secrets
    test_config.encryption_key = secrets.token_hex(32)
    init_encryption(test_config)

    user = User(id=uuid4(), username="updateuser")
    db_session.add(user)
    await db_session.flush()
    await db_session.commit()

    await set_user_openrouter_key(user, "key-v1", db_session)
    await set_user_openrouter_key(user, "key-v2", db_session)

    result = await get_user_openrouter_key(user, db_session)
    assert result == "key-v2"


@pytest.mark.asyncio
async def test_get_openrouter_key_no_key(db_session: AsyncSession):
    user = User(id=uuid4(), username="nokeyuser")
    db_session.add(user)
    await db_session.flush()
    await db_session.commit()

    result = await get_user_openrouter_key(user, db_session)
    assert result is None
