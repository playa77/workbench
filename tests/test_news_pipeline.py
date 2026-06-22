"""Tests for workbench.services.news_pipeline — core orchestration."""

import json
from unittest.mock import ANY, AsyncMock, MagicMock, patch

import pytest

from workbench.services.news_pipeline import NewsPipeline, detect_language


# ---------------------------------------------------------------------------
# detect_language
# ---------------------------------------------------------------------------

class TestDetectLanguage:
    def test_empty_text_returns_en(self):
        assert detect_language("") == "en"

    def test_whitespace_only_returns_en(self):
        assert detect_language("   ") == "en"

    def test_german_dominant_returns_de(self):
        text = "der die das und ist sind ein eine auf für"
        assert detect_language(text) == "de"

    def test_english_dominant_returns_en(self):
        text = "the a an and is are was were for with from to"
        assert detect_language(text) == "en"

    def test_equal_mix_falls_to_en(self):
        # equal counts, en_count * 1.5 > de_count so "en"
        text = "the der a die"
        assert detect_language(text) == "en"

    def test_german_just_over_threshold(self):
        # de_count=2, en_count=1 -> 2 > 1*1.5=1.5 -> "de"
        text = "der die the"
        assert detect_language(text) == "de"

    def test_exception_returns_en(self):
        # Trigger the exception path inside detect_language
        # using a custom object that raises on .split()
        class WeirdText:
            def lower(self):
                return self
            def split(self):
                raise RuntimeError("boom")
        assert detect_language(WeirdText()) == "en"  # type: ignore[arg-type]

    def test_empty_after_split_returns_en(self):
        # text with only whitespace should be caught by empty check
        assert detect_language("   ") == "en"


# ---------------------------------------------------------------------------
# NewsPipeline
# ---------------------------------------------------------------------------

@pytest.fixture
def store():
    return AsyncMock()


@pytest.fixture
def interest():
    return {
        "id": 1,
        "name": "TestInterest",
        "article_fetch_timeout_seconds": 15,
        "input_data_length_mode": "full_article",
        "max_themes_source_articles": 30,
        "max_themes": 5,
        "analysis_model": "some-model",
        "generation_model": "gen-model",
        "brief_model": "brief-model",
        "enable_summary": True,
        "enable_script": True,
        "enable_script_de": False,
        "enable_brief": True,
        "target_summary_words": 750,
        "target_script_words": 1250,
        "target_brief_words": 600,
    }


@pytest.fixture
def llm():
    return AsyncMock()


# ---- run ----

@pytest.mark.asyncio
async def test_run_success(store, interest, llm):
    with patch("workbench.services.news_pipeline.OpenRouterClient", return_value=llm) as mock_cls:
        store.create_run.return_value = {"id": 10}
        pipeline = NewsPipeline(store=store, session=MagicMock())
        run_id = await pipeline.run("user1", interest, "sk-xxx")

    assert run_id == 10
    store.create_run.assert_awaited_once_with(1)
    store.update_run.assert_awaited_with(10, status="completed", completed_at=ANY)
    llm.close.assert_awaited_once()
    mock_cls.assert_called_once_with(api_key="sk-xxx", rate_limit_user_id="user1")


@pytest.mark.asyncio
async def test_run_failure(store, interest, llm):
    store.create_run.return_value = {"id": 20}

    # Make _scrape raise
    with patch("workbench.services.news_pipeline.OpenRouterClient", return_value=llm):
        pipeline = NewsPipeline(store=store, session=MagicMock())
        pipeline._scrape = AsyncMock(side_effect=ValueError("scrape failed"))
        run_id = await pipeline.run("user1", interest, "sk-xxx")

    assert run_id == 20
    store.update_run.assert_awaited_with(20, status="failed", error="scrape failed")
    llm.close.assert_awaited_once()


# ---- _scrape ----

@pytest.mark.asyncio
async def test_scrape_no_feeds(store, interest, llm):
    store.get_feeds_for_interest.return_value = []
    pipeline = NewsPipeline(store=store, session=MagicMock())
    await pipeline._scrape(1, 1, interest)

    store.get_feeds_for_interest.assert_awaited_once_with(1)
    store.insert_article.assert_not_called()


