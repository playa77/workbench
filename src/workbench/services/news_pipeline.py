"""News Pipeline — core orchestration for RSS scraping, analysis, and generation.

Adapted from ai_news_scraper/src/pipeline.py.
Uses the workbench OpenRouter client and NewsStore for data persistence.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any

import feedparser
import httpx
import trafilatura

from workbench.core.router import OpenRouterClient
from workbench.services.news_store import NewsStore

logger = logging.getLogger(__name__)


class NewsPipeline:
    def __init__(self, store: NewsStore, session: Any):
        self._store = store
        self._session = session

    async def run(self, user_id: str, interest: dict, openrouter_key: str) -> int:
        interest_id = interest["id"]
        llm = OpenRouterClient(api_key=openrouter_key)
        run_record = await self._store.create_run(interest_id)
        run_id = run_record["id"]

        try:
            await self._scrape(run_id, interest_id)
            await self._analyze(run_id, interest, llm)
            if interest.get("enable_summary") or interest.get("enable_script"):
                await self._generate(run_id, interest, llm)
            if interest.get("enable_brief"):
                await self._brief(run_id, interest, llm)
            await self._store.update_run(run_id, status="completed", completed_at=datetime.now(tz=datetime.UTC).isoformat())
        except Exception as exc:
            logger.error("Pipeline run %d failed: %s", run_id, exc)
            await self._store.update_run(run_id, status="failed", error=str(exc))
        finally:
            await llm.close()

        return run_id

    async def _scrape(self, run_id: int, interest_id: int) -> None:
        await self._store.update_run(run_id, current_stage="scrape")
        feeds = await self._store.get_feeds_for_interest(interest_id)

        if not feeds:
            logger.info("No feeds configured for interest %d", interest_id)
            return

        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0), follow_redirects=True) as http:
            for feed in feeds:
                try:
                    parsed = feedparser.parse(feed["url"])
                    for entry in parsed.entries[:20]:
                        url = entry.get("link", "")
                        if not url:
                            continue
                        existing = await self._store.article_exists(url)
                        if existing:
                            continue

                        title = entry.get("title", "Untitled")
                        published = entry.get("published", datetime.utcnow().isoformat())

                        try:
                            resp = await http.get(url)
                            html = resp.text
                            content = trafilatura.extract(html, include_comments=False, include_tables=False)
                        except Exception:
                            content = None

                        await self._store.insert_article(
                            run_id=run_id,
                            feed_id=feed["id"],
                            url=url,
                            title=title,
                            author=entry.get("author"),
                            published_at=published,
                            excerpt=entry.get("summary"),
                            content=content,
                            content_status="full" if content else "excerpt",
                        )
                    logger.info("Scraped feed %s: %d new articles", feed["name"], len(parsed.entries))
                except Exception as exc:
                    logger.warning("Failed to scrape feed %s: %s", feed["url"], exc)

    async def _analyze(self, run_id: int, interest: dict, llm: OpenRouterClient) -> None:
        await self._store.update_run(run_id, current_stage="analyze")
        articles = await self._store.get_articles_for_run(run_id)
        if not articles:
            logger.info("No articles to analyze for run %d", run_id)
            return

        article_texts = []
        for a in articles[:30]:
            body = a.get("content") or a.get("excerpt") or ""
            if len(body) > 2000:
                body = body[:2000]
            article_texts.append(f"Title: {a['title']}\nSource: {a.get('url','')}\nBody: {body}")

        prompt = (
            "Analyze the following news articles. Identify 3-5 major themes. "
            "For each theme, provide:\n"
            "1. A concise title (one line)\n"
            "2. A two-sentence description\n"
            "3. Which article numbers are relevant\n\n"
            "Format as JSON array:\n"
            '[{"title": "...", "description": "...", "article_indices": [1,3,5]}, ...]\n\n'
            "Articles:\n\n"
        )
        for i, text in enumerate(article_texts, 1):
            prompt += f"[{i}] {text}\n\n"

        try:
            response = await llm.chat_completion(
                messages=[
                    {"role": "system", "content": "You are a news analyst. Respond only with valid JSON."},
                    {"role": "user", "content": prompt},
                ],
                model="deepseek/deepseek-v4-pro",
                temperature=0.3,
                max_tokens=2000,
            )
            import json, re
            match = re.search(r"\[.*\]", response, re.DOTALL)
            if match:
                themes = json.loads(match.group(0))
                for i, theme in enumerate(themes[:5]):
                    await self._store.insert_theme(
                        run_id=run_id,
                        title=theme.get("title", f"Theme {i+1}"),
                        description=theme.get("description", ""),
                        source_article_ids=theme.get("article_indices", []),
                        order_index=i,
                    )
                logger.info("Analyzed %d themes from %d articles", len(themes), len(article_texts))
        except Exception as exc:
            logger.error("Analysis failed: %s", exc)

    async def _generate(self, run_id: int, interest: dict, llm: OpenRouterClient) -> None:
        await self._store.update_run(run_id, current_stage="generate")
        themes = await self._store.get_themes_for_run(run_id)
        articles = await self._store.get_articles_for_run(run_id)

        for theme in themes:
            try:
                target_words = interest.get("target_summary_words", 750)
                prompt = (
                    f"Write a {target_words}-word summary of this news theme:\n\n"
                    f"Theme: {theme['title']}\n"
                    f"Description: {theme['description']}\n\n"
                    "Write a well-structured, journalistic summary with a headline."
                )
                response = await llm.chat_completion(
                    messages=[
                        {"role": "system", "content": "You are a professional journalist. Write clear, engaging summaries."},
                        {"role": "user", "content": prompt},
                    ],
                    model="deepseek/deepseek-v4-pro",
                    temperature=0.5,
                    max_tokens=2000,
                )
                await self._store.insert_deliverable(theme["id"], "summary", response)

                if interest.get("enable_script"):
                    target_script = interest.get("target_script_words", 1250)
                    script_prompt = (
                        f"Write a {target_script}-word YouTube script about this news theme:\n\n"
                        f"Theme: {theme['title']}\n"
                        f"Summary: {response}\n\n"
                        "Format as a video script with intro, segments, and outro. Include speaker directions in [brackets]."
                    )
                    script = await llm.chat_completion(
                        messages=[
                            {"role": "system", "content": "You are a video script writer. Write engaging YouTube scripts."},
                            {"role": "user", "content": script_prompt},
                        ],
                        model="deepseek/deepseek-v4-pro",
                        temperature=0.6,
                        max_tokens=3000,
                    )
                    await self._store.insert_deliverable(theme["id"], "script", script)

                logger.info("Generated content for theme: %s", theme["title"])
            except Exception as exc:
                logger.error("Generation failed for theme %s: %s", theme["title"], exc)

    async def _brief(self, run_id: int, interest: dict, llm: OpenRouterClient) -> None:
        await self._store.update_run(run_id, current_stage="brief")
        themes = await self._store.get_themes_for_run(run_id)
        if not themes:
            return

        theme_summaries = "\n\n".join(f"## {t['title']}\n{t['description']}" for t in themes)

        try:
            prompt = (
                "Synthesize a daily news brief from these themes:\n\n"
                f"{theme_summaries}\n\n"
                "Write a cohesive 400-600 word brief that ties these themes together, "
                "highlighting connections and key takeaways."
            )
            response = await llm.chat_completion(
                messages=[
                    {"role": "system", "content": "You are an executive editor. Write concise, insightful daily briefs."},
                    {"role": "user", "content": prompt},
                ],
                model="deepseek/deepseek-v4-pro",
                temperature=0.4,
                max_tokens=1500,
            )
            await self._store.insert_brief(run_id, response)
            logger.info("Generated daily brief for run %d", run_id)
        except Exception as exc:
            logger.error("Brief generation failed: %s", exc)
