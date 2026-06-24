"""Tests for workbench.services.news_store — PostgreSQL-backed data store.

Uses the ``db_session`` conftest fixture backed by in-memory SQLite.
"""

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from workbench.services.news_store import NewsStore


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def store(db_session: AsyncSession) -> NewsStore:
    return NewsStore(db_session)


@pytest.fixture
async def sample_interest(store: NewsStore) -> dict:
    """Create a sample interest and return it."""
    return await store.create_interest("user1", {"name": "Test Interest", "start_time": "08:00"})


@pytest.fixture
async def sample_run(store: NewsStore, sample_interest: dict) -> dict:
    return await store.create_run(sample_interest["id"])


# ---------------------------------------------------------------------------
# _utcnow_iso / _todays_date_str (tested indirectly via create_run)
# ---------------------------------------------------------------------------


class TestInterests:
    @pytest.mark.asyncio
    async def test_create_interest(self, store: NewsStore):
        data = {
            "name": "AI News",
            "start_time": "06:00",
            "interval_hours": 12,
            "target_summary_words": 500,
            "enable_summary": True,
            "enable_script": False,
        }
        interest = await store.create_interest("user1", data)
        assert interest["id"] > 0
        assert interest["name"] == "AI News"
        assert interest["user_id"] == "user1"
        assert interest["start_time"] == "06:00"

    @pytest.mark.asyncio
    async def test_create_interest_defaults(self, store: NewsStore):
        interest = await store.create_interest("user1", {})
        assert interest["name"] == "New Interest"
        assert interest["start_time"] == "04:00"
        assert interest["interval_hours"] == 24
        assert interest["enable_summary"] == 1

    @pytest.mark.asyncio
    async def test_list_interests(self, store: NewsStore, sample_interest: dict):
        # Create a second interest for a different user
        await store.create_interest("user2", {"name": "User2 Interest"})
        interests = await store.list_interests("user1")
        assert len(interests) == 1
        assert interests[0]["name"] == "Test Interest"

    @pytest.mark.asyncio
    async def test_get_interest_found(self, store: NewsStore, sample_interest: dict):
        got = await store.get_interest("user1", sample_interest["id"])
        assert got is not None
        assert got["name"] == "Test Interest"

    @pytest.mark.asyncio
    async def test_get_interest_not_found_wrong_user(self, store: NewsStore, sample_interest: dict):
        got = await store.get_interest("user2", sample_interest["id"])
        assert got is None

    @pytest.mark.asyncio
    async def test_get_interest_not_found_wrong_id(self, store: NewsStore):
        got = await store.get_interest("user1", 9999)
        assert got is None

    @pytest.mark.asyncio
    async def test_delete_interest(self, store: NewsStore, sample_interest: dict):
        await store.delete_interest("user1", sample_interest["id"])
        got = await store.get_interest("user1", sample_interest["id"])
        assert got is None

    @pytest.mark.asyncio
    async def test_update_interest(self, store: NewsStore, sample_interest: dict):
        updated = await store.update_interest("user1", sample_interest["id"], {"name": "Updated Name"})
        assert updated is not None
        assert updated["name"] == "Updated Name"

    @pytest.mark.asyncio
    async def test_update_interest_not_found(self, store: NewsStore):
        updated = await store.update_interest("user2", 999, {"name": "Nope"})
        assert updated is None

    @pytest.mark.asyncio
    async def test_update_interest_no_changes(self, store: NewsStore, sample_interest: dict):
        updated = await store.update_interest("user1", sample_interest["id"], {})
        assert updated is not None
        assert updated["name"] == "Test Interest"

    @pytest.mark.asyncio
    async def test_update_interest_invalid_field(self, store: NewsStore, sample_interest: dict):
        """Fields not in updatable set are ignored."""
        updated = await store.update_interest("user1", sample_interest["id"], {"nonexistent": "value"})
        assert updated is not None
        # No error, just no changes

    @pytest.mark.asyncio
    async def test_list_all_interests_global(self, store: NewsStore, sample_interest: dict):
        await store.create_interest("user2", {"name": "Another"})
        all_i = await store.list_all_interests_global()
        assert len(all_i) >= 2


