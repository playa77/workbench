"""Research Orchestrator — autonomous deep research agent with function calling.

Adapted from PResearch/orchestrator.py. Runs an autonomous agent loop:
send (with tools) -> process function calls -> handle results -> iterate.
Emits SSE events for real-time progress tracking via an asyncio.Queue.
"""

from __future__ import annotations

import asyncio
import json as _json
import logging
import time
import uuid
from collections.abc import Callable
from contextlib import suppress
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from workbench.shared.errors import RouterExhaustedError
from workbench.shared.llm.router import OpenRouterClient
from workbench.shared.network import validate_public_url

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------


class Source(BaseModel):
    url: str
    title: str = ""
    snippet: str = ""


class Contradiction(BaseModel):
    topic: str
    claim_a: str
    claim_b: str
    source_a: Source
    source_b: Source


class MindMapNode(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:8])
    topic: str
    content: str = ""
    sources: list[Source] = Field(default_factory=list)
    confidence: float = 0.0
    children: list[MindMapNode] = Field(default_factory=list)
    contradictions: list[Contradiction] = Field(default_factory=list)


class MindMap(BaseModel):
    root: MindMapNode
    query: str

    @classmethod
    def create(cls, query: str) -> MindMap:
        return cls(root=MindMapNode(topic=query), query=query)

    def find_or_create_node(self, topic: str) -> MindMapNode:
        found = self._find_node(self.root, topic)
        if found:
            return found
        node = MindMapNode(topic=topic)
        self.root.children.append(node)
        return node

    def _find_node(self, node: MindMapNode, topic: str) -> MindMapNode | None:
        if node.topic.lower() == topic.lower():
            return node
        for child in node.children:
            found = self._find_node(child, topic)
            if found:
                return found
        return None

    def add_finding(
        self, topic: str, content: str, sources: list[Source],
        confidence: float,
    ) -> MindMapNode:
        node = self.find_or_create_node(topic)
        node.content = f"{node.content}\n\n{content}".strip()
        existing_urls = {s.url for s in node.sources}
        for s in sources:
            if s.url not in existing_urls:
                node.sources.append(s)
                existing_urls.add(s.url)
        node.confidence = max(node.confidence, confidence)
        return node

    def log_contradiction(
        self, topic: str, claim_a: str, claim_b: str,
        source_a: Source, source_b: Source,
    ) -> None:
        node = self.find_or_create_node(topic)
        node.contradictions.append(Contradiction(
            topic=topic, claim_a=claim_a, claim_b=claim_b,
            source_a=source_a, source_b=source_b,
        ))

    def get_summary(self) -> str:
        lines: list[str] = []
        self._walk(self.root, lines, 0)
        return "\n".join(lines)

    def _walk(self, node: MindMapNode, lines: list[str], depth: int) -> None:
        pre = "  " * depth
        conf = f"{node.confidence:.0%}" if node.confidence else "none"
        lines.append(
            f"{pre}- {node.topic}  ({len(node.sources)} sources, confidence: {conf})"
        )
        for c in node.contradictions:
            lines.append(f"{pre}  [!] Contradiction: {c.claim_a} vs {c.claim_b}")
        for child in node.children:
            self._walk(child, lines, depth + 1)

    def get_gaps(self) -> list[str]:
        return [
            n.topic for n in self._all_nodes()
            if n.confidence < 0.3 and n.topic != self.query
        ]

    def get_contradictions(self) -> list[Contradiction]:
        result: list[Contradiction] = []
        for n in self._all_nodes():
            result.extend(n.contradictions)
        return result

    def source_count(self) -> int:
        return sum(len(n.sources) for n in self._all_nodes())

    def _all_nodes(self) -> list[MindMapNode]:
        nodes: list[MindMapNode] = []
        stack = [self.root]
        while stack:
            n = stack.pop()
            nodes.append(n)
            stack.extend(n.children)
        return nodes


class ActionLog(BaseModel):
    tool: str
    args: dict = Field(default_factory=dict)
    result_summary: str = ""
    timestamp: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat()
    )