@pytest.mark.asyncio
async def test_scrape_with_feeds(store, interest):
    store.get_feeds_for_interest.return_value = [
        {"id": 1, "url": "http://example.com/rss", "name": "Feed1"},
    ]

    parse_result = MagicMock()
    entry = MagicMock()
    entry.get.side_effect = lambda k, d=None: {
        "link": "http://example.com/article1",
        "title": "Article 1",
        "published": "2025-06-01",
        "author": "Author1",
        "summary": "Excerpt here",
    }.get(k, d)
    parse_result.entries = [entry]
    parse_result.__len__ = lambda _: 1

    store.article_exists.return_value = False

    with patch("feedparser.parse", return_value=parse_result):
        with patch("httpx.AsyncClient") as mock_http_cls:
            mock_http = AsyncMock()
            mock_http_cls.return_value.__aenter__.return_value = mock_http
            mock_resp = MagicMock()
            mock_resp.text = "<html><body>Article content</body></html>"
            mock_http.get.return_value = mock_resp

            with patch("trafilatura.extract", return_value="Full article content here."):
                pipeline = NewsPipeline(store=store, session=MagicMock())
                await pipeline._scrape(1, 1, interest)

    store.insert_article.assert_awaited_once_with(
        run_id=1,
        feed_id=1,
        url="http://example.com/article1",
        title="Article 1",
        author="Author1",
        published_at="2025-06-01",
        excerpt="Excerpt here",
        content="Full article content here.",
        content_status="full",
    )


@pytest.mark.asyncio
async def test_scrape_skip_existing_article(store, interest):
    store.get_feeds_for_interest.return_value = [
        {"id": 1, "url": "http://example.com/rss", "name": "Feed1"},
    ]

    parse_result = MagicMock()
    entry = MagicMock()
    entry.get.side_effect = lambda k, d=None: {
        "link": "http://example.com/article1",
        "title": "Title",
        "published": "2025-01-01",
        "author": "",
        "summary": "",
    }.get(k, d)
    parse_result.entries = [entry]
    parse_result.__len__ = lambda _: 1

    store.article_exists.return_value = True  # already exists

    with patch("feedparser.parse", return_value=parse_result):
        pipeline = NewsPipeline(store=store, session=MagicMock())
        await pipeline._scrape(1, 1, interest)

    store.insert_article.assert_not_called()


@pytest.mark.asyncio
async def test_scrape_skip_missing_url(store, interest):
    store.get_feeds_for_interest.return_value = [
        {"id": 1, "url": "http://example.com/rss", "name": "Feed1"},
    ]

    parse_result = MagicMock()
    entry = MagicMock()
    entry.get.side_effect = lambda k, d=None: {
        "link": "",  # empty link
        "title": "Title",
        "published": "2025-01-01",
        "author": "",
        "summary": "",
    }.get(k, d)
    parse_result.entries = [entry]
    parse_result.__len__ = lambda _: 1

    with patch("feedparser.parse", return_value=parse_result):
        pipeline = NewsPipeline(store=store, session=MagicMock())
        await pipeline._scrape(1, 1, interest)

    store.insert_article.assert_not_called()


@pytest.mark.asyncio
async def test_scrape_fetch_or_extract_fails(store, interest):
    """HTTP get or trafilatura extract fails -> content_status=excerpt."""
    store.get_feeds_for_interest.return_value = [
        {"id": 1, "url": "http://example.com/rss", "name": "Feed1"},
    ]

    parse_result = MagicMock()
    entry = MagicMock()
    entry.get.side_effect = lambda k, d=None: {
        "link": "http://example.com/article1",
        "title": "Title",
        "published": "2025-01-01",
        "author": "",
        "summary": "Some excerpt",
    }.get(k, d)
    parse_result.entries = [entry]
    parse_result.__len__ = lambda _: 1

    store.article_exists.return_value = False

    with patch("feedparser.parse", return_value=parse_result):
        with patch("httpx.AsyncClient") as mock_http_cls:
            mock_http = AsyncMock()
            mock_http_cls.return_value.__aenter__.return_value = mock_http
            mock_http.get.side_effect = ValueError("connection error")

            pipeline = NewsPipeline(store=store, session=MagicMock())
            await pipeline._scrape(1, 1, interest)

    store.insert_article.assert_awaited_once()
    call_kwargs = store.insert_article.call_args[1]
    assert call_kwargs["content"] is None
    assert call_kwargs["content_status"] == "excerpt"


