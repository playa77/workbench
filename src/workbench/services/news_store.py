"""News Plugin — data store (PostgreSQL-backed).

Replaces the SQLite-based Database class from ai_news_scraper.
Tables: news_interests, news_feeds, news_runs, news_articles, news_themes, news_deliverables, news_briefs
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import select, insert, update, delete, text
from sqlalchemy.ext.asyncio import AsyncSession


class NewsStore:
    def __init__(self, session: AsyncSession):
        self._s = session

    # ---- Interests ----
    async def list_interests(self, user_id: str) -> list[dict]:
        rows = await self._s.execute(
            text("SELECT * FROM news_interests WHERE user_id = :uid ORDER BY name"),
            {"uid": user_id},
        )
        return [dict(r._mapping) for r in rows]

    async def get_interest(self, user_id: str, interest_id: int) -> Optional[dict]:
        row = await self._s.execute(
            text("SELECT * FROM news_interests WHERE id = :iid AND user_id = :uid"),
            {"iid": interest_id, "uid": user_id},
        )
        r = row.first()
        return dict(r._mapping) if r else None

    async def create_interest(self, user_id: str, data: dict) -> dict:
        result = await self._s.execute(
            text("""INSERT INTO news_interests (user_id, name, start_time, interval_hours, target_summary_words, target_script_words, enable_summary, enable_script, enable_brief, enable_email)
                   VALUES (:uid, :name, :start_time, :interval_hours, :target_summary_words, :target_script_words, :enable_summary, :enable_script, :enable_brief, :enable_email)
                   RETURNING *"""),
            {
                "uid": user_id,
                "name": data.get("name", "New Interest"),
                "start_time": data.get("start_time", "04:00"),
                "interval_hours": data.get("interval_hours", 24),
                "target_summary_words": data.get("target_summary_words", 750),
                "target_script_words": data.get("target_script_words", 1250),
                "enable_summary": data.get("enable_summary", True),
                "enable_script": data.get("enable_script", True),
                "enable_brief": data.get("enable_brief", True),
                "enable_email": data.get("enable_email", True),
            },
        )
        await self._s.commit()
        return dict(result.first()._mapping)

    async def delete_interest(self, user_id: str, interest_id: int) -> None:
        await self._s.execute(
            text("DELETE FROM news_interests WHERE id = :iid AND user_id = :uid"),
            {"iid": interest_id, "uid": user_id},
        )
        await self._s.commit()

    # ---- Feeds ----
    async def list_feeds(self, user_id: str, interest_id: int) -> list[dict]:
        rows = await self._s.execute(
            text("SELECT * FROM news_feeds WHERE interest_id = :iid ORDER BY name"),
            {"iid": interest_id},
        )
        return [dict(r._mapping) for r in rows]

    async def add_feed(self, user_id: str, interest_id: int, url: str, name: str, category: str) -> dict:
        result = await self._s.execute(
            text("""INSERT INTO news_feeds (interest_id, url, name, category)
                   VALUES (:iid, :url, :name, :cat)
                   ON CONFLICT (interest_id, url) DO UPDATE SET name = :name2, category = :cat2
                   RETURNING *"""),
            {"iid": interest_id, "url": url, "name": name, "cat": category, "name2": name, "cat2": category},
        )
        await self._s.commit()
        return dict(result.first()._mapping)

    async def delete_feed(self, user_id: str, interest_id: int, feed_id: int) -> None:
        await self._s.execute(
            text("DELETE FROM news_feeds WHERE id = :fid AND interest_id = :iid"),
            {"fid": feed_id, "iid": interest_id},
        )
        await self._s.commit()

    async def get_feeds_for_interest(self, interest_id: int) -> list[dict]:
        rows = await self._s.execute(
            text("SELECT * FROM news_feeds WHERE interest_id = :iid"),
            {"iid": interest_id},
        )
        return [dict(r._mapping) for r in rows]

    # ---- Pipeline Runs ----
    async def create_run(self, interest_id: int) -> dict:
        result = await self._s.execute(
            text("""INSERT INTO news_runs (interest_id, status, started_at, run_date)
                   VALUES (:iid, 'running', :now, :today)
                   RETURNING *"""),
            {"iid": interest_id, "now": datetime.utcnow().isoformat(), "today": datetime.utcnow().strftime("%Y-%m-%d")},
        )
        await self._s.commit()
        return dict(result.first()._mapping)

    async def update_run(self, run_id: int, **kwargs) -> None:
        sets = ", ".join(f"{k} = :{k}" for k in kwargs)
        await self._s.execute(
            text(f"UPDATE news_runs SET {sets} WHERE id = :rid"),
            {**kwargs, "rid": run_id},
        )
        await self._s.commit()

    async def list_runs(self, user_id: str, interest_id: int) -> list[dict]:
        rows = await self._s.execute(
            text("SELECT * FROM news_runs WHERE interest_id = :iid ORDER BY id DESC LIMIT 20"),
            {"iid": interest_id},
        )
        return [dict(r._mapping) for r in rows]

    async def get_run(self, run_id: int) -> Optional[dict]:
        row = await self._s.execute(text("SELECT * FROM news_runs WHERE id = :rid"), {"rid": run_id})
        r = row.first()
        return dict(r._mapping) if r else None

    # ---- Articles ----
    async def article_exists(self, url: str) -> bool:
        row = await self._s.execute(text("SELECT 1 FROM news_articles WHERE url = :url LIMIT 1"), {"url": url})
        return row.first() is not None

    async def insert_article(self, run_id: int, feed_id: int, url: str, title: str, author: Optional[str], published_at: str, excerpt: Optional[str], content: Optional[str], content_status: str) -> dict:
        result = await self._s.execute(
            text("""INSERT INTO news_articles (run_id, feed_id, url, title, author, published_at, scraped_at, excerpt, content, content_status)
                   VALUES (:rid, :fid, :url, :title, :author, :pat, :now, :excerpt, :content, :cs)
                   ON CONFLICT (url) DO NOTHING
                   RETURNING *"""),
            {"rid": run_id, "fid": feed_id, "url": url, "title": title, "author": author, "pat": published_at, "now": datetime.utcnow().isoformat(), "excerpt": excerpt, "content": content, "cs": content_status},
        )
        await self._s.commit()
        r = result.first()
        return dict(r._mapping) if r else {}

    async def get_articles_for_run(self, run_id: int) -> list[dict]:
        rows = await self._s.execute(text("SELECT * FROM news_articles WHERE run_id = :rid"), {"rid": run_id})
        return [dict(r._mapping) for r in rows]

    # ---- Themes ----
    async def insert_theme(self, run_id: int, title: str, description: str, source_article_ids: list[int], order_index: int) -> dict:
        result = await self._s.execute(
            text("""INSERT INTO news_themes (run_id, title, description, source_article_ids, order_index)
                   VALUES (:rid, :title, :desc, :saids, :oi)
                   RETURNING *"""),
            {"rid": run_id, "title": title, "desc": description, "saids": json.dumps(source_article_ids), "oi": order_index},
        )
        await self._s.commit()
        return dict(result.first()._mapping)

    async def get_themes_for_run(self, run_id: int) -> list[dict]:
        rows = await self._s.execute(text("SELECT * FROM news_themes WHERE run_id = :rid ORDER BY order_index"), {"rid": run_id})
        return [dict(r._mapping) for r in rows]

    # ---- Deliverables ----
    async def insert_deliverable(self, theme_id: int, d_type: str, content: str) -> dict:
        result = await self._s.execute(
            text("""INSERT INTO news_deliverables (theme_id, deliverable_type, content)
                   VALUES (:tid, :dt, :content)
                   RETURNING *"""),
            {"tid": theme_id, "dt": d_type, "content": content},
        )
        await self._s.commit()
        return dict(result.first()._mapping)

    # ---- Briefs ----
    async def insert_brief(self, run_id: int, content: str) -> dict:
        result = await self._s.execute(
            text("""INSERT INTO news_briefs (run_id, content, word_count)
                   VALUES (:rid, :content, :wc)
                   RETURNING *"""),
            {"rid": run_id, "content": content, "wc": len(content.split())},
        )
        await self._s.commit()
        return dict(result.first()._mapping)

    async def get_daily_brief_for_run(self, run_id: int) -> Optional[dict]:
        row = await self._s.execute(text("SELECT * FROM news_briefs WHERE run_id = :rid LIMIT 1"), {"rid": run_id})
        r = row.first()
        return dict(r._mapping) if r else None

    async def get_previous_brief(self, before_date: str) -> Optional[dict]:
        row = await self._s.execute(
            text("SELECT nb.* FROM news_briefs nb JOIN news_runs nr ON nb.run_id = nr.id WHERE nr.run_date < :bd AND nr.status = 'completed' ORDER BY nr.run_date DESC LIMIT 1"),
            {"bd": before_date},
        )
        r = row.first()
        return dict(r._mapping) if r else None