class TokenUsage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0

    def add(self, inp: int, out: int) -> None:
        self.input_tokens += inp
        self.output_tokens += out


class ResearchState(BaseModel):
    query: str
    mind_map: MindMap
    iteration: int = 0
    max_iterations: int = 20
    tree_depth: int = 2
    branching_factor: int = 5
    language: str = "auto"
    actions_log: list[ActionLog] = Field(default_factory=list)
    token_usage: TokenUsage = Field(default_factory=TokenUsage)
    draft_requested: bool = False
    status: str = "PENDING"
    report: str = ""
    run_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:8])
    error: str = ""

    @classmethod
    def create(cls, query: str, max_iterations: int = 20, tree_depth: int = 2, branching_factor: int = 5, language: str = "auto") -> ResearchState:
        if language == "auto":
            language = cls._detect_language(query)
        return cls(
            query=query,
            mind_map=MindMap.create(query),
            max_iterations=max_iterations,
            tree_depth=tree_depth,
            branching_factor=branching_factor,
            language=language,
        )

    @staticmethod
    def _detect_language(text: str) -> str:
        """Simple heuristic: count common German vs English words."""
        german_words = ["der", "die", "das", "und", "ist", "ein", "eine", "einen", "nicht",
                        "mit", "auf", "für", "von", "zu", "den", "dem", "des", "sich",
                        "werden", "wird", "hat", "war", "sind", "kann", "muss", "soll",
                        "würde", "könnte", "möchte"]
        english_words = ["the", "and", "that", "have", "for", "not", "with", "this",
                         "but", "from", "they", "will", "would", "there", "their",
                         "what", "about", "which", "when", "make", "like", "just",
                         "over", "take", "into", "year", "also"]

        text_lower = text.lower()
        de_count = sum(1 for w in german_words if f" {w} " in f" {text_lower} ")
        en_count = sum(1 for w in english_words if f" {w} " in f" {text_lower} ")

        if de_count > en_count * 2:
            return "de"
        return "en"

    def increment_iteration(self) -> int:
        self.iteration += 1
        return self.iteration

    def log_action(self, tool: str, args: dict, result_summary: str = "") -> None:
        self.actions_log.append(
            ActionLog(tool=tool, args=args, result_summary=result_summary)
        )

    def is_over_budget(self) -> bool:
        return self.max_iterations > 0 and self.iteration >= self.max_iterations


# ---------------------------------------------------------------------------
# Tool Declarations (OpenAI function-calling format)
# ---------------------------------------------------------------------------


def _tool_declaration(name: str, description: str, parameters: dict) -> dict:
    return {
        "type": "function",
        "function": {"name": name, "description": description, "parameters": parameters},
    }