class TestFeeds:
    @pytest.mark.asyncio
    async def test_add_feed(self, store: NewsStore, sample_interest: dict):
        feed = await store.add_feed("user1", sample_interest["id"], "http://example.com/rss", "Example Feed", "tech")
        assert feed["id"] > 0
        assert feed["url"] == "http://example.com/rss"
        assert feed["name"] == "Example Feed"

    @pytest.mark.asyncio
    async def test_add_feed_upsert(self, store: NewsStore, sample_interest: dict):
        feed1 = await store.add_feed("user1", sample_interest["id"], "http://example.com/rss", "Old Name", "news")
        feed2 = await store.add_feed("user1", sample_interest["id"], "http://example.com/rss", "New Name", "tech")
        assert feed2["id"] == feed1["id"]
        assert feed2["name"] == "New Name"

    @pytest.mark.asyncio
    async def test_add_feed_interest_not_found(self, store: NewsStore):
        with pytest.raises(ValueError, match="Interest not found or access denied"):
            await store.add_feed("user1", 9999, "http://x.com/rss", "X", "news")

    @pytest.mark.asyncio
    async def test_list_feeds(self, store: NewsStore, sample_interest: dict):
        await store.add_feed("user1", sample_interest["id"], "http://a.com/rss", "Feed A", "news")
        await store.add_feed("user1", sample_interest["id"], "http://b.com/rss", "Feed B", "sports")
        feeds = await store.list_feeds("user1", sample_interest["id"])
        assert len(feeds) == 2

    @pytest.mark.asyncio
    async def test_list_feeds_wrong_user(self, store: NewsStore, sample_interest: dict):
        await store.add_feed("user1", sample_interest["id"], "http://a.com/rss", "Feed A", "news")
        feeds = await store.list_feeds("user2", sample_interest["id"])
        assert len(feeds) == 0

    @pytest.mark.asyncio
    async def test_delete_feed(self, store: NewsStore, sample_interest: dict):
        feed = await store.add_feed("user1", sample_interest["id"], "http://x.com/rss", "X", "news")
        await store.delete_feed("user1", sample_interest["id"], feed["id"])
        feeds = await store.list_feeds("user1", sample_interest["id"])
        assert len(feeds) == 0

    @pytest.mark.asyncio
    async def test_get_feeds_for_interest(self, store: NewsStore, sample_interest: dict):
        await store.add_feed("user1", sample_interest["id"], "http://a.com/rss", "A", "news")
        feeds = await store.get_feeds_for_interest(sample_interest["id"])
        assert len(feeds) == 1

    @pytest.mark.asyncio
    async def test_update_feed(self, store: NewsStore, sample_interest: dict):
        feed = await store.add_feed("user1", sample_interest["id"], "http://x.com/rss", "X", "news")
        updated = await store.update_feed("user1", sample_interest["id"], feed["id"], {"name": "Y"})
        assert updated is not None
        assert updated["name"] == "Y"

    @pytest.mark.asyncio
    async def test_update_feed_not_found_interest(self, store: NewsStore):
        updated = await store.update_feed("user1", 999, 1, {"name": "Y"})
        assert updated is None

    @pytest.mark.asyncio
    async def test_update_feed_no_changes(self, store: NewsStore, sample_interest: dict):
        feed = await store.add_feed("user1", sample_interest["id"], "http://x.com/rss", "X", "news")
        updated = await store.update_feed("user1", sample_interest["id"], feed["id"], {})
        assert updated is not None
        assert updated["name"] == "X"

    @pytest.mark.asyncio
    async def test_update_feed_invalid_field_ignored(self, store: NewsStore, sample_interest: dict):
        feed = await store.add_feed("user1", sample_interest["id"], "http://x.com/rss", "X", "news")
        updated = await store.update_feed("user1", sample_interest["id"], feed["id"], {"nonexistent": "val"})
        assert updated is not None
        assert updated["name"] == "X"

    @pytest.mark.asyncio
    async def test_update_feed_not_found(self, store: NewsStore, sample_interest: dict):
        updated = await store.update_feed("user1", sample_interest["id"], 9999, {"name": "Y"})
        assert updated is None


