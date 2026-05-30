"""Tests for workbench.core.models."""

from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from workbench.core.models import (
    StoredReport,
    User,
    UserAgentSettings,
    UserApiKey,
    UserOpenRouterKey,
)


@pytest.mark.asyncio
async def test_create_user(db_session: AsyncSession):
    user = User(id=uuid4(), username="alice")
    db_session.add(user)
    await db_session.commit()

    result = await db_session.execute(select(User).where(User.username == "alice"))
    fetched = result.scalar_one()
    assert fetched.username == "alice"
    assert fetched.id == user.id


@pytest.mark.asyncio
async def test_user_username_unique(db_session: AsyncSession):
    u1 = User(id=uuid4(), username="bob")
    db_session.add(u1)
    await db_session.commit()

    u2 = User(id=uuid4(), username="bob")
    db_session.add(u2)
    with pytest.raises(Exception):
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_create_api_key(db_session: AsyncSession):
    user = User(id=uuid4(), username="carol")
    db_session.add(user)
    await db_session.flush()

    key = UserApiKey(user_id=user.id, key_hash="hashed-secret", label="default")
    db_session.add(key)
    await db_session.commit()

    result = await db_session.execute(select(UserApiKey).where(UserApiKey.user_id == user.id))
    fetched = result.scalar_one()
    assert fetched.key_hash == "hashed-secret"
    assert fetched.label == "default"
    assert fetched.last_used_at is None


@pytest.mark.asyncio
async def test_api_key_cascade_delete(db_session: AsyncSession):
    user = User(id=uuid4(), username="dave")
    db_session.add(user)
    await db_session.flush()

    key = UserApiKey(user_id=user.id, key_hash="hash", label="test")
    db_session.add(key)
    await db_session.commit()

    await db_session.delete(user)
    await db_session.commit()

    result = await db_session.execute(select(UserApiKey))
    assert len(result.scalars().all()) == 0


@pytest.mark.asyncio
async def test_openrouter_key_one_per_user(db_session: AsyncSession):
    user = User(id=uuid4(), username="eve")
    db_session.add(user)
    await db_session.flush()

    or_key = UserOpenRouterKey(user_id=user.id, encrypted_key="secret")
    db_session.add(or_key)
    await db_session.commit()

    result = await db_session.execute(
        select(UserOpenRouterKey).where(UserOpenRouterKey.user_id == user.id)
    )
    fetched = result.scalar_one()
    assert fetched.encrypted_key == "secret"


@pytest.mark.asyncio
async def test_agent_settings(db_session: AsyncSession):
    user = User(id=uuid4(), username="frank")
    db_session.add(user)
    await db_session.flush()

    settings = UserAgentSettings(
        user_id=user.id, agent_name="chat", enabled=True, settings={"model": "deepseek"}
    )
    db_session.add(settings)
    await db_session.commit()

    result = await db_session.execute(
        select(UserAgentSettings).where(
            UserAgentSettings.user_id == user.id, UserAgentSettings.agent_name == "chat"
        )
    )
    fetched = result.scalar_one()
    assert fetched.enabled is True
    assert fetched.settings == {"model": "deepseek"}


@pytest.mark.asyncio
async def test_agent_settings_unique_per_user(db_session: AsyncSession):
    user = User(id=uuid4(), username="grace")
    db_session.add(user)
    await db_session.flush()

    s1 = UserAgentSettings(user_id=user.id, agent_name="chat", enabled=True, settings={})
    db_session.add(s1)
    await db_session.commit()

    s2 = UserAgentSettings(user_id=user.id, agent_name="chat", enabled=False, settings={})
    db_session.add(s2)
    with pytest.raises(Exception):
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_stored_report(db_session: AsyncSession):
    user = User(id=uuid4(), username="heidi")
    db_session.add(user)
    await db_session.flush()

    report = StoredReport(
        user_id=user.id,
        agent_name="research",
        title="Test Report",
        content="# Findings\n\nImportant results.",
        content_format="markdown",
    )
    db_session.add(report)
    await db_session.commit()

    result = await db_session.execute(
        select(StoredReport).where(StoredReport.user_id == user.id)
    )
    fetched = result.scalar_one()
    assert fetched.title == "Test Report"
    assert fetched.content_format == "markdown"


@pytest.mark.asyncio
async def test_user_relationships(db_session: AsyncSession):
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    user = User(id=uuid4(), username="ivan")
    db_session.add(user)
    await db_session.flush()

    api_key = UserApiKey(user_id=user.id, key_hash="h1", label="key1")
    or_key = UserOpenRouterKey(user_id=user.id, encrypted_key="ek1")
    db_session.add_all([api_key, or_key])
    await db_session.commit()

    result = await db_session.execute(
        select(User)
        .where(User.id == user.id)
        .options(selectinload(User.api_keys), selectinload(User.openrouter_key))
    )
    fetched = result.scalar_one()
    assert len(fetched.api_keys) == 1
    assert fetched.openrouter_key is not None
    assert fetched.openrouter_key.encrypted_key == "ek1"