@pytest.mark.asyncio
async def test_scrape_headers_only_mode(store, interest):
    """input_data_length_mode=headers_only -> content=None even if extracted."""
    interest["input_data_length_mode"] = "headers_only"
    store.get_feeds_for_interest.return_value = [
        {"id": 1, "url": "http://example.com/rss", "name": "Feed1"},
    ]

    parse_result = MagicMock()
    entry = MagicMock()
    entry.get.side_effect = lambda k, d=None: {
        "link": "http://example.com/a1",
        "title": "Title",
        "published": "2025-01-01",
        "author": "",
        "summary": "",
    }.get(k, d)
    parse_result.entries = [entry]
    parse_result.__len__ = lambda _: 1

    store.article_exists.return_value = False

    with patch("feedparser.parse", return_value=parse_result):
        with patch("httpx.AsyncClient") as mock_http_cls:
            mock_http = AsyncMock()
            mock_http_cls.return_value.__aenter__.return_value = mock_http
            mock_resp = MagicMock()
            mock_resp.text = "<html>content</html>"
            mock_http.get.return_value = mock_resp
            with patch("trafilatura.extract", return_value="Extracted full text"):
                pipeline = NewsPipeline(store=store, session=MagicMock())
                await pipeline._scrape(1, 1, interest)

    call_kwargs = store.insert_article.call_args[1]
    assert call_kwargs["content"] is None
    assert call_kwargs["content_status"] == "excerpt"


@pytest.mark.asyncio
async def test_scrape_word_count_mode_truncated(store, interest):
    """input_data_length_mode=word_count with truncation."""
    interest["input_data_length_mode"] = "word_count"
    interest["input_word_count"] = 5
    store.get_feeds_for_interest.return_value = [
        {"id": 1, "url": "http://example.com/rss", "name": "Feed1"},
    ]

    parse_result = MagicMock()
    entry = MagicMock()
    entry.get.side_effect = lambda k, d=None: {
        "link": "http://example.com/a1",
        "title": "Title",
        "published": "2025-01-01",
        "author": "",
        "summary": "",
    }.get(k, d)
    parse_result.entries = [entry]
    parse_result.__len__ = lambda _: 1

    store.article_exists.return_value = False

    with patch("feedparser.parse", return_value=parse_result):
        with patch("httpx.AsyncClient") as mock_http_cls:
            mock_http = AsyncMock()
            mock_http_cls.return_value.__aenter__.return_value = mock_http
            mock_resp = MagicMock()
            mock_resp.text = "<html>content</html>"
            mock_http.get.return_value = mock_resp
            with patch("trafilatura.extract", return_value="one two three four five six seven eight"):
                pipeline = NewsPipeline(store=store, session=MagicMock())
                await pipeline._scrape(1, 1, interest)

    call_kwargs = store.insert_article.call_args[1]
    assert call_kwargs["content"] == "one two three four five"
    assert call_kwargs["content_status"] == "word_count"


@pytest.mark.asyncio
async def test_scrape_word_count_no_truncation(store, interest):
    """input_data_length_mode=word_count but content shorter than limit."""
    interest["input_data_length_mode"] = "word_count"
    interest["input_word_count"] = 100
    store.get_feeds_for_interest.return_value = [
        {"id": 1, "url": "http://example.com/rss", "name": "Feed1"},
    ]

    parse_result = MagicMock()
    entry = MagicMock()
    entry.get.side_effect = lambda k, d=None: {
        "link": "http://example.com/a1",
        "title": "Title",
        "published": "2025-01-01",
        "author": "",
        "summary": "",
    }.get(k, d)
    parse_result.entries = [entry]
    parse_result.__len__ = lambda _: 1

    store.article_exists.return_value = False

    with patch("feedparser.parse", return_value=parse_result):
        with patch("httpx.AsyncClient") as mock_http_cls:
            mock_http = AsyncMock()
            mock_http_cls.return_value.__aenter__.return_value = mock_http
            mock_resp = MagicMock()
            mock_resp.text = "<html>content</html>"
            mock_http.get.return_value = mock_resp
            with patch("trafilatura.extract", return_value="short text"):
                pipeline = NewsPipeline(store=store, session=MagicMock())
                await pipeline._scrape(1, 1, interest)

    call_kwargs = store.insert_article.call_args[1]
    assert call_kwargs["content"] == "short text"
    assert call_kwargs["content_status"] == "full"


