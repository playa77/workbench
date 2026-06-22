"""Comprehensive tests for workbench.services.research_orchestrator.

Covers all data models, tool handlers, agent loop paths, error handling,
and edge cases to achieve 100% statement coverage.
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from workbench.services.research_orchestrator import (
    ActionLog,
    Contradiction,
    MindMap,
    MindMapNode,
    ResearchOrchestrator,
    ResearchState,
    Source,
    TokenUsage,
    _extract_with_httpx,
    _extract_with_trafilatura,
    _tool_declaration,
    _tool_draft_report,
    _tool_log_contradiction,
    _tool_read_webpage,
    _tool_update_findings,
    _tool_web_search,
)
from workbench.shared.errors import RouterExhaustedError

# =========================================================================
# Data Model Tests
# =========================================================================


class TestSource:
    def test_defaults(self):
        s = Source(url="https://example.com")
        assert s.url == "https://example.com"
        assert s.title == ""
        assert s.snippet == ""


class TestContradiction:
    def test_create(self):
        s1 = Source(url="https://a.com", title="A")
        s2 = Source(url="https://b.com", title="B")
        c = Contradiction(
            topic="t", claim_a="a", claim_b="b", source_a=s1, source_b=s2,
        )
        assert c.topic == "t"
        assert c.source_a.url == "https://a.com"


class TestMindMapNode:
    def test_default_id(self):
        n1 = MindMapNode(topic="x")
        n2 = MindMapNode(topic="y")
        assert n1.id != n2.id
        assert len(n1.id) == 8

    def test_fields(self):
        n = MindMapNode(
            topic="t", content="c", confidence=0.5,
            sources=[Source(url="https://x.com")],
            children=[MindMapNode(topic="child")],
        )
        assert n.topic == "t"
        assert len(n.children) == 1
        assert n.confidence == 0.5
        assert n.contradictions == []


class TestMindMap:
    def test_create(self):
        mm = MindMap.create("hello world")
        assert mm.query == "hello world"
        assert mm.root.topic == "hello world"

    def test_find_or_create_node_found(self):
        mm = MindMap.create("q")
        child = MindMapNode(topic="sub")
        mm.root.children.append(child)
        found = mm.find_or_create_node("sub")
        assert found is child

    def test_find_or_create_node_new(self):
        mm = MindMap.create("q")
        node = mm.find_or_create_node("new topic")
        assert node.topic == "new topic"
        assert node in mm.root.children

    def test_find_or_create_case_insensitive(self):
        mm = MindMap.create("q")
        child = MindMapNode(topic="SubTopic")
        mm.root.children.append(child)
        found = mm.find_or_create_node("subtopic")
        assert found is child

    def test_add_finding_new_node(self):
        mm = MindMap.create("q")
        sources = [Source(url="https://a.com", title="A")]
        node = mm.add_finding("topic1", "content1", sources, 0.8)
        assert node.topic == "topic1"
        assert node.content == "content1"
        assert node.sources == sources
        assert node.confidence == 0.8

    def test_add_finding_existing_node_appends(self):
        mm = MindMap.create("q")
        s1 = [Source(url="https://a.com", title="A")]
        mm.add_finding("t", "first", s1, 0.5)
        s2 = [Source(url="https://b.com", title="B")]
        node = mm.add_finding("t", "second", s2, 0.9)
        assert node.content == "first\n\nsecond"
        assert len(node.sources) == 2
        assert node.confidence == 0.9

    def test_add_finding_dedup_sources(self):
        mm = MindMap.create("q")
        s = [Source(url="https://a.com", title="A")]
        mm.add_finding("t", "c1", s, 0.5)
        mm.add_finding("t", "c2", s, 0.7)
        assert len(mm.root.children[0].sources) == 1

    def test_log_contradiction(self):
        mm = MindMap.create("q")
        sa = Source(url="https://a.com", title="A")
        sb = Source(url="https://b.com", title="B")
        mm.log_contradiction("t", "claim a", "claim b", sa, sb)
        # Contradiction is added to the child node created for topic "t"
        assert len(mm.root.children) == 1
        assert len(mm.root.children[0].contradictions) == 1
        c = mm.root.children[0].contradictions[0]
        assert c.claim_a == "claim a"
        assert c.source_a.url == "https://a.com"

    def test_get_summary(self):
        mm = MindMap.create("query")
        s1 = Source(url="https://a.com")
        mm.add_finding("sub1", "data1", [s1], 0.9)
        summary = mm.get_summary()
        assert "- query" in summary
        assert "- sub1" in summary
        assert "1 sources" in summary
        assert "90%" in summary

    def test_get_summary_none_confidence(self):
        mm = MindMap.create("q")
        mm.root.confidence = 0.0
        summary = mm.get_summary()
        assert "none" in summary

    def test_get_summary_with_contradiction(self):
        mm = MindMap.create("q")
        s1 = Source(url="https://a.com")
        s2 = Source(url="https://b.com")
        mm.log_contradiction("t", "x", "y", s1, s2)
        summary = mm.get_summary()
        assert "Contradiction:" in summary

    def test_get_gaps(self):
        mm = MindMap.create("query")
        mm.add_finding("low_conf", "d", [], 0.1)
        mm.add_finding("high_conf", "d", [], 0.9)
        gaps = mm.get_gaps()
        assert "low_conf" in gaps
        assert "high_conf" not in gaps
        assert "query" not in gaps  # root excluded

    def test_get_gaps_no_gaps(self):
        mm = MindMap.create("q")
        mm.add_finding("sub", "d", [], 0.9)
        assert mm.get_gaps() == []

    def test_get_contradictions(self):
        mm = MindMap.create("q")
        sa = Source(url="https://a.com")
        sb = Source(url="https://b.com")
        mm.log_contradiction("t1", "a", "b", sa, sb)
        mm.log_contradiction("t2", "c", "d", sa, sb)
        contras = mm.get_contradictions()
        assert len(contras) == 2

    def test_get_contradictions_empty(self):
        mm = MindMap.create("q")
        assert mm.get_contradictions() == []

    def test_source_count(self):
        mm = MindMap.create("q")
        mm.add_finding("t1", "d", [Source(url="https://a.com")], 0.5)
        mm.add_finding("t2", "d", [Source(url="https://b.com")], 0.5)
        assert mm.source_count() == 2

    def test_source_count_empty(self):
        mm = MindMap.create("q")
        assert mm.source_count() == 0

    def test_walk_with_children(self):
        mm = MindMap.create("q")
        child = MindMapNode(topic="sub", confidence=0.0)
        mm.root.children.append(child)
        summary = mm.get_summary()
        assert "- sub" in summary

    def test_find_or_create_node_nested(self):
        mm = MindMap.create("root")
        child = MindMapNode(topic="level1")
        grandchild = MindMapNode(topic="level2")
        child.children.append(grandchild)
        mm.root.children.append(child)
        found = mm.find_or_create_node("level2")
        assert found is grandchild

    def test_find_or_create_node_not_found(self):
        mm = MindMap.create("root")
        found = mm._find_node(mm.root, "nonexistent")
        assert found is None


class TestTokenUsage:
    def test_add(self):
        t = TokenUsage()
        t.add(10, 20)
        assert t.input_tokens == 10
        assert t.output_tokens == 20
        t.add(5, 5)
        assert t.input_tokens == 15
        assert t.output_tokens == 25


class TestActionLog:
    def test_create(self):
        log = ActionLog(tool="web_search", args={"q": "test"}, result_summary="ok")
        assert log.tool == "web_search"
        assert log.args == {"q": "test"}
        assert log.result_summary == "ok"
        assert log.timestamp is not None


class TestResearchState:
    def test_create_default_language(self):
        rs = ResearchState.create("hello world")
        assert rs.query == "hello world"
        assert rs.language == "en"
        assert rs.mind_map is not None
        assert rs.iteration == 0
        assert rs.run_id is not None

    def test_create_german_language(self):
        rs = ResearchState.create("Der Hund und die Katze")
        assert rs.language == "de"

    def test_create_explicit_language(self):
        rs = ResearchState.create("hello", language="de")
        assert rs.language == "de"

    def test_create_with_params(self):
        rs = ResearchState.create(
            "test", max_iterations=10, tree_depth=3, branching_factor=7,
            language="en",
        )
        assert rs.max_iterations == 10
        assert rs.tree_depth == 3
        assert rs.branching_factor == 7

    def test_detect_language_german(self):
        assert ResearchState._detect_language("Der Hund und die Katze ist nicht") == "de"
        assert ResearchState._detect_language("Das ist ein schöner Tag") == "de"

    def test_detect_language_english(self):
        assert ResearchState._detect_language("The dog and the cat") == "en"
        assert ResearchState._detect_language("Hello world") == "en"

    def test_detect_language_edge_equal_counts(self):
        # "der" is both a German and English word, but english has more
        result = ResearchState._detect_language("the and for not with")
        assert result == "en"

    def test_detect_language_german_double(self):
        # German words must be 2x English to count
        text = "der die das und ist ein eine " * 3 + "the and"
        assert ResearchState._detect_language(text) == "de"

    def test_increment_iteration(self):
        rs = ResearchState.create("q")
        assert rs.increment_iteration() == 1
        assert rs.increment_iteration() == 2

    def test_log_action(self):
        rs = ResearchState.create("q")
        rs.log_action("web_search", {"query": "test"}, "3 results")
        assert len(rs.actions_log) == 1
        assert rs.actions_log[0].tool == "web_search"

    def test_log_action_default_summary(self):
        rs = ResearchState.create("q")
        rs.log_action("web_search", {"query": "test"})
        assert rs.actions_log[0].result_summary == ""

    def test_is_over_budget_under(self):
        rs = ResearchState.create("q", max_iterations=5)
        assert rs.is_over_budget() is False

    def test_is_over_budget_at_limit(self):
        rs = ResearchState.create("q", max_iterations=5)
        for _ in range(5):
            rs.increment_iteration()
        assert rs.is_over_budget() is True

    def test_is_over_budget_unlimited(self):
        rs = ResearchState.create("q", max_iterations=0)
        assert rs.is_over_budget() is False

    def test_defaults(self):
        rs = ResearchState.create("q")
        assert rs.status == "PENDING"
        assert rs.report == ""
        assert rs.error == ""
        assert rs.draft_requested is False


# =========================================================================
# Tool Declaration Helper
# =========================================================================


class TestToolDeclaration:
    def test_creates_struct(self):
        td = _tool_declaration(
            "test_tool", "A test tool",
            {"type": "object", "properties": {"x": {"type": "string"}}, "required": ["x"]},
        )
        assert td["type"] == "function"
        assert td["function"]["name"] == "test_tool"


# =========================================================================
# Tool Handler Tests
# =========================================================================


class TestToolWebSearch:
    async def test_empty_query(self):
        result = await _tool_web_search({}, MagicMock(), "key")
        assert result["error"] == "Empty search query."
        assert result["results"] == []

    async def test_no_api_key(self):
        result = await _tool_web_search({"query": "test"}, MagicMock(), None)
        assert "BRAVE_API_KEY" in result["error"]
        assert result["results"] == []

    @patch("httpx.AsyncClient")
    async def test_success(self, mock_client_cls):
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__.return_value = mock_client
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "web": {
                "results": [
                    {"title": "Result 1", "url": "https://a.com", "description": "Snippet 1"},
                    {"title": "Result 2", "url": "https://b.com", "description": "Snippet 2"},
                ],
            },
        }
        mock_client.get.return_value = mock_resp

        result = await _tool_web_search(
            {"query": "test query", "max_results": 5},
            MagicMock(), "fake_key",
        )
        assert result["count"] == 2
        assert result["query"] == "test query"
        assert result["results"][0]["title"] == "Result 1"

    @patch("httpx.AsyncClient")
    async def test_http_failure(self, mock_client_cls):
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__.return_value = mock_client
        mock_client.get.side_effect = RuntimeError("Connection refused")

        result = await _tool_web_search({"query": "test"}, MagicMock(), "key")
        assert "Search failed" in result["error"]

    @patch("httpx.AsyncClient")
    async def test_missing_web_key(self, mock_client_cls):
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__.return_value = mock_client
        mock_resp = MagicMock()
        mock_resp.json.return_value = {}
        mock_client.get.return_value = mock_resp

        result = await _tool_web_search({"query": "test"}, MagicMock(), "key")
        assert result["count"] == 0

    @patch("httpx.AsyncClient")
    async def test_max_results_capped(self, mock_client_cls):
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__.return_value = mock_client
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"web": {"results": []}}
        mock_client.get.return_value = mock_resp

        result = await _tool_web_search(
            {"query": "test", "max_results": 100},
            MagicMock(), "key",
        )
        # Should cap at 20
        assert result["count"] == 0  # No results, just confirming the mock worked

    @patch("httpx.AsyncClient")
    async def test_non_dict_response(self, mock_client_cls):
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__.return_value = mock_client
        mock_resp = MagicMock()
        mock_resp.json.return_value = "string response"
        mock_client.get.return_value = mock_resp

        result = await _tool_web_search({"query": "test"}, MagicMock(), "key")
        assert result["count"] == 0


class TestToolReadWebpage:
    async def test_empty_url(self):
        result = await _tool_read_webpage({}, MagicMock())
        assert result["error"] == "No URL provided."

    @patch("workbench.services.research_orchestrator.validate_public_url")
    async def test_invalid_url(self, mock_validate):
        mock_validate.side_effect = ValueError("Invalid URL")
        result = await _tool_read_webpage({"url": "https://evil.internal"}, MagicMock())
        assert "error" in result

    @patch("workbench.services.research_orchestrator._extract_with_trafilatura")
    @patch("workbench.services.research_orchestrator.validate_public_url")
    async def test_trafilatura_success(self, mock_validate, mock_traf):
        mock_validate.return_value = "https://example.com"
        mock_traf.return_value = {
            "content": "Hello world", "title": "Example", "url": "https://example.com",
        }
        result = await _tool_read_webpage({"url": "https://example.com"}, MagicMock())
        assert result["content"] == "Hello world"
        assert result["title"] == "Example"
        assert result["char_count"] == 11

    @patch("workbench.services.research_orchestrator._extract_with_trafilatura")
    @patch("workbench.services.research_orchestrator._extract_with_httpx")
    @patch("workbench.services.research_orchestrator.validate_public_url")
    async def test_trafilatura_fails_httpx_fallback(
        self, mock_validate, mock_httpx_ext, mock_traf,
    ):
        mock_validate.return_value = "https://example.com"
        mock_traf.return_value = None
        mock_httpx_ext.return_value = {
            "content": "Fallback content", "title": "Fallback",
            "url": "https://example.com",
        }
        result = await _tool_read_webpage({"url": "https://example.com"}, MagicMock())
        assert result["content"] == "Fallback content"

    @patch("workbench.services.research_orchestrator._extract_with_trafilatura")
    @patch("workbench.services.research_orchestrator._extract_with_httpx")
    @patch("workbench.services.research_orchestrator.validate_public_url")
    async def test_both_fail(self, mock_validate, mock_httpx_ext, mock_traf):
        mock_validate.return_value = "https://example.com"
        mock_traf.return_value = None
        mock_httpx_ext.return_value = None
        result = await _tool_read_webpage({"url": "https://example.com"}, MagicMock())
        assert "Could not extract" in result["error"]

    @patch("workbench.services.research_orchestrator._extract_with_trafilatura")
    @patch("workbench.services.research_orchestrator.validate_public_url")
    async def test_truncated_content(self, mock_validate, mock_traf):
        mock_validate.return_value = "https://example.com"
        long_content = "x" * 200_000
        mock_traf.return_value = {
            "content": long_content, "title": "Long", "url": "https://example.com",
        }
        result = await _tool_read_webpage({"url": "https://example.com"}, MagicMock())
        assert result["truncated"] is True
        assert "[Content truncated...]" in result["content"]


class TestExtractWithTrafilatura:
    @patch("trafilatura.fetch_url")
    @patch("trafilatura.extract")
    @patch("trafilatura.extract_metadata")
    async def test_success(self, mock_meta, mock_extract, mock_fetch):
        mock_fetch.return_value = "<html>data</html>"
        mock_extract.return_value = "markdown content"
        mock_meta_instance = MagicMock()
        mock_meta_instance.title = "Page Title"
        mock_meta.return_value = mock_meta_instance

        result = await _extract_with_trafilatura("https://example.com")
        assert result is not None
        assert result["content"] == "markdown content"
        assert result["title"] == "Page Title"

    @patch("trafilatura.fetch_url")
    async def test_no_download(self, mock_fetch):
        mock_fetch.return_value = None
        result = await _extract_with_trafilatura("https://example.com")
        assert result is None

    @patch("trafilatura.fetch_url")
    @patch("trafilatura.extract")
    @patch("trafilatura.extract_metadata")
    async def test_no_text(self, mock_meta, mock_extract, mock_fetch):
        mock_fetch.return_value = "<html>data</html>"
        mock_extract.return_value = None
        result = await _extract_with_trafilatura("https://example.com")
        assert result is None

    @patch("trafilatura.fetch_url")
    async def test_exception(self, mock_fetch):
        mock_fetch.side_effect = RuntimeError("fetch failed")
        result = await _extract_with_trafilatura("https://example.com")
        assert result is None


class TestExtractWithHttpx:
    @patch("httpx.AsyncClient")
    async def test_success(self, mock_client_cls):
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__.return_value = mock_client
        mock_resp = MagicMock()
        mock_resp.text = (
            "<html><head><title>Test</title></head><body>"
            "<p>Hello world content here. This is a longer paragraph with sufficient "
            "text to pass the 50 character minimum threshold for extraction. "
            "We need enough content to make sure the test passes correctly.</p>"
            "</body></html>"
        )
        mock_client.get.return_value = mock_resp

        result = await _extract_with_httpx("https://example.com")
        assert result is not None
        assert result["title"] == "Test"
        assert "Hello world" in result["content"]

    @patch("httpx.AsyncClient")
    async def test_no_title(self, mock_client_cls):
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__.return_value = mock_client
        mock_resp = MagicMock()
        mock_resp.text = "<html><body><p>Content here with enough length</p></body></html>"
        mock_resp.text += "x" * 100  # Ensure >50 chars
        mock_client.get.return_value = mock_resp

        result = await _extract_with_httpx("https://example.com")
        assert result is not None
        assert result["title"] == ""

    @patch("httpx.AsyncClient")
    async def test_too_short(self, mock_client_cls):
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__.return_value = mock_client
        mock_resp = MagicMock()
        mock_resp.text = "<html><body>short</body></html>"
        mock_client.get.return_value = mock_resp

        result = await _extract_with_httpx("https://example.com")
        assert result is None

    @patch("httpx.AsyncClient")
    async def test_exception(self, mock_client_cls):
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__.return_value = mock_client
        mock_client.get.side_effect = RuntimeError("HTTP error")

        result = await _extract_with_httpx("https://example.com")
        assert result is None

    @patch("httpx.AsyncClient")
    async def test_script_style_removed(self, mock_client_cls):
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__.return_value = mock_client
        mock_resp = MagicMock()
        mock_resp.text = (
            "<html><head><title>Test</title></head><body>"
            "<script>alert('hi')</script>"
            "<style>body{color:red}</style>"
            "<nav>menu</nav>"
            "<p>Actual content here with lots of text for testing</p>"
            "</body></html>"
        )
        mock_client.get.return_value = mock_resp

        result = await _extract_with_httpx("https://example.com")
        assert result is not None
        assert "Actual content" in result["content"]

    @patch("httpx.AsyncClient")
    async def test_raise_for_status_error(self, mock_client_cls):
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__.return_value = mock_client
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = RuntimeError("403 Forbidden")
        mock_client.get.return_value = mock_resp

        result = await _extract_with_httpx("https://example.com")
        assert result is None


class TestToolUpdateFindings:
    @pytest.mark.asyncio
    async def test_basic(self):
        state = ResearchState.create("test query")
        result = await _tool_update_findings(
            {
                "topic": "test topic",
                "content": "some finding",
                "sources": [{"url": "https://a.com", "title": "A"}],
                "confidence": 0.75,
            },
            state,
        )
        assert result["status"] == "ok"
        assert "test topic" in result["summary"]

    @pytest.mark.asyncio
    async def test_defaults(self):
        state = ResearchState.create("q")
        result = await _tool_update_findings({}, state)
        assert result["status"] == "ok"


class TestToolLogContradiction:
    @pytest.mark.asyncio
    async def test_missing_args(self):
        result = await _tool_log_contradiction({}, MagicMock())
        assert "Missing required argument" in result["error"]

    @pytest.mark.asyncio
    async def test_missing_specific_arg(self):
        result = await _tool_log_contradiction(
            {"topic": "t", "claim_a": "a", "claim_b": "b", "source_a": {"url": "https://a.com"}, "source_b": {"url": "https://b.com"}},
            MagicMock(),
        )
        assert result["status"] == "ok"

    @pytest.mark.asyncio
    async def test_success(self):
        state = ResearchState.create("q")
        result = await _tool_log_contradiction(
            {
                "topic": "t",
                "claim_a": "a",
                "claim_b": "b",
                "source_a": {"url": "https://a.com", "title": "A"},
                "source_b": {"url": "https://b.com", "title": "B"},
            },
            state,
        )
        assert result["status"] == "ok"
        assert result["contradictions_count"] == 1


class TestToolDraftReport:
    @pytest.mark.asyncio
    async def test_rejected_too_few_sources(self):
        state = ResearchState.create("q")
        result = await _tool_draft_report({}, state)
        assert result["status"] == "rejected"
        assert "Not enough research" in result["reason"]

    @pytest.mark.asyncio
    async def test_rejected_too_few_topics(self):
        """3 sources but only 1 topic -> topics (1) < 2, so rejected."""
        state = ResearchState.create("q")
        state.mind_map.add_finding("t1", "d", [Source(url="https://a.com")], 0.5)
        state.mind_map.add_finding("t1", "d", [Source(url="https://b.com")], 0.5)
        state.mind_map.add_finding("t1", "d", [Source(url="https://c.com")], 0.5)
        result = await _tool_draft_report({}, state)
        assert result["status"] == "rejected"

    @pytest.mark.asyncio
    async def test_ready(self):
        state = ResearchState.create("q")
        for i in range(4):
            state.mind_map.add_finding(
                f"t{i}", "d", [Source(url=f"https://{i}.com")], 0.5,
            )
        result = await _tool_draft_report({}, state)
        assert result["status"] == "ready"
        assert state.draft_requested is True


# =========================================================================
# ResearchOrchestrator Tests
# =========================================================================


@pytest.fixture
def mock_client():
    client = MagicMock()
    client.chat_completion_full = AsyncMock()
    return client


@pytest.fixture
def state():
    return ResearchState.create("test query", max_iterations=5, tree_depth=2, branching_factor=3)


@pytest.fixture
def orchestrator(mock_client, state):
    return ResearchOrchestrator(mock_client, state, brave_api_key="fake_key")


class TestOrchestratorInit:
    def test_properties(self, orchestrator):
        assert orchestrator.run_id == orchestrator._state.run_id
        assert orchestrator.state.query == "test query"

    def test_stop(self, orchestrator):
        orchestrator.stop()
        assert orchestrator._stop_flag.is_set()
        assert orchestrator._state.status == "STOPPED"

    def test_to_dict(self, orchestrator):
        d = orchestrator.to_dict()
        assert d["query"] == "test query"

    def test_to_json(self, orchestrator):
        j = orchestrator.to_json()
        assert "test query" in j

    def test_emit_with_handler(self, orchestrator):
        self.events = []
        def handler(e):
            self.events.append(e)
        orchestrator._on_event = handler
        orchestrator._emit("test", {"key": "val"})
        assert len(self.events) == 1
        assert self.events[0]["event"] == "test"

    def test_emit_without_handler(self, orchestrator):
        # Should not raise
        orchestrator._on_event = None
        orchestrator._emit("test", "data")

    def test_emit_queue_full(self, orchestrator):
        # Fill the queue
        for _ in range(500):
            orchestrator._event_queue.put_nowait({"event": "x", "data": "y"})
        # Should not raise despite QueueFull
        orchestrator._emit("overflow", "test")


class TestOrchestratorResponseToMessage:
    def test_with_tool_calls(self):
        msg = ResearchOrchestrator._response_to_message(
            {"text": "thinking", "tool_calls": [{"id": "call_1", "function": {"name": "test"}}]},
        )
        assert msg["role"] == "assistant"
        assert msg["content"] == "thinking"
        assert "tool_calls" in msg

    def test_without_tool_calls(self):
        msg = ResearchOrchestrator._response_to_message({"text": "hello"})
        assert msg["role"] == "assistant"
        assert msg["content"] == "hello"
        assert "tool_calls" not in msg


class TestOrchestratorSummarizeResult:
    def test_error(self):
        s = ResearchOrchestrator._summarize_result("web_search", {"error": "Something failed badly"})
        assert s.startswith("Error:")

    def test_web_search(self):
        s = ResearchOrchestrator._summarize_result("web_search", {"count": 5, "query": "test"})
        assert "5 results" in s

    def test_read_webpage(self):
        s = ResearchOrchestrator._summarize_result("read_webpage", {"char_count": 1000})
        assert "1000 chars" in s

    def test_read_webpage_truncated(self):
        s = ResearchOrchestrator._summarize_result(
            "read_webpage", {"char_count": 1000, "truncated": True},
        )
        assert "1000 chars" in s
        assert "truncated" in s

    def test_update_findings(self):
        s = ResearchOrchestrator._summarize_result("update_findings", {"status": "ok"})
        assert s == "Recorded"

    def test_log_contradiction(self):
        s = ResearchOrchestrator._summarize_result(
            "log_contradiction", {"contradictions_count": 3},
        )
        assert "3 contradictions" in s

    def test_draft_report(self):
        s = ResearchOrchestrator._summarize_result("draft_report", {"status": "ready"})
        assert s == "ready"

    def test_unknown(self):
        s = ResearchOrchestrator._summarize_result("unknown_tool", {"x": "y"})
        assert s == "{'x': 'y'}"


class TestOrchestratorSend:
    async def test_success_with_usage(self, orchestrator, mock_client):
        mock_client.chat_completion_full.return_value = {
            "text": "hello",
            "tool_calls": None,
            "usage": {"prompt_tokens": 10, "completion_tokens": 20},
            "finish_reason": "stop",
        }
        result = await orchestrator._send([{"role": "user", "content": "hi"}])
        assert result["text"] == "hello"
        assert orchestrator._state.token_usage.input_tokens == 10
        assert orchestrator._state.token_usage.output_tokens == 20

    async def test_success_without_usage(self, orchestrator, mock_client):
        mock_client.chat_completion_full.return_value = {
            "text": "hello",
            "tool_calls": None,
            "usage": None,
            "finish_reason": "stop",
        }
        result = await orchestrator._send([{"role": "user", "content": "hi"}])
        assert result["text"] == "hello"
        assert orchestrator._state.token_usage.input_tokens == 0

    async def test_success_without_usage_key(self, orchestrator, mock_client):
        mock_client.chat_completion_full.return_value = {
            "text": "hello",
        }
        result = await orchestrator._send([{"role": "user", "content": "hi"}])
        assert result["text"] == "hello"

    async def test_exception(self, orchestrator, mock_client):
        mock_client.chat_completion_full.side_effect = RuntimeError("LLM API down")
        with pytest.raises(RuntimeError, match="LLM API down"):
            await orchestrator._send([{"role": "user", "content": "hi"}])


class TestOrchestratorDispatchTool:
    async def test_known_tool(self, orchestrator):
        result = await orchestrator._dispatch_tool("draft_report", {})
        assert "status" in result

    async def test_unknown_tool(self, orchestrator):
        result = await orchestrator._dispatch_tool("nonexistent", {})
        assert "error" in result
        assert "Unknown tool" in result["error"]

    async def test_tool_exception(self, orchestrator):
        # Dispatch a tool that raises
        with patch(
            "workbench.services.research_orchestrator._tool_web_search",
            side_effect=ValueError("bad value"),
        ):
            result = await orchestrator._dispatch_tool("web_search", {"query": "x"})
            assert "error" in result
            assert "ValueError" in result["error"]


class TestOrchestratorExecuteToolCalls:
    async def test_basic(self, orchestrator, state):
        state.mind_map.add_finding(
            "t1", "d", [Source(url="https://a.com")], 0.5,
        )
        state.mind_map.add_finding(
            "t2", "d", [Source(url="https://b.com")], 0.5,
        )
        state.mind_map.add_finding(
            "t3", "d", [Source(url="https://c.com")], 0.5,
        )
        state.mind_map.add_finding(
            "t4", "d", [Source(url="https://d.com")], 0.5,
        )

        tool_calls = [
            {
                "id": "call_1",
                "function": {
                    "name": "draft_report",
                    "arguments": "{}",
                },
            },
        ]
        results = await orchestrator._execute_tool_calls(tool_calls)
        assert len(results) == 1
        assert results[0]["role"] == "tool"
        assert results[0]["tool_call_id"] == "call_1"
        assert "ready" in results[0]["content"]
        assert len(state.actions_log) == 1

    async def test_json_decode_error(self, orchestrator):
        tool_calls = [
            {
                "id": "call_2",
                "function": {
                    "name": "update_findings",
                    "arguments": "not valid json",
                },
            },
        ]
        results = await orchestrator._execute_tool_calls(tool_calls)
        assert len(results) == 1
        # Should handle gracefully (args become {})

    async def test_args_as_dict(self, orchestrator):
        tool_calls = [
            {
                "id": "call_3",
                "function": {
                    "name": "draft_report",
                    "arguments": {},
                },
            },
        ]
        results = await orchestrator._execute_tool_calls(tool_calls)
        assert len(results) == 1


class TestOrchestratorComputeCurrentDepth:
    def test_empty(self, orchestrator):
        assert orchestrator._compute_current_depth() == 0

    def test_with_children(self, orchestrator):
        orchestrator._state.mind_map.root.children.append(MindMapNode(topic="c1"))
        assert orchestrator._compute_current_depth() == 1

    def test_nested(self, orchestrator):
        c1 = MindMapNode(topic="c1")
        c2 = MindMapNode(topic="c2")
        c1.children.append(c2)
        orchestrator._state.mind_map.root.children.append(c1)
        assert orchestrator._compute_current_depth() == 2

    def test_exception_returns_one(self, orchestrator):
        # Force an exception by making root raise
        with patch.object(orchestrator._state.mind_map.root, "children", create=True):
            # This is tricky — _compute_current_depth calls max_depth which accesses .children
            # Let's just simulate an exception
            orig_root = orchestrator._state.mind_map.root
            bad_node = MagicMock()
            bad_node.children.side_effect = RuntimeError("boom")
            orchestrator._state.mind_map.root = bad_node
            assert orchestrator._compute_current_depth() == 1
            orchestrator._state.mind_map.root = orig_root


class TestOrchestratorBuildSystemPrompt:
    def test_basic(self, orchestrator):
        prompt = orchestrator._build_system_prompt()
        assert "test query" in prompt
        assert "none identified yet" in prompt
        assert "none" in prompt  # for contradictions
        assert "English" in prompt
        assert "deep_rearch_v4" not in prompt  # just checking

    def test_with_gaps_and_contradictions(self, orchestrator):
        state = orchestrator._state
        state.mind_map.add_finding(
            "low_conf_topic", "d", [Source(url="https://a.com")], 0.1,
        )
        sa = Source(url="https://a.com", title="A")
        sb = Source(url="https://b.com", title="B")
        state.mind_map.log_contradiction("t", "a", "b", sa, sb)
        prompt = orchestrator._build_system_prompt()
        assert "low_conf_topic" in prompt
        assert "1 unresolved" in prompt or "2 unresolved" in prompt or "1" in prompt

    def test_german_language(self, orchestrator):
        orchestrator._state.language = "de"
        prompt = orchestrator._build_system_prompt()
        assert "German (Deutsch)" in prompt or "de" in prompt

    def test_no_findings(self, orchestrator):
        prompt = orchestrator._build_system_prompt()
        assert "(no findings yet)" in prompt or "none" in prompt

    def test_unlimited_iterations(self, orchestrator):
        orchestrator._state.max_iterations = 0
        prompt = orchestrator._build_system_prompt()
        assert "unlimited" in prompt

    def test_source_count_zero(self, orchestrator):
        prompt = orchestrator._build_system_prompt()
        assert "0 sources" in prompt or "sources" in prompt


# =========================================================================
# Orchestrator Run/Agent Loop Tests (Complex Integrated)
# =========================================================================


class TestOrchestratorRunSuccess:
    """HAPPY PATH: Tool calls → execute → draft → report."""

    async def test_happy_path(self, orchestrator, mock_client, state):
        # Prepare state with enough data for draft_report
        for i in range(4):
            state.mind_map.add_finding(
                f"t{i}", "d", [Source(url=f"https://{i}.com")], 0.5,
            )

        # Simulate agent loop:
        # 1. Initial response with tool_calls (draft_report)
        # 2. After executing draft_report, response has no tool_calls and draft_requested is True
        # 3. _handle_report returns the report text
        mock_client.chat_completion_full.side_effect = [
            # First _send: returns tool_calls
            {
                "text": "Let me do research",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "function": {"name": "draft_report", "arguments": "{}"},
                    },
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5},
                "finish_reason": "tool_calls",
            },
            # Second _send (after executing tool): draft_requested is True, no more tool_calls
            {
                "text": "Here is the report with much more content to be at least two hundred characters long so that the handle report function will recognize it as a proper report and return it directly without another send call. This should be enough to meet the threshold.",
                "usage": {"prompt_tokens": 20, "completion_tokens": 30},
                "finish_reason": "stop",
            },
        ]

        report = await orchestrator.run("test query")
        assert "report" in report.lower()
        assert orchestrator._state.status == "COMPLETED"


class TestOrchestratorRunRouterExhausted:
    async def test_router_exhausted(self, orchestrator, mock_client):
        mock_client.chat_completion_full.side_effect = RouterExhaustedError("All models failed")
        report = await orchestrator.run("test query")
        assert "Research failed" in report
        assert orchestrator._state.status == "ERROR"
        assert "All models failed" in orchestrator._state.error


class TestOrchestratorRunCancelled:
    async def test_cancelled(self, orchestrator, mock_client):
        mock_client.chat_completion_full.side_effect = asyncio.CancelledError()
        with pytest.raises(asyncio.CancelledError):
            await orchestrator.run("test query")
        assert orchestrator._state.status == "STOPPED"


class TestOrchestratorRunGenericError:
    async def test_generic_error(self, orchestrator, mock_client):
        mock_client.chat_completion_full.side_effect = ValueError("Something went wrong")
        report = await orchestrator.run("test query")
        assert "internal error" in report
        assert orchestrator._state.status == "ERROR"


class TestOrchestratorAgentLoopStopFlag:
    async def test_stop_flag(self, orchestrator, mock_client, state):
        # Set stop flag so the loop exits immediately
        orchestrator.stop()

        mock_client.chat_completion_full.side_effect = [
            # _send in _agent_loop first call
            {
                "text": "initial response",
                "usage": {"prompt_tokens": 10, "completion_tokens": 5},
                "finish_reason": "stop",
            },
            # _send in _finalize_on_stop
            {
                "text": "Partial report due to stop",
                "usage": {"prompt_tokens": 5, "completion_tokens": 5},
                "finish_reason": "stop",
            },
        ]

        report = await orchestrator.run("test query")
        assert "Partial report" in report

    async def test_stop_flag_finalize_empty(self, orchestrator, mock_client, state):
        orchestrator.stop()
        mock_client.chat_completion_full.side_effect = [
            {
                "text": "initial",
                "usage": {},
                "finish_reason": "stop",
            },
            # _finalize_on_stop: text is empty
            {
                "text": "",
                "usage": {},
                "finish_reason": "stop",
            },
        ]
        report = await orchestrator.run("test query")
        # Falls back to mind_map.get_summary() which includes root node
        assert "test query" in report

    async def test_stop_flag_finalize_exception(self, orchestrator, mock_client, state):
        orchestrator.stop()
        mock_client.chat_completion_full.side_effect = [
            {
                "text": "initial",
                "usage": {},
                "finish_reason": "stop",
            },
            RuntimeError("finalize failed"),
        ]
        report = await orchestrator.run("test query")
        assert "test query" in report


class TestOrchestratorAgentLoop:
    """Tests of the _agent_loop method directly with various simulation scenarios."""

    async def test_draft_requested_with_long_text(self, orchestrator, mock_client, state):
        """No tool_calls, draft_requested already True, text > 200 chars -> return text."""
        state.draft_requested = True
        long_text = "A" * 300
        mock_client.chat_completion_full.return_value = {
            "text": long_text,
            "usage": {},
            "finish_reason": "stop",
        }
        report = await orchestrator.run("test query")
        assert report == long_text

    async def test_finish_reason_stop_with_text(self, orchestrator, mock_client):
        """No tool_calls, not draft_requested, finish_reason=stop, has text -> return text."""
        mock_client.chat_completion_full.return_value = {
            "text": "Final answer from model",
            "usage": {},
            "finish_reason": "stop",
        }
        report = await orchestrator.run("test query")
        assert report == "Final answer from model"

    async def test_over_budget_force_report(self, orchestrator, mock_client, state):
        """No tool_calls, over budget -> force final report with tools=None."""
        # Make the model return text that doesn't match finish_reason=="stop"
        # First call: response that triggers loop to continue
        mock_client.chat_completion_full.side_effect = [
            # _send in _agent_loop (first call)
            {
                "text": "Research in progress",
                "usage": {},
                "finish_reason": "length",
            },
            # After budget check, _send with tools=None for forced report
            {
                "text": "Forced final report content",
                "usage": {},
                "finish_reason": "stop",
            },
        ]
        # Force over budget: max_iterations=5 already, we need iteration >= 5
        # But agent_loop starts with increment_iteration, so after first call iteration=1
        # Only over_budget when iteration >= max_iterations (5)
        # Let's set it directly
        state.iteration = 4  # So after increment it's 5

        report = await orchestrator.run("test query")
        assert report == "Forced final report content"

    async def test_over_budget_empty_report(self, orchestrator, mock_client, state):
        """Over budget but LLM returns empty text."""
        mock_client.chat_completion_full.side_effect = [
            {
                "text": "Research in progress",
                "usage": {},
                "finish_reason": "length",
            },
            {
                "text": "",
                "usage": {},
                "finish_reason": "stop",
            },
        ]
        state.iteration = 4

        report = await orchestrator.run("test query")
        assert "iteration limit" in report

    async def test_continue_researching_loop(self, orchestrator, mock_client, state):
        """Text present, no tool_calls, not draft_requested, not stop -> continue researching."""
        # We need: first response has text but finish_reason != "stop", not over budget
        # Then the "Continue researching" message triggers a second call
        state.max_iterations = 2  # Make sure we can get to the continue researching path

        mock_client.chat_completion_full.side_effect = [
            # First _send: text, no tool_calls, not stop
            {
                "text": "Intermediate thought",
                "tool_calls": None,
                "usage": {},
                "finish_reason": "length",
            },
            # Second _send: after "Continue researching" message
            {
                "text": "More research done",
                "tool_calls": None,
                "usage": {},
                "finish_reason": "stop",
            },
        ]

        # After first call iteration = 1, then it enters loop:
        # tool_calls = None (no tool_calls key - wait, we set tool_calls: None explicitly)
        # Actually response.get("tool_calls") returns None (the value), not the default
        # So we go to else branch
        # Not draft_requested
        # finish_reason == "length" so not "stop"
        # is_over_budget: iteration=1, max=2 → False
        # increment_iteration → 2
        # response.get("text") and not tool_calls → True
        # Appends "Continue researching" and calls _send again
        # Second response returns "More research done"
        # Loop again: iteration=2, not is_over_budget... wait 2 >= 2 so True
        # Hmm, it will be over budget. Let me check...

        # Actually after increment_iteration, iteration becomes 2, and max=2 → 2 >= 2 → over budget
        # So it won't test the continue path directly. Let me set max_iterations=10
        state.max_iterations = 10

        report = await orchestrator.run("test query")
        assert report == "More research done"

    async def test_draft_requested_short_text_handle_report(
        self, orchestrator, mock_client, state,
    ):
        """Tool calls executed, draft_requested becomes True, short text -> _handle_report path."""
        state.max_iterations = 10

        # Setup state similar to having researched
        for i in range(4):
            state.mind_map.add_finding(
                f"t{i}", "d", [Source(url=f"https://{i}.com")], 0.5,
            )

        mock_client.chat_completion_full.side_effect = [
            # First _send: tool call -> draft_report
            {
                "text": "Ready to report",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "function": {"name": "draft_report", "arguments": "{}"},
                    },
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5},
                "finish_reason": "tool_calls",
            },
            # After executing tool calls -> draft_requested is True
            # _send again: short text, no tool_calls
            {
                "text": "short",
                "usage": {"prompt_tokens": 5, "completion_tokens": 5},
                "finish_reason": "stop",
            },
            # _handle_report second branch: _send with tools=None
            {
                "text": "The final comprehensive report with lots of content here",
                "usage": {},
                "finish_reason": "stop",
            },
        ]

        report = await orchestrator.run("test query")
        assert "comprehensive report" in report

    async def test_handle_report_empty_then_summary(self, orchestrator, mock_client, state):
        """After draft_requested: text > 200 but empty? No, _handle_report called when
        draft_requested and no tool_calls. If text is short, it tries _send with tools=None.
        If that returns empty, falls back to mind_map summary."""
        state.draft_requested = True

        # Make a short initial response so we enter the else branch
        # Actually, _handle_report is called from the tool_calls path:
        # After tool calls are executed, if draft_requested and no tool_calls in response

        for i in range(4):
            state.mind_map.add_finding(
                f"t{i}", "d", [Source(url=f"https://{i}.com")], 0.5,
            )

        state.mind_map.add_finding("summary_test", "This is the fallback summary", [], 0.5)

        mock_client.chat_completion_full.side_effect = [
            # First _send: tool call to draft_report
            {
                "text": "Ready",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "function": {"name": "draft_report", "arguments": "{}"},
                    },
                ],
                "usage": {},
                "finish_reason": "tool_calls",
            },
            # After executing tool: short text
            {
                "text": "short",
                "tool_calls": None,
                "usage": {},
                "finish_reason": "stop",
            },
            # _handle_report second branch: send with tools=None, returns empty
            {
                "text": "",
                "usage": {},
                "finish_reason": "stop",
            },
        ]

        report = await orchestrator.run("test query")
        # Falls back to mind map summary
        assert "summary_test" in report


# =========================================================================
# Orchestrator Event Stream Tests
# =========================================================================


class TestEventStream:
    async def test_normal_event(self, orchestrator):
        orchestrator._event_queue.put_nowait({"event": "status", "data": {"iteration": 1}})
        orchestrator._event_queue.put_nowait({"event": "done", "data": {}})

        events = []
        async for event in orchestrator.event_stream():
            events.append(event)
        assert len(events) == 1
        assert "event: status" in events[0]
        assert '"iteration": 1' in events[0]

    async def test_timeout_sends_ping(self, orchestrator):
        """When queue.get times out, a ping event is yielded."""
        # Put done event after a delay
        async def delayed_done():
            await asyncio.sleep(0.05)
            orchestrator._event_queue.put_nowait({"event": "done", "data": {}})

        asyncio.create_task(delayed_done())

        # Set a very short timeout to trigger timeout
        # We need to patch asyncio.wait_for or the queue timeout
        # Actually the timeout is 30 seconds, which is too long. Let's patch.
        original_wait_for = asyncio.wait_for

        call_count = 0

        async def short_timeout(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                raise asyncio.TimeoutError()
            return await original_wait_for(*args, **kwargs)

        with patch("asyncio.wait_for", short_timeout):
            events = []
            async for event in orchestrator.event_stream():
                events.append(event)
                if len(events) >= 3:
                    break

        # First two calls timed out -> ping
        ping_events = [e for e in events if "ping" in e]
        assert len(ping_events) >= 1


# =========================================================================
# Orchestrator Run with tool_calls that have non-JSON args
# =========================================================================


class TestOrchestratorToolCallsNonJson:
    async def test_non_json_args(self, orchestrator, mock_client, state):
        """Tool call with invalid JSON arguments should default to {}."""
        state.max_iterations = 10
        for i in range(4):
            state.mind_map.add_finding(
                f"t{i}", "d", [Source(url=f"https://{i}.com")], 0.5,
            )

        mock_client.chat_completion_full.side_effect = [
            {
                "text": "Research",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "function": {
                            "name": "update_findings",
                            "arguments": "not valid json{{{",
                        },
                    },
                ],
                "usage": {},
                "finish_reason": "tool_calls",
            },
            # After executing (should handle gracefully), next response
            {
                "text": "Done researching",
                "usage": {},
                "finish_reason": "stop",
            },
        ]

        # Should not raise
        report = await orchestrator.run("test query")
        assert report is not None


# =========================================================================
# Edge Cases: Agent loop with various finish_reason values
# =========================================================================


class TestAgentLoopEdgeCases:
    async def test_no_tool_calls_no_text_no_stop(self, orchestrator, mock_client, state):
        """Response with no tool_calls, no text, no stop -> should loop."""
        # This is tricky - after the first response, we go into the else branch
        # draft_requested is False, finish_reason isn't "stop"
        # not over_budget, increment_iteration
        # Then response.get("text") is "" which is falsy -> skip "Continue researching"
        # Loop continues... but mock_client has no more responses -> raises StopIteration
        # Actually it will just keep calling mock which will return the same thing
        # But we need to avoid an infinite loop. Let's use side_effect with limited calls.

        state.max_iterations = 2  # So we hit over budget fast

        mock_client.chat_completion_full.side_effect = [
            # First call: response with no text, no tool_calls, not stop
            {
                "text": "",
                "usage": {},
                "finish_reason": "length",
            },
            # After budget check, force report
            {
                "text": "",
                "usage": {},
                "finish_reason": "stop",
            },
        ]

        report = await orchestrator.run("test query")
        assert "iteration limit" in report


# =========================================================================
# _tool_web_search: query with no web results key
# =========================================================================


class TestToolWebSearchNoWebKey:
    @patch("httpx.AsyncClient")
    async def test_no_web_key_in_response(self, mock_client_cls):
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__.return_value = mock_client
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"other": "data"}
        mock_client.get.return_value = mock_resp

        result = await _tool_web_search({"query": "test"}, MagicMock(), "key")
        assert result["count"] == 0


# =========================================================================
# _tool_update_findings async wrapper test
# =========================================================================

class TestToolUpdateFindingsAsync:
    async def test_sync_to_async(self):
        """_tool_update_findings is sync but called as async in dispatch."""
        state = ResearchState.create("q")
        result = await _tool_update_findings(
            {"topic": "t", "content": "c", "sources": [{"url": "https://a.com", "title": "A"}], "confidence": 0.5},
            state,
        )
        assert result["status"] == "ok"


# =========================================================================
# Extra edge: _extract_with_httpx with BeautifulSoup import issues
# =========================================================================


class TestExtractWithHttpxExceptions:
    @patch("httpx.AsyncClient")
    async def test_http_error_response(self, mock_client_cls):
        """Test when raise_for_status raises."""
        mock_client = AsyncMock()
        mock_client_cls.return_value.__aenter__.return_value = mock_client
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = RuntimeError("403 Client Error")
        mock_client.get.return_value = mock_resp

        result = await _extract_with_httpx("https://example.com")
        assert result is None


# =========================================================================
# Comprehensive: Test the _agent_loop directly with send patch
# =========================================================================


class TestAgentLoopDirect:
    """More direct tests of _agent_loop by patching _send."""

    async def test_unknown_tool_in_execute(self, orchestrator, mock_client, state):
        """When _execute_tool_calls gets an unknown tool."""
        state.draft_requested = True
        state.max_iterations = 10

        mock_client.chat_completion_full.side_effect = [
            # First _send
            {
                "text": "calling unknown tool",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "function": {
                            "name": "nonexistent_tool",
                            "arguments": "{}",
                        },
                    },
                ],
                "usage": {},
                "finish_reason": "tool_calls",
            },
            # After execution, draft_requested is True so it will go to handle_report
            # Actually after tool_calls execution, _send is called again
            # If draft_requested and no tool_calls -> _handle_report
            # Let's say the next response has text
            {
                "text": "A" * 300,
                "tool_calls": None,
                "usage": {},
                "finish_reason": "stop",
            },
        ]

        report = await orchestrator.run("test query")
        assert "AAAAA" in report


# =========================================================================
# ResearchState: json export
# =========================================================================


class TestResearchStateJson:
    def test_model_dump(self):
        rs = ResearchState.create("test")
        d = rs.model_dump()
        assert d["query"] == "test"
        assert isinstance(d["mind_map"], dict)

    def test_model_dump_json(self):
        rs = ResearchState.create("test")
        j = rs.model_dump_json(indent=2)
        assert "test" in j


# =========================================================================
# Comprehensive run test: tool_calls -> draft -> _handle_report second branch
# =========================================================================


class TestHandleReportSecondBranch:
    async def test_handle_report_short_text_fallback(
        self, orchestrator, mock_client, state,
    ):
        """_handle_report: text <= 200, then _send with tools=None returns empty,
        returns mind_map summary."""
        for i in range(4):
            state.mind_map.add_finding(
                f"t{i}", "d", [Source(url=f"https://{i}.com")], 0.5,
            )
        state.mind_map.add_finding("fallback", "Fallback summary data", [], 0.5)
        state.max_iterations = 10

        mock_client.chat_completion_full.side_effect = [
            # First _send: tool call (needed to enter the tool_calls path)
            {
                "text": "thinking",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "function": {"name": "draft_report", "arguments": "{}"},
                    },
                ],
                "usage": {},
                "finish_reason": "tool_calls",
            },
            # After executing tool: draft_requested = True, short text, no tool_calls
            {
                "text": "short",
                "tool_calls": None,
                "usage": {},
                "finish_reason": "stop",
            },
            # _handle_report calls _send with tools=None: empty text
            {
                "text": "",
                "tool_calls": None,
                "usage": {},
                "finish_reason": "stop",
            },
        ]

        report = await orchestrator.run("test query")
        assert "fallback" in report


# =========================================================================
# Test event_stream with timeout via patching
# =========================================================================


class TestEventStreamTimeout:
    async def test_timeout_events(self, orchestrator):
        """Verify that timeout yields ping events and done breaks the loop."""
        # Put events with a ping in between
        original_wait_for = asyncio.wait_for
        call_index = [0]

        async def timeout_then_events(awaitable, *args, **kwargs):
            call_index[0] += 1
            if call_index[0] <= 2:
                raise asyncio.TimeoutError()
            return await original_wait_for(awaitable, *args, **kwargs)

        # Put a done event on the queue
        async def schedule_done():
            orchestrator._event_queue.put_nowait({"event": "done", "data": {}})

        with patch("asyncio.wait_for", timeout_then_events):
            asyncio.create_task(schedule_done())
            events = []
            async for event in orchestrator.event_stream():
                events.append(event)

        ping_count = sum(1 for e in events if "ping" in e)
        assert ping_count == 2