_TOOLS = [
    _tool_declaration(
        "web_search",
        "Search the web using Brave Search. Returns a list of results with "
        "title, URL, and snippet. Use specific, targeted queries. Include year "
        "for time-sensitive topics. Use quotes for exact phrases. Try multiple "
        "different queries per sub-topic. NEVER repeat a query.",
        {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query."},
                "max_results": {
                    "type": "integer",
                    "description": "Max results (default 10, max 20).",
                },
            },
            "required": ["query"],
        },
    ),
    _tool_declaration(
        "read_webpage",
        "Fetch and extract the main content from a webpage URL. Returns clean "
        "text, title, and URL. Use this to read full articles, documentation, "
        "or news stories. Prefer authoritative primary sources.",
        {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "URL to fetch."},
            },
            "required": ["url"],
        },
    ),
    _tool_declaration(
        "update_findings",
        "Record a research finding in the mind map. Call IMMEDIATELY after "
        "every read_webpage. topic = descriptive category, content = detailed "
        "facts with numbers and quotes, confidence = 0.0 to 1.0.",
        {
            "type": "object",
            "properties": {
                "topic": {"type": "string", "description": "Topic/category."},
                "content": {"type": "string", "description": "Finding text."},
                "sources": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "url": {"type": "string"},
                            "title": {"type": "string"},
                        },
                        "required": ["url", "title"],
                    },
                    "description": "Sources for this finding.",
                },
                "confidence": {
                    "type": "number",
                    "description": "Confidence 0.0-1.0.",
                },
            },
            "required": ["topic", "content", "sources", "confidence"],
        },
    ),
    _tool_declaration(
        "log_contradiction",
        "Record a contradiction between two sources. This helps track "
        "conflicting information for later resolution.",
        {
            "type": "object",
            "properties": {
                "topic": {"type": "string"},
                "claim_a": {"type": "string"},
                "claim_b": {"type": "string"},
                "source_a": {
                    "type": "object",
                    "properties": {
                        "url": {"type": "string"},
                        "title": {"type": "string"},
                    },
                    "required": ["url", "title"],
                },
                "source_b": {
                    "type": "object",
                    "properties": {
                        "url": {"type": "string"},
                        "title": {"type": "string"},
                    },
                    "required": ["url", "title"],
                },
            },
            "required": ["topic", "claim_a", "claim_b", "source_a", "source_b"],
        },
    ),
    _tool_declaration(
        "draft_report",
        "Signal that you are ready to write the final report. Call ONLY after "
        "10+ pages read, all sub-questions answered, contradictions logged. "
        "Your NEXT response MUST be the complete report.",
        {"type": "object", "properties": {}},
    ),
]

# ---------------------------------------------------------------------------
# Tool Handlers
# ---------------------------------------------------------------------------

BRAVE_SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"


async def _tool_web_search(
    args: dict, state: ResearchState, brave_api_key: str | None,
) -> dict:
    query = args.get("query", "")
    if not query:
        return {"error": "Empty search query.", "results": []}
    max_results = min(args.get("max_results", 10), 20)

    if not brave_api_key:
        return {"error": "BRAVE_API_KEY not configured. Configure it in Settings.", "results": []}

    import httpx
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                BRAVE_SEARCH_URL,
                params={"q": query, "count": max_results},
                headers={
                    "Accept": "application/json",
                    "Accept-Encoding": "gzip",
                    "X-Subscription-Token": brave_api_key,
                },
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        logger.warning("Web search failed for %r: %s", query, e)
        return {"error": f"Search failed: {e}", "results": [], "query": query}

    web = data.get("web", {}) if isinstance(data, dict) else {}
    raw_results = web.get("results", []) if isinstance(web, dict) else []

    results = [
        {
            "title": r.get("title", ""),
            "url": r.get("url", ""),
            "snippet": r.get("description", ""),
        }
        for r in raw_results
    ]
    return {"results": results, "count": len(results), "query": query}


MAX_CONTENT_LEN = 100_000


async def _tool_read_webpage(args: dict, state: ResearchState) -> dict:
    url = args.get("url", "")
    if not url:
        return {"error": "No URL provided."}

    try:
        validate_public_url(url)
    except ValueError as e:
        return {"error": str(e)}

    result = await _extract_with_trafilatura(url)
    if not result:
        result = await _extract_with_httpx(url)
    if not result:
        return {"error": f"Could not extract content from {url}."}

    content = result["content"]
    if len(content) > MAX_CONTENT_LEN:
        result["content"] = content[:MAX_CONTENT_LEN] + "\n\n[Content truncated...]"
        result["truncated"] = True
    result["char_count"] = len(content)
    return result


async def _extract_with_trafilatura(url: str) -> dict | None:
    def _extract():
        import trafilatura
        downloaded = trafilatura.fetch_url(url)
        if not downloaded:
            return None
        text = trafilatura.extract(
            downloaded, output_format="markdown",
            include_links=True, with_metadata=True,
        )
        metadata = trafilatura.extract_metadata(downloaded)
        title = metadata.title if metadata else ""
        if not text:
            return None
        return {"content": text, "title": title, "url": url}
    try:
        return await asyncio.to_thread(_extract)
    except Exception as e:
        logger.debug("Trafilatura failed for %s: %s", url, e)
        return None