class TestRuns:
    @pytest.mark.asyncio
    async def test_create_run(self, store: NewsStore, sample_interest: dict):
        run = await store.create_run(sample_interest["id"])
        assert run["id"] > 0
        assert run["status"] == "running"
        assert run["interest_id"] == sample_interest["id"]

    @pytest.mark.asyncio
    async def test_get_run_found(self, store: NewsStore, sample_run: dict):
        got = await store.get_run(sample_run["id"])
        assert got is not None
        assert got["id"] == sample_run["id"]

    @pytest.mark.asyncio
    async def test_get_run_not_found(self, store: NewsStore):
        got = await store.get_run(9999)
        assert got is None

    @pytest.mark.asyncio
    async def test_get_run_for_user_found(self, store: NewsStore, sample_interest: dict, sample_run: dict):
        got = await store.get_run_for_user("user1", sample_run["id"])
        assert got is not None
        assert got["id"] == sample_run["id"]

    @pytest.mark.asyncio
    async def test_get_run_for_user_not_found(self, store: NewsStore, sample_run: dict):
        got = await store.get_run_for_user("user2", sample_run["id"])
        assert got is None

    @pytest.mark.asyncio
    async def test_update_run_allowed_cols(self, store: NewsStore, sample_run: dict):
        await store.update_run(sample_run["id"], status="completed", current_stage="brief")
        got = await store.get_run(sample_run["id"])
        assert got["status"] == "completed"
        assert got["current_stage"] == "brief"

    @pytest.mark.asyncio
    async def test_update_run_empty_kwargs(self, store: NewsStore, sample_run: dict):
        # Should not raise
        await store.update_run(sample_run["id"])

    @pytest.mark.asyncio
    async def test_update_run_disallowed_col(self, store: NewsStore, sample_run: dict):
        with pytest.raises(ValueError, match="unknown columns"):
            await store.update_run(sample_run["id"], invalid_col="value")

    @pytest.mark.asyncio
    async def test_list_runs(self, store: NewsStore, sample_interest: dict, sample_run: dict):
        runs = await store.list_runs("user1", sample_interest["id"])
        assert len(runs) == 1


class TestArticles:
    @pytest.mark.asyncio
    async def test_insert_article(self, store: NewsStore, sample_run: dict):
        art = await store.insert_article(
            run_id=sample_run["id"],
            feed_id=1,
            url="http://example.com/article1",
            title="Article 1",
            author="Author",
            published_at="2025-06-01T00:00:00",
            excerpt="Excerpt",
            content="Full content",
            content_status="full",
        )
        assert art["id"] > 0
        assert art["title"] == "Article 1"

    @pytest.mark.asyncio
    async def test_insert_article_on_conflict(self, store: NewsStore, sample_run: dict):
        art1 = await store.insert_article(
            run_id=sample_run["id"], feed_id=1,
            url="http://example.com/dup", title="First",
            author=None, published_at="2025-06-01", excerpt=None, content=None,
            content_status="excerpt",
        )
        art2 = await store.insert_article(
            run_id=sample_run["id"], feed_id=1,
            url="http://example.com/dup", title="Second (ignored)",
            author=None, published_at="2025-06-01", excerpt=None, content=None,
            content_status="full",
        )
        # ON CONFLICT DO NOTHING -> art2 should be empty dict
        assert art2 == {}

    @pytest.mark.asyncio
    async def test_article_exists_true(self, store: NewsStore, sample_run: dict):
        await store.insert_article(
            run_id=sample_run["id"], feed_id=1,
            url="http://example.com/exists", title="T",
            author=None, published_at="2025-06-01", excerpt=None, content=None,
            content_status="excerpt",
        )
        assert await store.article_exists("http://example.com/exists") is True

    @pytest.mark.asyncio
    async def test_article_exists_false(self, store: NewsStore):
        assert await store.article_exists("http://unknown.com/article") is False

    @pytest.mark.asyncio
    async def test_get_articles_for_run(self, store: NewsStore, sample_run: dict):
        await store.insert_article(
            run_id=sample_run["id"], feed_id=1,
            url="http://example.com/a1", title="A1",
            author=None, published_at="2025-06-01", excerpt=None, content=None,
            content_status="excerpt",
        )
        articles = await store.get_articles_for_run(sample_run["id"])
        assert len(articles) == 1
        assert articles[0]["title"] == "A1"