@pytest.mark.asyncio
async def test_scrape_feed_failure_logged(store, interest):
    """If feedparser raises for one feed, other feeds still process."""
    store.get_feeds_for_interest.return_value = [
        {"id": 1, "url": "http://badfeed.com/rss", "name": "Bad"},
        {"id": 2, "url": "http://goodfeed.com/rss", "name": "Good"},
    ]

    parse_result = MagicMock()
    entry = MagicMock()
    entry.get.side_effect = lambda k, d=None: {
        "link": "http://example.com/a1",
        "title": "Title",
        "published": "2025-01-01",
        "author": "",
        "summary": "",
    }.get(k, d)
    parse_result.entries = [entry]
    parse_result.__len__ = lambda _: 1

    store.article_exists.return_value = False

    # First feed will raise, second succeeds
    call_count = 0

    def parse_side_effect(url):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise ValueError("Feed parse error")
        return parse_result

    with patch("feedparser.parse", side_effect=parse_side_effect):
        with patch("httpx.AsyncClient") as mock_http_cls:
            mock_http = AsyncMock()
            mock_http_cls.return_value.__aenter__.return_value = mock_http
            mock_resp = MagicMock()
            mock_resp.text = "<html>content</html>"
            mock_http.get.return_value = mock_resp
            with patch("trafilatura.extract", return_value="full text"):
                pipeline = NewsPipeline(store=store, session=MagicMock())
                await pipeline._scrape(1, 1, interest)

    # Only second feed's article is inserted
    assert store.insert_article.await_count == 1


# ---- _analyze ----

@pytest.mark.asyncio
async def test_analyze_no_articles(store, interest, llm):
    store.get_articles_for_run.return_value = []
    pipeline = NewsPipeline(store=store, session=MagicMock())
    await pipeline._analyze(1, interest, llm)

    store.get_articles_for_run.assert_awaited_once_with(1)
    llm.chat_completion.assert_not_called()


@pytest.mark.asyncio
async def test_analyze_success(store, interest, llm):
    article = {
        "title": "Article 1",
        "url": "http://example.com/1",
        "content": "Some article content here that is long enough.",
        "excerpt": "Excerpt",
    }
    store.get_articles_for_run.return_value = [article]

    llm.chat_completion.return_value = json.dumps([
        {"title": "Theme 1", "description": "Description 1", "article_indices": [1]},
        {"title": "Theme 2", "description": "Description 2", "article_indices": [1, 2]},
    ])

    pipeline = NewsPipeline(store=store, session=MagicMock())
    await pipeline._analyze(1, interest, llm)

    llm.chat_completion.assert_awaited_once()
    assert store.insert_theme.await_count == 2
    store.insert_theme.assert_any_await(run_id=1, title="Theme 1", description="Description 1",
                                         source_article_ids=[1], order_index=0)
    store.insert_theme.assert_any_await(run_id=1, title="Theme 2", description="Description 2",
                                         source_article_ids=[1, 2], order_index=1)


@pytest.mark.asyncio
async def test_analyze_truncates_long_body(store, interest, llm):
    """Article content over 2000 chars is truncated."""
    article = {
        "title": "Long Article",
        "url": "http://example.com/long",
        "content": "x" * 3000,
        "excerpt": "Short excerpt",
    }
    store.get_articles_for_run.return_value = [article]

    llm.chat_completion.return_value = "[]"

    pipeline = NewsPipeline(store=store, session=MagicMock())
    await pipeline._analyze(1, interest, llm)

    # Verify prompt contains truncated body
    sent_prompt = llm.chat_completion.call_args[1]["messages"][1]["content"]
    assert "x" * 2000 in sent_prompt