async def _extract_with_httpx(url: str) -> dict | None:
    try:
        import httpx
        from bs4 import BeautifulSoup
        async with httpx.AsyncClient(follow_redirects=True, timeout=15) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")
            for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
                tag.decompose()
            title = soup.title.string if soup.title else ""
            content = soup.get_text(separator="\n", strip=True)
            if not content or len(content) < 50:
                return None
            return {"content": content, "title": title, "url": url}
    except Exception as e:
        logger.debug("httpx fallback failed for %s: %s", url, e)
        return None


async def _tool_update_findings(args: dict, state: ResearchState) -> dict:
    topic = args.get("topic", "")
    content = args.get("content", "")
    confidence = args.get("confidence", 0.5)
    raw_sources = args.get("sources", [])

    sources = [
        Source(url=s.get("url", ""), title=s.get("title", ""))
        for s in raw_sources
    ]
    state.mind_map.add_finding(
        topic=topic, content=content, sources=sources, confidence=confidence,
    )
    return {"status": "ok", "summary": state.mind_map.get_summary()}


async def _tool_log_contradiction(args: dict, state: ResearchState) -> dict:
    for key in ("topic", "claim_a", "claim_b", "source_a", "source_b"):
        if key not in args:
            return {"error": f"Missing required argument: {key}"}
    state.mind_map.log_contradiction(
        topic=args["topic"],
        claim_a=args["claim_a"],
        claim_b=args["claim_b"],
        source_a=Source(
            url=args["source_a"].get("url", ""),
            title=args["source_a"].get("title", ""),
        ),
        source_b=Source(
            url=args["source_b"].get("url", ""),
            title=args["source_b"].get("title", ""),
        ),
    )
    contras = state.mind_map.get_contradictions()
    return {"status": "ok", "contradictions_count": len(contras)}


async def _tool_draft_report(args: dict, state: ResearchState) -> dict:
    src_count = state.mind_map.source_count()
    topics = len(state.mind_map.root.children)
    if src_count < 3 or topics < 2:
        return {
            "status": "rejected",
            "reason": (
                f"Not enough research yet. {src_count} sources across {topics} "
                f"topics. Need more investigation. Keep searching and reading."
            ),
        }
    state.draft_requested = True
    return {"status": "ready"}


# ---------------------------------------------------------------------------
# System Prompt
# ---------------------------------------------------------------------------

_REPORT_FORMAT = {
    "en": """REQUIRED REPORT FORMAT (markdown):
# Research Report: {{Descriptive Title}}

## Executive Summary (6-8 dense sentences)
- What is the question and why does it matter?
- What are the main findings?
- What are the key tensions, contradictions, or open questions?
- What is the actionable takeaway?

## {{Thematic Section}} — at least 3 sections, each with {depth_paragraphs} dense, citation-rich paragraphs
- One clear theme or dimension per section. Weave sources into the argument.
- Use concrete numbers, dates, and quotes where available.
- Include inline citations like [1], [2], [5] after each sourced claim.

## Contradictions & Debates
- Explicitly surface contradictions between sources.
- If sources disagree, present both sides with citations.
- Note consensus where it exists versus areas of active disagreement.

## Limitations
- What is missing from this report?
- What biases might the sources carry?
- What follow-up research would be needed?

## Sources — [1] Title - URL, numbered by first citation
- List every source, numbered by order of first citation in the report.
- Format: [N] Title — URL""",

    "de": """REQUIRED REPORT FORMAT (markdown):
# Forschungsbericht: {{Aussagekräftiger Titel}}

## Zusammenfassung (6-8 dichte Sätze)
- Was ist die Frage und warum ist sie relevant?
- Was sind die wichtigsten Erkenntnisse?
- Welche Spannungen, Widersprüche oder offenen Fragen gibt es?
- Was ist die handlungsrelevante Kernaussage?

## {{Thematischer Abschnitt}} — mindestens 3 Abschnitte, jeweils {depth_paragraphs} dichte, quellengestützte Absätze
- Ein klares Thema oder eine Dimension pro Abschnitt. Quellen in die Argumentation einweben.
- Konkrete Zahlen, Daten und Zitate verwenden, wo verfügbar.
- Inline-Zitationen wie [1], [2], [5] nach jeder quellengestützten Behauptung einfügen.

## Widersprüche & Debatten
- Widersprüche zwischen Quellen explizit aufzeigen.
- Wenn Quellen uneins sind, beide Seiten mit Zitationen darstellen.
- Konsensbereiche von aktiven Meinungsverschiedenheiten unterscheiden.

## Einschränkungen
- Was fehlt in diesem Bericht?
- Welche Verzerrungen könnten die Quellen enthalten?
- Welche Folgerecherche wäre nötig?

## Quellen — [1] Titel - URL, nummeriert nach erster Zitation
- Jede Quelle auflisten, nummeriert nach Reihenfolge der ersten Zitation im Bericht.
- Format: [N] Titel — URL""",
}


