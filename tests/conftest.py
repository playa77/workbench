"""Test fixtures for Workbench core."""

import secrets
import sys
from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from workbench.core.config import WorkbenchConfig


@pytest.fixture
def test_config() -> WorkbenchConfig:
    return WorkbenchConfig(
        log_level="DEBUG",
        database_url="sqlite+aiosqlite:///:memory:",
        encryption_key=secrets.token_hex(32),
        auth_api_key_prefix="wb",
        auth_max_keys_per_user=5,
    )


@pytest.fixture
def test_config_no_encryption_key() -> WorkbenchConfig:
    return WorkbenchConfig(
        log_level="DEBUG",
        database_url="sqlite+aiosqlite:///:memory:",
        encryption_key="",
        auth_api_key_prefix="wb",
    )


@pytest_asyncio.fixture
async def _db_engine_and_sessionmaker(test_config: WorkbenchConfig):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(_create_all_tables)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    yield engine, session_factory
    await engine.dispose()


def _create_all_tables(connection):
    from workbench.core.models import Base
    Base.metadata.create_all(connection)

    connection.execute(text(
        """CREATE TABLE IF NOT EXISTS news_interests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            name TEXT NOT NULL,
            start_time TEXT NOT NULL DEFAULT '04:00',
            interval_hours INTEGER NOT NULL DEFAULT 24,
            target_summary_words INTEGER NOT NULL DEFAULT 750,
            target_script_words INTEGER NOT NULL DEFAULT 1250,
            target_script_de_words INTEGER NOT NULL DEFAULT 1250,
            target_brief_words INTEGER NOT NULL DEFAULT 600,
            enable_summary INTEGER NOT NULL DEFAULT 1,
            enable_script INTEGER NOT NULL DEFAULT 1,
            enable_script_de INTEGER NOT NULL DEFAULT 0,
            enable_brief INTEGER NOT NULL DEFAULT 1,
            enable_email INTEGER NOT NULL DEFAULT 0,
            input_data_length_mode TEXT NOT NULL DEFAULT 'full_article',
            input_word_count INTEGER NOT NULL DEFAULT 256,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )"""
    ))
    connection.execute(text(
        """CREATE TABLE IF NOT EXISTS news_feeds (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            interest_id INTEGER NOT NULL,
            url TEXT NOT NULL,
            name TEXT NOT NULL,
            category TEXT NOT NULL DEFAULT 'news',
            UNIQUE(interest_id, url)
        )"""
    ))
    connection.execute(text(
        """CREATE TABLE IF NOT EXISTS news_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            interest_id INTEGER NOT NULL,
            run_date TEXT NOT NULL,
            started_at TEXT NOT NULL DEFAULT (datetime('now')),
            completed_at TEXT,
            status TEXT NOT NULL DEFAULT 'running',
            current_stage TEXT,
            error TEXT
        )"""
    ))
    connection.execute(text(
        """CREATE TABLE IF NOT EXISTS news_articles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id INTEGER NOT NULL,
            feed_id INTEGER NOT NULL,
            url TEXT NOT NULL UNIQUE,
            title TEXT NOT NULL,
            author TEXT,
            published_at TEXT NOT NULL,
            scraped_at TEXT NOT NULL DEFAULT (datetime('now')),
            excerpt TEXT,
            content TEXT,
            content_status TEXT NOT NULL DEFAULT 'full'
        )"""
    ))
    connection.execute(text(
        """CREATE TABLE IF NOT EXISTS news_themes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            source_article_ids TEXT NOT NULL,
            order_index INTEGER NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )"""
    ))
    connection.execute(text(
        """CREATE TABLE IF NOT EXISTS news_deliverables (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            theme_id INTEGER NOT NULL,
            deliverable_type TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )"""
    ))
    connection.execute(text(
        """CREATE TABLE IF NOT EXISTS news_briefs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id INTEGER NOT NULL,
            content TEXT NOT NULL,
            word_count INTEGER NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )"""
    ))


@pytest_asyncio.fixture
async def db_session(_db_engine_and_sessionmaker) -> AsyncGenerator[AsyncSession, None]:
    _, session_factory = _db_engine_and_sessionmaker
    async with session_factory() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def db_engine(_db_engine_and_sessionmaker):
    engine, _ = _db_engine_and_sessionmaker
    return engine


@pytest.fixture
def setup_encryption(test_config: WorkbenchConfig):
    from workbench.core.encryption import init_encryption
    init_encryption(test_config)
    return test_config.encryption_key


@pytest_asyncio.fixture
async def registered_user(db_session: AsyncSession) -> tuple[str, str]:
    from uuid import uuid4
    from workbench.core.models import User, UserApiKey
    from workbench.core.auth import generate_api_key

    user = User(id=uuid4(), username="testuser")
    db_session.add(user)
    await db_session.flush()

    raw_key, hashed = generate_api_key()
    api_key = UserApiKey(user_id=user.id, key_hash=hashed, label="test-key")
    db_session.add(api_key)
    await db_session.commit()

    return str(user.id), raw_key