class TestThemes:
    @pytest.mark.asyncio
    async def test_insert_theme(self, store: NewsStore, sample_run: dict):
        theme = await store.insert_theme(
            run_id=sample_run["id"],
            title="Theme 1",
            description="Description",
            source_article_ids=[1, 2, 3],
            order_index=0,
        )
        assert theme["id"] > 0
        assert theme["title"] == "Theme 1"
        assert theme["run_id"] == sample_run["id"]

    @pytest.mark.asyncio
    async def test_get_themes_for_run(self, store: NewsStore, sample_run: dict):
        await store.insert_theme(sample_run["id"], "T1", "D1", [1], 1)
        await store.insert_theme(sample_run["id"], "T2", "D2", [2], 0)
        themes = await store.get_themes_for_run(sample_run["id"])
        assert len(themes) == 2
        # Ordered by order_index
        assert themes[0]["title"] == "T2"
        assert themes[1]["title"] == "T1"


class TestDeliverables:
    @pytest.mark.asyncio
    async def test_insert_deliverable(self, store: NewsStore, sample_run: dict):
        theme = await store.insert_theme(sample_run["id"], "T", "D", [1], 0)
        d = await store.insert_deliverable(theme["id"], "summary", "Summary content")
        assert d["id"] > 0
        assert d["deliverable_type"] == "summary"

    @pytest.mark.asyncio
    async def test_get_deliverables_for_theme(self, store: NewsStore, sample_run: dict):
        theme = await store.insert_theme(sample_run["id"], "T", "D", [1], 0)
        await store.insert_deliverable(theme["id"], "script", "Script content")
        await store.insert_deliverable(theme["id"], "summary", "Summary content")
        ds = await store.get_deliverables_for_theme(theme["id"])
        assert len(ds) == 2


class TestBriefs:
    @pytest.mark.asyncio
    async def test_insert_brief(self, store: NewsStore, sample_run: dict):
        b = await store.insert_brief(sample_run["id"], "Brief content here.")
        assert b["id"] > 0
        assert b["word_count"] == 3
        assert b["content"] == "Brief content here."

    @pytest.mark.asyncio
    async def test_get_daily_brief_for_run_found(self, store: NewsStore, sample_run: dict):
        await store.insert_brief(sample_run["id"], "Daily brief")
        b = await store.get_daily_brief_for_run(sample_run["id"])
        assert b is not None
        assert b["content"] == "Daily brief"

    @pytest.mark.asyncio
    async def test_get_daily_brief_for_run_not_found(self, store: NewsStore):
        b = await store.get_daily_brief_for_run(9999)
        assert b is None

    @pytest.mark.asyncio
    async def test_get_previous_brief_found(self, store: NewsStore, sample_run: dict):
        # First complete the run
        await store.update_run(sample_run["id"], status="completed")
        await store.insert_brief(sample_run["id"], "Previous brief")
        b = await store.get_previous_brief("2099-01-01")  # far in the future
        assert b is not None
        assert b["content"] == "Previous brief"

    @pytest.mark.asyncio
    async def test_get_previous_brief_not_found(self, store: NewsStore):
        b = await store.get_previous_brief("2000-01-01")
        assert b is None


class TestIsInterestRunning:
    @pytest.mark.asyncio
    async def test_is_running_true(self, store: NewsStore, sample_run: dict):
        assert await store.is_interest_running(sample_run["interest_id"]) is True

    @pytest.mark.asyncio
    async def test_is_running_false(self, store: NewsStore, sample_interest: dict):
        assert await store.is_interest_running(sample_interest["id"]) is False

    @pytest.mark.asyncio
    async def test_is_running_completed(self, store: NewsStore, sample_run: dict):
        await store.update_run(sample_run["id"], status="completed")
        assert await store.is_interest_running(sample_run["interest_id"]) is False