SYSTEM_TEMPLATE = """\
You are an autonomous deep research agent. You conduct rigorous, multi-source
investigations and produce publication-quality reports where every factual claim
is backed by a citation. You are methodical and thorough.

LANGUAGE REQUIREMENT:
You MUST write the ENTIRE final report in {language_name} ({language_code}).
- Think in {language_name} throughout the research process.
- Write ALL findings, summaries, and the final report directly in {language_name}.
- Do NOT write in English then translate — produce the output natively in {language_name}.
- ALL section headings, citations, and metadata must be in {language_name}.

RESEARCH METHODOLOGY:

Phase 1 — Decompose:
Break the query into 5-8 distinct sub-questions covering different angles.

Phase 2 — Search and Read (repeat at least 5-10 times):
For EACH sub-question:
1. web_search with a specific, targeted query (NEVER repeat queries)
2. read_webpage on the 2-3 best results
3. update_findings IMMEDIATELY after each read_webpage
Continue until you have real source data for all sub-questions.

Phase 3 — Verify and Deepen:
- Low confidence topics? Search and read MORE.
- Contradictions? Log them with log_contradiction.
- Claims from single sources? Find a second source.

Phase 4 — Synthesize:
ONLY when you have findings across ALL sub-questions with real sources,
log contradictions, investigate low-confidence areas — THEN call draft_report()
and write the complete report.

TREE TOPOLOGY — Current level: {current_depth}/{tree_depth}, Branching: {branching_factor}

You are conducting research as a recursive decomposition tree:
- At level 1, decompose the query into {branching_factor} distinct sub-questions.
- For EACH sub-question: search + read 2–3 sources + record findings.
- Then identify the 2–3 most promising or under-explored branches and descend to level 2.
- At level 2, for each branch: decompose into {branching_factor} sub-sub-questions.
- Repeat until you reach level {tree_depth} (terminal leaves).
- At terminal leaves: produce a thorough, cited summary for that branch.
- After all branches are complete: synthesize upward into a single cohesive report.

For a shallow tree (depth=1), you spread wide but never descend — each of the {branching_factor} sub-questions gets one round of research then you synthesize.
For a deep tree (depth=4–5), you drill down methodically, narrowing scope at each level.

TOOL DISTANCE RULE:
Between draft_report() and your final report text, you may make AT MOST one
more tool call (e.g. one last web_search or read_webpage to fill a critical
gap). After calling draft_report(), write the report in your next response.

CITATION RULES:
- Every factual claim MUST have an inline citation [N].
- Number sources sequentially: [1], [2], [3]. Multiple: [1][3].
- If you cannot cite a claim, do NOT include it.

{report_format_template}

QUALITY STANDARDS:
- DEPTH: {depth_paragraphs} paragraphs per section
- SPECIFICITY: Exact numbers, dates, names
- BALANCE: Multiple perspectives
- LENGTH: Minimum 1500 words

CURRENT STATE:
Query: "{query}"
Language: {language_name} ({language_code})
Tree: depth {current_depth}/{tree_depth}, branching {branching_factor}
Findings so far: {mind_map_summary}
Knowledge gaps: {gaps}
Contradictions: {contradictions}
Sources consulted: {source_count}
Iteration: {iteration}/{max_iterations}

Research the query thoroughly. Do NOT rush to draft_report(). A 10-source,
well-structured report is vastly better than a 2-source summary."""


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

