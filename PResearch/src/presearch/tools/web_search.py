"""Web search tool using Brave Search API."""

from __future__ import annotations

import logging

import httpx

from presearch.providers.types import ToolDeclaration

log = logging.getLogger(__name__)

BRAVE_SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"

WEB_SEARCH_DECLARATION = ToolDeclaration(
    name="web_search",
    description=(
        "Search the web using Brave Search. Returns a list of results with "
        "title, URL, and snippet. Use specific, targeted queries — not vague "
        "ones. Include year for time-sensitive topics. Use quotes for exact "
        "phrases. Try multiple different queries per sub-topic."
    ),
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query. Be specific and targeted.",
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum results to return (default 10, max 20).",
            },
        },
        "required": ["query"],
    },
)


async def handle_web_search(args: dict, **_ctx) -> dict:
    """Execute a Brave Search web search with error handling."""
    query = args.get("query", "")
    if not query:
        return {"error": "Empty search query.", "results": []}
    max_results = min(args.get("max_results", 10), 20)

    api_key = _ctx.get("config").brave_api_key if _ctx.get("config") else None
    if not api_key:
        return {"error": "BRAVE_API_KEY is not configured.", "results": []}

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                BRAVE_SEARCH_URL,
                params={"q": query, "count": max_results},
                headers={
                    "Accept": "application/json",
                    "Accept-Encoding": "gzip",
                    "X-Subscription-Token": api_key,
                },
            )
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError as e:
        log.warning("Web search failed for %r: %s", query, e)
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