@pytest.mark.asyncio
async def test_analyze_no_content_or_excerpt(store, interest, llm):
    """Article with no content and no excerpt -> empty body."""
    article = {
        "title": "No content",
        "url": "http://example.com/nc",
        "content": None,
        "excerpt": None,
    }
    store.get_articles_for_run.return_value = [article]

    llm.chat_completion.return_value = "[]"

    pipeline = NewsPipeline(store=store, session=MagicMock())
    await pipeline._analyze(1, interest, llm)

    sent_prompt = llm.chat_completion.call_args[1]["messages"][1]["content"]
    assert "Body: " in sent_prompt


@pytest.mark.asyncio
async def test_analyze_limits_articles(store, interest, llm):
    """Only first max_themes_source_articles are included."""
    interest["max_themes_source_articles"] = 2
    store.get_articles_for_run.return_value = [
        {"title": f"A{i}", "url": f"http://example.com/{i}", "content": "content", "excerpt": ""}
        for i in range(5)
    ]

    llm.chat_completion.return_value = "[]"

    pipeline = NewsPipeline(store=store, session=MagicMock())
    await pipeline._analyze(1, interest, llm)

    sent_prompt = llm.chat_completion.call_args[1]["messages"][1]["content"]
    # Only 2 articles should appear
    assert "[1]" in sent_prompt
    assert "[2]" in sent_prompt
    assert "[3]" not in sent_prompt


@pytest.mark.asyncio
async def test_analyze_no_json_match(store, interest, llm):
    """LLM returns text without JSON array -> no themes inserted."""
    store.get_articles_for_run.return_value = [
        {"title": "A1", "url": "http://example.com/1", "content": "content", "excerpt": ""},
    ]

    llm.chat_completion.return_value = "No JSON here at all"

    pipeline = NewsPipeline(store=store, session=MagicMock())
    await pipeline._analyze(1, interest, llm)

    store.insert_theme.assert_not_called()


@pytest.mark.asyncio
async def test_analyze_llm_exception(store, interest, llm):
    """LLM raises -> logged, no themes inserted."""
    store.get_articles_for_run.return_value = [
        {"title": "A1", "url": "http://example.com/1", "content": "content", "excerpt": ""},
    ]

    llm.chat_completion.side_effect = ValueError("API error")

    pipeline = NewsPipeline(store=store, session=MagicMock())
    await pipeline._analyze(1, interest, llm)

    store.insert_theme.assert_not_called()


@pytest.mark.asyncio
async def test_analyze_limits_themes(store, interest, llm):
    """Only first max_themes themes are stored."""
    interest["max_themes"] = 2
    store.get_articles_for_run.return_value = [
        {"title": "A1", "url": "http://example.com/1", "content": "content", "excerpt": ""},
    ]

    llm.chat_completion.return_value = json.dumps([
        {"title": "T1", "description": "D1", "article_indices": [1]},
        {"title": "T2", "description": "D2", "article_indices": [2]},
        {"title": "T3", "description": "D3", "article_indices": [3]},
    ])

    pipeline = NewsPipeline(store=store, session=MagicMock())
    await pipeline._analyze(1, interest, llm)

    assert store.insert_theme.await_count == 2


# ---- _generate ----

@pytest.mark.asyncio
async def test_generate_no_themes(store, interest, llm):
    store.get_themes_for_run.return_value = []
    pipeline = NewsPipeline(store=store, session=MagicMock())
    await pipeline._generate(1, interest, llm)

    llm.chat_completion.assert_not_called()


@pytest.mark.asyncio
async def test_generate_full(store, interest, llm):
    """All three deliverable types generated."""
    interest["enable_script_de"] = True
    store.get_themes_for_run.return_value = [
        {"id": 10, "title": "Theme 1", "description": "Description of theme 1"},
    ]

    llm.chat_completion.return_value = "Generated content"

    pipeline = NewsPipeline(store=store, session=MagicMock())
    await pipeline._generate(1, interest, llm)

    # 3 chat_completion calls (summary, script, script_de)
    assert llm.chat_completion.await_count == 3
    assert store.insert_deliverable.await_count == 3
    store.insert_deliverable.assert_any_await(10, "summary", "Generated content")
    store.insert_deliverable.assert_any_await(10, "script", "Generated content")
    store.insert_deliverable.assert_any_await(10, "script_de", "Generated content")