SSEEventHandler = Callable[[dict], None]


class ResearchOrchestrator:
    """Runs the autonomous research agent loop.

    Emits SSE events for real-time progress tracking. Designed to be headless
    — no console UI. All state is accessible for polling/export.
    """

    def __init__(
        self,
        client: OpenRouterClient,
        state: ResearchState,
        *,
        brave_api_key: str | None = None,
        on_event: SSEEventHandler | None = None,
    ) -> None:
        self._client = client
        self._state = state
        self._brave_api_key = brave_api_key
        self._on_event = on_event
        self._stop_flag = asyncio.Event()
        self._event_queue: asyncio.Queue[dict] = asyncio.Queue(maxsize=500)
        self._start_time: float = 0.0

    @property
    def state(self) -> ResearchState:
        return self._state

    @property
    def run_id(self) -> str:
        return self._state.run_id

    def stop(self) -> None:
        """Signal the orchestrator to stop at the next safe point."""
        self._stop_flag.set()
        self._state.status = "STOPPED"

    async def run(self, query: str) -> str:
        """Run the autonomous research loop. Returns the final report text."""
        self._start_time = time.monotonic()
        self._state.status = "RUNNING"
        self._emit("thinking", "Analyzing query and planning research strategy...")

        try:
            report = await self._agent_loop()
        except RouterExhaustedError as e:
            self._state.error = str(e)
            self._state.status = "ERROR"
            self._emit("error", str(e))
            return f"Research failed: {e}"
        except asyncio.CancelledError:
            self._state.status = "STOPPED"
            self._emit("error", "Research was cancelled")
            raise
        except Exception as e:
            logger.exception("Unhandled error in research orchestrator")
            self._state.error = str(e)
            self._state.status = "ERROR"
            self._emit("error", str(e))
            return f"Research failed due to internal error: {e}"
        else:
            self._state.status = "COMPLETED"
            elapsed = time.monotonic() - self._start_time
            self._emit("status", {
                "iteration": self._state.iteration,
                "sources": self._state.mind_map.source_count(),
                "input_tokens": self._state.token_usage.input_tokens,
                "output_tokens": self._state.token_usage.output_tokens,
                "elapsed_seconds": round(elapsed, 1),
            })
            self._emit("complete", report)
            return report
        finally:
            self._emit("done", {})

    async def event_stream(self):
        """Async generator yielding SSE-formatted events from the queue."""
        while True:
            try:
                event = await asyncio.wait_for(self._event_queue.get(), timeout=30)
                event_type = event.get("event", "message")
                data = event.get("data", "")
                if event_type == "done":
                    break
                yield f"event: {event_type}\ndata: {_json.dumps(data)}\n\n"
            except TimeoutError:
                yield "event: ping\ndata: {}\n\n"

    # ---- agent loop ----

    async def _agent_loop(self) -> str:
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": self._build_system_prompt()},
            {"role": "user", "content": f"Research this thoroughly: {self._state.query}"},
        ]

        response = await self._send(messages)
        self._state.increment_iteration()

        while True:
            if self._stop_flag.is_set():
                return await self._finalize_on_stop(messages)

            tool_calls = response.get("tool_calls")
            finish_reason = response.get("finish_reason", "")

            if tool_calls:
                assistant_msg = self._response_to_message(response)
                messages.append(assistant_msg)

                tool_results_msgs = await self._execute_tool_calls(tool_calls)
                messages.extend(tool_results_msgs)

                self._emit("status", {
                    "iteration": self._state.iteration,
                    "max_iterations": self._state.max_iterations,
                    "sources": self._state.mind_map.source_count(),
                })

                response = await self._send(messages)

                if self._state.draft_requested and not response.get("tool_calls"):
                    return await self._handle_report(response, messages)
            else:
                if self._state.draft_requested:
                    text = response.get("text", "")
                    if text and len(text) > 200:
                        self._state.report = text
                        return text

                if finish_reason == "stop" and response.get("text"):
                    return response["text"]

            if self._state.is_over_budget():
                self._emit("thinking", "Max iterations reached. Requesting final report...")
                messages.append({
                    "role": "user",
                    "content": (
                        "Iteration limit reached. You MUST write the final "
                        "research report NOW. Do not call any more tools."
                    ),
                })
                response = await self._send(messages, tools=None)
                text = response.get("text", "")
                if text:
                    self._state.report = text
                    return text
                return "Research completed but could not generate report (iteration limit)."

            self._state.increment_iteration()

            if response.get("text") and not tool_calls:
                messages.append(self._response_to_message(response))
                messages.append({
                    "role": "user",
                    "content": (
                        "Continue researching. Search for more sources, read "
                        "more pages, and update your findings. Do NOT write "
                        "the report yet unless you have thoroughly covered "
                        "all sub-questions with real data from read_webpage."
                    ),
                })
                response = await self._send(messages)

    async def _handle_report(self, response: dict, messages: list[dict]) -> str:
        text = response.get("text", "")
        if text and len(text) > 200:
            self._state.report = text
            return text

        messages.append(self._response_to_message(response))
        messages.append({
            "role": "user",
            "content": (
                "draft_report() was approved. Write the complete research "
                "report now. Follow the required format. Include citations. "
                "Be thorough. Do NOT call any more tools."
            ),
        })
        response = await self._send(messages, tools=None)
        text = response.get("text", "")
        if text:
            self._state.report = text
            return text

        return self._state.mind_map.get_summary()

    async def _finalize_on_stop(self, messages: list[dict]) -> str:
        self._emit("thinking", "Stop requested. Generating partial report...")
        messages.append({
            "role": "user",
            "content": (
                "Stop requested. Write a concise report covering what you "
                "have found so far. Include all findings and sources. "
                "Do NOT call any more tools."
            ),
        })
        try:
            response = await self._send(messages, tools=None)
            text = response.get("text", "")
            if text:
                self._state.report = text
                return text
        except Exception:
            pass
        return self._state.mind_map.get_summary() or "Research stopped."

    # ---- helpers ----

    async def _send(
        self, messages: list[dict], *,
        tools: list[dict] | None = _TOOLS,
    ) -> dict[str, Any]:
        t0 = time.monotonic()
        try:
            result = await self._client.chat_completion_full(
                messages=messages,
                temperature=0.4,
                tools=tools,
            )
        except Exception as e:
            logger.error("LLM call failed: %s", e)
            raise

        elapsed = time.monotonic() - t0
        usage = result.get("usage") or {}
        if usage:
            self._state.token_usage.add(
                usage.get("prompt_tokens", 0),
                usage.get("completion_tokens", 0),
            )
        logger.debug(
            "LLM call: %.1fs, %d input, %d output tokens",
            elapsed,
            usage.get("prompt_tokens", 0),
            usage.get("completion_tokens", 0),
        )
        return result

    @staticmethod
    def _response_to_message(response: dict) -> dict:
        msg: dict[str, Any] = {"role": "assistant", "content": response.get("text")}
        if response.get("tool_calls"):
            msg["tool_calls"] = response["tool_calls"]
        return msg

    async def _execute_tool_calls(
        self, tool_calls: list[dict],
    ) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for tc in tool_calls:
            fn = tc.get("function", {})
            name = fn.get("name", "")
            args_str = fn.get("arguments", "{}")
            tc_id = tc.get("id", "")

            try:
                args = _json.loads(args_str) if isinstance(args_str, str) else args_str
            except _json.JSONDecodeError:
                args = {}

            self._emit("tool_call", {"name": name, "args": args})

            t0 = time.monotonic()
            result = await self._dispatch_tool(name, args)
            elapsed = time.monotonic() - t0

            summary = self._summarize_result(name, result)
            self._state.log_action(name, args, summary)
            self._emit("tool_result", {
                "name": name,
                "summary": summary,
                "elapsed_seconds": round(elapsed, 2),
            })

            results.append({
                "role": "tool",
                "tool_call_id": tc_id,
                "content": _json.dumps(result, default=str),
            })
        return results

    async def _dispatch_tool(self, name: str, args: dict) -> dict:
        handlers = {
            "web_search": lambda a: _tool_web_search(a, self._state, self._brave_api_key),
            "read_webpage": lambda a: _tool_read_webpage(a, self._state),
            "update_findings": lambda a: _tool_update_findings(a, self._state),
            "log_contradiction": lambda a: _tool_log_contradiction(a, self._state),
            "draft_report": lambda a: _tool_draft_report(a, self._state),
        }
        handler = handlers.get(name)
        if not handler:
            return {"error": f"Unknown tool: {name}"}
        try:
            return await handler(args)
        except Exception as e:
            logger.exception("Tool %s failed", name)
            return {"error": f"{type(e).__name__}: {e}"}

    @staticmethod
    def _summarize_result(name: str, result: dict) -> str:
        if result.get("error"):
            return f"Error: {result['error'][:100]}"
        if name == "web_search":
            return f"{result.get('count', 0)} results for '{result.get('query', '')}'"
        if name == "read_webpage":
            chars = result.get("char_count", 0)
            truncated = " (truncated)" if result.get("truncated") else ""
            return f"{chars} chars{truncated}"
        if name == "update_findings":
            return "Recorded"
        if name == "log_contradiction":
            return f"{result.get('contradictions_count', 0)} contradictions total"
        if name == "draft_report":
            return result.get("status", "unknown")
        return str(result)[:100]

    def _build_system_prompt(self) -> str:
        state = self._state
        gaps = state.mind_map.get_gaps()
        contradictions = state.mind_map.get_contradictions()

        # Map language code to display name
        lang_names = {"en": "English", "de": "German (Deutsch)"}
        language_name = lang_names.get(state.language, "English")
        language_code = state.language

        # Determine current depth: count deepest MindMapNode level visited
        current_depth = self._compute_current_depth()

        # Depth-based paragraph requirement
        depth_paragraphs = state.tree_depth * 2

        # Localized report format template
        report_format_template = _REPORT_FORMAT.get(
            language_code, _REPORT_FORMAT["en"]
        ).format(depth_paragraphs=depth_paragraphs)

        return SYSTEM_TEMPLATE.format(
            query=state.query,
            language_name=language_name,
            language_code=language_code,
            current_depth=current_depth,
            tree_depth=state.tree_depth,
            branching_factor=state.branching_factor,
            depth_paragraphs=depth_paragraphs,
            mind_map_summary=state.mind_map.get_summary() or "(no findings yet)",
            gaps=", ".join(gaps) if gaps else "none identified yet",
            contradictions=(
                f"{len(contradictions)} unresolved"
                if contradictions
                else "none"
            ),
            source_count=state.mind_map.source_count(),
            iteration=state.iteration,
            max_iterations=str(state.max_iterations) if state.max_iterations else "unlimited",
            report_format_template=report_format_template,
        )

    def _compute_current_depth(self) -> int:
        """Compute the deepest level of the MindMap tree currently explored."""
        def max_depth(node, depth=0):
            if not node.children:
                return depth
            return max(max_depth(c, depth + 1) for c in node.children)
        try:
            return max_depth(self._state.mind_map.root)
        except Exception:
            return 1

    def _emit(self, event_type: str, data: Any) -> None:
        payload = {"event": event_type, "data": data}
        if self._on_event:
            with suppress(Exception):
                self._on_event(payload)
        with suppress(asyncio.QueueFull):
            self._event_queue.put_nowait(payload)

    def to_dict(self) -> dict[str, Any]:
        return self._state.model_dump()

    def to_json(self) -> str:
        return self._state.model_dump_json(indent=2)