# ---------------------------------------------------------------------------
# RuntimeError paths for INSERT...RETURNING returning no rows
# ---------------------------------------------------------------------------


class TestRuntimeErrorPaths:
    """Test RuntimeError when INSERT RETURNING returns no rows."""

    @pytest.mark.asyncio
    async def test_create_interest_runtime_error(self, store: NewsStore, db_session: AsyncSession):
        """Line 84: RuntimeError when INSERT RETURNING returns no rows."""
        from unittest.mock import AsyncMock, MagicMock, patch

        mock_result = MagicMock()
        mock_result.first.return_value = None
        with patch.object(db_session, "execute", new=AsyncMock(return_value=mock_result)):
            with pytest.raises(RuntimeError, match="Failed to create interest"):
                await store.create_interest("user1", {"name": "Test"})

    @pytest.mark.asyncio
    async def test_add_feed_runtime_error(
        self, store: NewsStore, db_session: AsyncSession, sample_interest: dict,
    ):
        """Line 127: RuntimeError when INSERT RETURNING returns no rows."""
        from unittest.mock import AsyncMock, MagicMock, patch

        # Need get_interest to pass validation before the INSERT RETURNING
        with patch.object(store, "get_interest", return_value=sample_interest):
            mock_result = MagicMock()
            mock_result.first.return_value = None
            with patch.object(db_session, "execute", new=AsyncMock(return_value=mock_result)):
                with pytest.raises(RuntimeError, match="Failed to add feed"):
                    await store.add_feed("user1", sample_interest["id"], "http://x.com", "X", "news")

    @pytest.mark.asyncio
    async def test_create_run_runtime_error(self, store: NewsStore, db_session: AsyncSession, sample_interest: dict):
        """Line 161: RuntimeError when INSERT RETURNING returns no rows."""
        from unittest.mock import AsyncMock, MagicMock, patch

        mock_result = MagicMock()
        mock_result.first.return_value = None
        with patch.object(db_session, "execute", new=AsyncMock(return_value=mock_result)):
            with pytest.raises(RuntimeError, match="Failed to create run"):
                await store.create_run(sample_interest["id"])

    @pytest.mark.asyncio
    async def test_insert_theme_runtime_error(self, store: NewsStore, db_session: AsyncSession, sample_run: dict):
        """Line 268: RuntimeError when INSERT RETURNING returns no rows."""
        from unittest.mock import AsyncMock, MagicMock, patch

        mock_result = MagicMock()
        mock_result.first.return_value = None
        with patch.object(db_session, "execute", new=AsyncMock(return_value=mock_result)):
            with pytest.raises(RuntimeError, match="Failed to insert theme"):
                await store.insert_theme(sample_run["id"], "T", "D", [1], 0)

    @pytest.mark.asyncio
    async def test_insert_deliverable_runtime_error(self, store: NewsStore, db_session: AsyncSession, sample_run: dict):
        """Line 291: RuntimeError when INSERT RETURNING returns no rows."""
        from unittest.mock import AsyncMock, MagicMock, patch

        # First create a real theme
        theme = await store.insert_theme(sample_run["id"], "T", "D", [1], 0)
        mock_result = MagicMock()
        mock_result.first.return_value = None
        with patch.object(db_session, "execute", new=AsyncMock(return_value=mock_result)):
            with pytest.raises(RuntimeError, match="Failed to insert deliverable"):
                await store.insert_deliverable(theme["id"], "summary", "Content")

    @pytest.mark.asyncio
    async def test_insert_brief_runtime_error(self, store: NewsStore, db_session: AsyncSession, sample_run: dict):
        """Line 307: RuntimeError when INSERT RETURNING returns no rows."""
        from unittest.mock import AsyncMock, MagicMock, patch

        mock_result = MagicMock()
        mock_result.first.return_value = None
        with patch.object(db_session, "execute", new=AsyncMock(return_value=mock_result)):
            with pytest.raises(RuntimeError, match="Failed to insert brief"):
                await store.insert_brief(sample_run["id"], "Content")