@pytest.mark.asyncio
async def test_generate_summary_disabled(store, interest, llm):
    """Only summary disabled -> script still generated."""
    interest["enable_summary"] = False
    store.get_themes_for_run.return_value = [
        {"id": 10, "title": "Theme 1", "description": "Desc"},
    ]

    llm.chat_completion.return_value = "Script content"

    pipeline = NewsPipeline(store=store, session=MagicMock())
    await pipeline._generate(1, interest, llm)

    assert llm.chat_completion.await_count == 1  # only script
    store.insert_deliverable.assert_awaited_once_with(10, "script", "Script content")


@pytest.mark.asyncio
async def test_generate_exception_continues(store, interest, llm):
    """Exception in generate for one theme -> logged, continues to next."""
    store.get_themes_for_run.return_value = [
        {"id": 10, "title": "Theme 1", "description": "Desc 1"},
        {"id": 11, "title": "Theme 2", "description": "Desc 2"},
    ]

    # First call raises, second succeeds for Theme 1
    # Then for Theme 2, first call raises, second succeeds
    llm.chat_completion.side_effect = [
        ValueError("gen error"),  # Theme 1 summary -> fails, entire theme skipped
        "Good content 1",         # Theme 2 summary -> succeeds
        "Good content 2",         # Theme 2 script -> succeeds
    ]

    pipeline = NewsPipeline(store=store, session=MagicMock())
    await pipeline._generate(1, interest, llm)

    # 3 chat_completion calls (Theme 1: 1 failed summary; Theme 2: 2 successes)
    assert llm.chat_completion.await_count == 3
    # Only 2 successful ones should produce inserts
    assert store.insert_deliverable.await_count == 2


# ---- _brief ----

@pytest.mark.asyncio
async def test_brief_disabled(store, interest, llm):
    interest["enable_brief"] = False
    pipeline = NewsPipeline(store=store, session=MagicMock())
    await pipeline._brief(1, interest, llm)

    llm.chat_completion.assert_not_called()


@pytest.mark.asyncio
async def test_brief_no_themes(store, interest, llm):
    store.get_themes_for_run.return_value = []
    pipeline = NewsPipeline(store=store, session=MagicMock())
    await pipeline._brief(1, interest, llm)

    llm.chat_completion.assert_not_called()


@pytest.mark.asyncio
async def test_brief_english(store, interest, llm):
    store.get_themes_for_run.return_value = [
        {"title": "Theme 1", "description": "Description 1"},
    ]
    llm.chat_completion.return_value = "Brief content in English."

    pipeline = NewsPipeline(store=store, session=MagicMock())
    await pipeline._brief(1, interest, llm)

    llm.chat_completion.assert_awaited_once()
    sent_system = llm.chat_completion.call_args[1]["messages"][0]["content"]
    assert "executive editor" in sent_system
    store.insert_brief.assert_awaited_once_with(1, "Brief content in English.")


@pytest.mark.asyncio
async def test_brief_german(store, interest, llm):
    store.get_themes_for_run.return_value = [
        {"title": "Thema 1", "description": "der die das und ist"},
    ]
    llm.chat_completion.return_value = "Kurznachricht auf Deutsch."

    pipeline = NewsPipeline(store=store, session=MagicMock())
    await pipeline._brief(1, interest, llm)

    sent_system = llm.chat_completion.call_args[1]["messages"][0]["content"]
    assert "Redaktionsleiter" in sent_system
    store.insert_brief.assert_awaited_once_with(1, "Kurznachricht auf Deutsch.")


@pytest.mark.asyncio
async def test_brief_exception(store, interest, llm):
    store.get_themes_for_run.return_value = [
        {"title": "Theme 1", "description": "Desc"},
    ]
    llm.chat_completion.side_effect = ValueError("LLM error")

    pipeline = NewsPipeline(store=store, session=MagicMock())
    await pipeline._brief(1, interest, llm)

    store.insert_brief.assert_not_called()
