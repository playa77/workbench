"""Knowledge Base Agent — RAG-powered document ingestion and querying."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agents.base import AgentBase
from agents.knowledge.ingestion import IngestPipeline, get_ingestion_progress
from agents.knowledge.models import KnowledgeBase, KnowledgeDocument
from agents.knowledge.vector_store import VectorStore
from workbench.core.agents import get_user_agent_settings as _get_agent_settings
from workbench.core.auth import get_current_user, get_user_inference_api_key, get_user_llm_client
from workbench.core.db import get_session
from workbench.core.models import User
from workbench.shared.llm.router import OpenRouterClient

logger = logging.getLogger(__name__)


class KnowledgeBaseAgent(AgentBase):
    name = "knowledge"
    display_name = "Knowledge Base"
    description = "Ingest documents into a vector database and ask questions over them with RAG"
    version = "0.1.0"
    icon = "database"

    def _build_router(self) -> APIRouter:
        router = APIRouter()
        router.add_api_route("/kbs", self.list_kbs, methods=["GET"])
        router.add_api_route("/kbs", self.create_kb, methods=["POST"])
        router.add_api_route("/kbs/{kb_id}", self.get_kb, methods=["GET"])
        router.add_api_route("/kbs/{kb_id}", self.delete_kb, methods=["DELETE"])
        router.add_api_route("/kbs/{kb_id}/upload", self.upload_document, methods=["POST"])
        router.add_api_route("/kbs/{kb_id}/upload-text", self.upload_text, methods=["POST"])
        router.add_api_route("/kbs/{kb_id}/documents", self.list_documents, methods=["GET"])
        router.add_api_route(
            "/kbs/{kb_id}/documents/{doc_id}", self.get_document, methods=["GET"]
        )
        router.add_api_route(
            "/kbs/{kb_id}/documents/{doc_id}", self.delete_document, methods=["DELETE"]
        )
        router.add_api_route("/kbs/{kb_id}/query", self.query_kb, methods=["POST"])
        router.add_api_route(
            "/kbs/{kb_id}/ingestion-progress", self.ingestion_progress, methods=["GET"]
        )
        router.add_api_route(
            "/kbs/{kb_id}/chunks/{doc_id}", self.list_chunks, methods=["GET"]
        )
        return router

    def get_settings_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "default_chunk_size": {
                    "type": "integer",
                    "title": "Default Chunk Size",
                    "description": "Characters per chunk",
                    "default": 1000,
                    "minimum": 200,
                    "maximum": 8000,
                },
                "default_chunk_overlap": {
                    "type": "integer",
                    "title": "Default Chunk Overlap",
                    "description": "Character overlap between consecutive chunks",
                    "default": 200,
                    "minimum": 0,
                    "maximum": 2000,
                },
                "embedding_model": {
                    "type": "string",
                    "title": "Embedding Model",
                    "description": "OpenRouter embedding model ID",
                    "default": "openai/text-embedding-3-small",
                },
                "top_k": {
                    "type": "integer",
                    "title": "Top K Chunks",
                    "description": "Number of chunks to retrieve per query",
                    "default": 5,
                    "minimum": 1,
                    "maximum": 20,
                },
            },
            "additionalProperties": False,
        }

    def get_default_settings(self) -> dict[str, Any]:
        return {
            "default_chunk_size": 1000,
            "default_chunk_overlap": 200,
            "embedding_model": "openai/text-embedding-3-small",
            "top_k": 5,
        }

    def get_static_dir(self) -> Path:
        return Path(__file__).parent / "static"

    def get_frontend_tab(self) -> dict:
        return {
            "id": self.name,
            "displayName": self.display_name,
            "icon": self.icon,
            "component": f"agent-{self.name}",
            "js": f"/static/plugins/{self.name}/js/tab.js",
            "css": f"/static/plugins/{self.name}/css/styles.css",
        }

    async def on_enable(self, user_id: str, session: AsyncSession) -> None:
        pass

    async def on_disable(self, user_id: str, session: AsyncSession) -> None:
        pass

    async def _require_enabled(self, user: User, session: AsyncSession) -> None:
        user_settings = await _get_agent_settings(str(user.id), session)
        agent_config = user_settings.get(self.name, {})
        if not agent_config.get("enabled", True):
            raise HTTPException(
                status_code=403,
                detail=f"Agent '{self.display_name}' is not enabled. "
                "Enable it in Settings to use this feature.",
            )

    async def _get_or_key(self, user: User, session: AsyncSession) -> str:
        api_key = await get_user_inference_api_key(user, session)
        if not api_key:
            raise HTTPException(status_code=400, detail="Set your OpenRouter key in Settings")
        return api_key

    # ---- Knowledge Bases ----

    async def list_kbs(
        self,
        user: User = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
    ):
        await self._require_enabled(user, session)
        result = await session.execute(
            select(KnowledgeBase)
            .where(KnowledgeBase.user_id == user.id)
            .order_by(KnowledgeBase.created_at.desc())
        )
        kbs = result.scalars().all()
        return {
            "kbs": [
                {
                    "id": str(kb.id),
                    "name": kb.name,
                    "description": kb.description,
                    "chunk_size": kb.chunk_size,
                    "chunk_overlap": kb.chunk_overlap,
                    "embedding_model": kb.embedding_model,
                    "document_count": kb.document_count,
                    "chunk_count": kb.chunk_count,
                    "created_at": kb.created_at.isoformat() if kb.created_at else None,
                }
                for kb in kbs
            ]
        }

    async def create_kb(
        self,
        body: CreateKBRequest,
        user: User = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
    ):
        await self._require_enabled(user, session)
        kb = KnowledgeBase(
            id=uuid.uuid4(),
            user_id=user.id,
            name=body.name,
            description=body.description,
            chunk_size=body.chunk_size,
            chunk_overlap=body.chunk_overlap,
            embedding_model=body.embedding_model,
        )
        session.add(kb)
        await session.commit()
        await session.refresh(kb)
        return {"kb": self._kb_to_dict(kb)}

    async def get_kb(
        self,
        kb_id: str,
        user: User = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
    ):
        await self._require_enabled(user, session)
        kb = await self._get_kb(kb_id, user, session)
        return {"kb": self._kb_to_dict(kb)}

    async def delete_kb(
        self,
        kb_id: str,
        user: User = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
    ):
        await self._require_enabled(user, session)
        kb = await self._get_kb(kb_id, user, session)
        store = VectorStore(str(kb.id), self._get_data_dir())
        await store.delete_collection()
        await session.delete(kb)
        await session.commit()
        return {"status": "deleted"}

    # ---- Documents ----

    async def upload_document(
        self,
        kb_id: str,
        file: UploadFile = File(...),
        chunk_size: int | None = Form(None),
        chunk_overlap: int | None = Form(None),
        user: User = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
    ):
        await self._require_enabled(user, session)
        or_key = await self._get_or_key(user, session)
        kb = await self._get_kb(kb_id, user, session)

        if chunk_size is not None:
            kb.chunk_size = chunk_size
        if chunk_overlap is not None:
            kb.chunk_overlap = chunk_overlap

        filename = file.filename or "uploaded_file"
        mime_type = file.content_type or "application/octet-stream"

        doc = KnowledgeDocument(
            id=uuid.uuid4(),
            knowledge_base_id=kb.id,
            filename=filename,
            mime_type=mime_type,
            status="pending",
        )
        session.add(doc)
        await session.commit()
        await session.refresh(doc)

        file_bytes = await file.read()
        config = self._get_config()
        pipeline = IngestPipeline(str(kb.id), or_key, session, config)
        try:
            await pipeline.ingest_file(doc, file_bytes, filename)
            await session.commit()
            await session.refresh(doc)
        except Exception as e:
            doc.status = "error"
            doc.error_message = str(e)
            await session.commit()
            raise HTTPException(status_code=500, detail=f"Ingestion failed: {e}") from e

        return {"document": self._doc_to_dict(doc)}

    async def upload_text(
        self,
        kb_id: str,
        body: UploadTextRequest,
        user: User = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
    ):
        await self._require_enabled(user, session)
        or_key = await self._get_or_key(user, session)
        kb = await self._get_kb(kb_id, user, session)

        filename = body.filename or "pasted_text.txt"
        mime_type = "text/plain"

        doc = KnowledgeDocument(
            id=uuid.uuid4(),
            knowledge_base_id=kb.id,
            filename=filename,
            mime_type=mime_type,
            content=body.content,
            status="pending",
        )
        session.add(doc)
        await session.commit()
        await session.refresh(doc)

        config = self._get_config()
        pipeline = IngestPipeline(str(kb.id), or_key, session, config)
        try:
            await pipeline.ingest_document(doc, body.content)
            await session.commit()
            await session.refresh(doc)
        except Exception as e:
            doc.status = "error"
            doc.error_message = str(e)
            await session.commit()
            raise HTTPException(status_code=500, detail=f"Ingestion failed: {e}") from e

        return {"document": self._doc_to_dict(doc)}

    async def list_documents(
        self,
        kb_id: str,
        user: User = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
    ):
        await self._require_enabled(user, session)
        kb = await self._get_kb(kb_id, user, session)
        result = await session.execute(
            select(KnowledgeDocument)
            .where(KnowledgeDocument.knowledge_base_id == kb.id)
            .order_by(KnowledgeDocument.created_at.desc())
        )
        docs = result.scalars().all()
        return {"documents": [self._doc_to_dict(d) for d in docs]}

    async def get_document(
        self,
        kb_id: str,
        doc_id: str,
        user: User = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
    ):
        await self._require_enabled(user, session)
        kb = await self._get_kb(kb_id, user, session)
        result = await session.execute(
            select(KnowledgeDocument).where(
                KnowledgeDocument.knowledge_base_id == kb.id,
                KnowledgeDocument.id == doc_id,
            )
        )
        doc = result.scalar_one_or_none()
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")
        return {"document": self._doc_to_dict(doc)}

    async def delete_document(
        self,
        kb_id: str,
        doc_id: str,
        user: User = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
    ):
        await self._require_enabled(user, session)
        kb = await self._get_kb(kb_id, user, session)
        result = await session.execute(
            select(KnowledgeDocument).where(
                KnowledgeDocument.knowledge_base_id == kb.id,
                KnowledgeDocument.id == doc_id,
            )
        )
        doc = result.scalar_one_or_none()
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")

        store = VectorStore(str(kb.id), self._get_data_dir())
        await store.delete_document(str(doc.id))

        chunk_count = doc.chunk_count or 0
        kb.chunk_count = max((kb.chunk_count or 0) - chunk_count, 0)
        kb.document_count = max((kb.document_count or 1) - 1, 0)

        await session.delete(doc)
        await session.commit()
        return {"status": "deleted"}

    # ---- Query (RAG) ----

    async def query_kb(
        self,
        kb_id: str,
        body: QueryRequest,
        request: Request,
        user: User = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
    ):
        await self._require_enabled(user, session)
        kb = await self._get_kb(kb_id, user, session)
        top_k = body.top_k or 5

        client = await get_user_llm_client(user, session, request.app.state.config)

        async def generate_sse():
            try:
                question_embedding = await client.get_embedding(
                    body.question, model=kb.embedding_model
                )

                store = VectorStore(str(kb.id), self._get_data_dir())
                results = await store.query(question_embedding, top_k=top_k)

                if not results:
                    no_docs_msg = (
                        "No documents ingested yet. "
                        "Add documents to this knowledge base first."
                    )
                    yield f"event: error\ndata: {json.dumps({'message': no_docs_msg})}\n\n"
                    return

                context_parts = []
                sources = []
                for r in results:
                    filename = r.get("metadata", {}).get("filename", "unknown")
                    chunk_idx = r["metadata"].get("chunk_index", "?")
                    context_parts.append(
                        f"[Source: {filename}, Chunk {chunk_idx}]\n{r['text']}"
                    )
                    sources.append({
                        "doc_id": r["metadata"].get("doc_id", ""),
                        "filename": filename,
                        "chunk_index": r["metadata"].get("chunk_index", 0),
                        "text": r["text"][:500],
                        "score": r.get("score", 0),
                    })

                context_text = "\n\n---\n\n".join(context_parts)

                system_prompt = (
                    "You are a helpful research assistant. Answer the user's question "
                    "based on the provided document excerpts. If the answer cannot be "
                    "found in the excerpts, say so clearly. Cite specific sources "
                    "when possible.\n\n"
                    f"DOCUMENT EXCERPTS:\n{context_text}"
                )

                messages = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": body.question},
                ]

                async for chunk in self._stream_chat_response(client, messages):
                    yield chunk

                yield f"event: sources\ndata: {json.dumps({'sources': sources})}\n\n"
                yield "event: done\ndata: {}\n\n"
            except asyncio.CancelledError:
                yield 'event: error\ndata: {"message": "Client disconnected"}\n\n'
            except Exception:
                logger.exception("Knowledge base query error")
                yield 'event: error\ndata: {"message": "An internal error occurred"}\n\n'
            finally:
                await client.close()

        return StreamingResponse(
            generate_sse(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    # ---- Ingestion Progress ----

    async def ingestion_progress(
        self,
        kb_id: str,
        user: User = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
    ):
        await self._require_enabled(user, session)
        await self._get_kb(kb_id, user, session)
        progress = get_ingestion_progress(kb_id)
        if progress is None:
            return {"active": False, "processed": 0, "total": 0}
        return {"active": True, "processed": progress[0], "total": progress[1]}

    # ---- Chunks ----

    async def list_chunks(
        self,
        kb_id: str,
        doc_id: str,
        user: User = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
    ):
        await self._require_enabled(user, session)
        kb = await self._get_kb(kb_id, user, session)
        result = await session.execute(
            select(KnowledgeDocument).where(
                KnowledgeDocument.knowledge_base_id == kb.id,
                KnowledgeDocument.id == doc_id,
            )
        )
        doc = result.scalar_one_or_none()
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")

        store = VectorStore(str(kb.id), self._get_data_dir())
        try:

            def _get_chunks():
                coll = store._get_or_create_collection()
                return coll.get(
                    where={"doc_id": doc_id},
                    include=["documents", "metadatas", "embeddings"],
                )

            results = await asyncio.to_thread(_get_chunks)
            chunks = []
            if results.get("ids"):
                for i in range(len(results["ids"])):
                    meta = results.get("metadatas", [{}])
                    emb = results.get("embeddings", [[]])
                    chunks.append({
                        "id": results["ids"][i],
                        "text": results.get("documents", [""])[i],
                        "chunk_index": (meta[i].get("chunk_index", i)
                                        if meta else i),
                        "embedding_dim": (len(emb[i]) if emb else 0),
                    })
            return {"chunks": chunks, "count": len(chunks)}
        except Exception:
            return {"chunks": [], "count": 0}

    # ---- Helpers ----

    async def _get_kb(self, kb_id: str, user: User, session: AsyncSession) -> KnowledgeBase:
        result = await session.execute(
            select(KnowledgeBase).where(
                KnowledgeBase.id == kb_id, KnowledgeBase.user_id == user.id
            )
        )
        kb = result.scalar_one_or_none()
        if not kb:
            raise HTTPException(status_code=404, detail="Knowledge base not found")
        return kb

    @staticmethod
    def _get_data_dir() -> str:
        from workbench.core.config import load_config
        return load_config().data_dir

    @staticmethod
    def _get_config():
        from workbench.core.config import load_config
        return load_config()

    @staticmethod
    def _kb_to_dict(kb: KnowledgeBase) -> dict:
        return {
            "id": str(kb.id),
            "name": kb.name,
            "description": kb.description,
            "chunk_size": kb.chunk_size,
            "chunk_overlap": kb.chunk_overlap,
            "embedding_model": kb.embedding_model,
            "document_count": kb.document_count,
            "chunk_count": kb.chunk_count,
            "created_at": kb.created_at.isoformat() if kb.created_at else None,
        }

    @staticmethod
    def _doc_to_dict(doc: KnowledgeDocument) -> dict:
        return {
            "id": str(doc.id),
            "knowledge_base_id": str(doc.knowledge_base_id),
            "filename": doc.filename,
            "mime_type": doc.mime_type,
            "chunk_count": doc.chunk_count,
            "status": doc.status,
            "error_message": doc.error_message,
            "created_at": doc.created_at.isoformat() if doc.created_at else None,
        }

    async def _stream_chat_response(self, client, messages):
        _SENTINEL = "__STREAM_DONE__"
        queue: asyncio.Queue[str] = asyncio.Queue()

        async def stream_to_queue():
            try:
                async for chunk in client.chat_completion_stream(
                    messages=messages,
                    temperature=0.3,
                ):
                    await queue.put(
                        f"event: chunk\ndata: {json.dumps({'content': chunk})}\n\n"
                    )
                await queue.put(_SENTINEL)
            except Exception as e:
                await queue.put(str(e))
                await queue.put(_SENTINEL)

        task = asyncio.create_task(stream_to_queue())

        try:
            while True:
                item = await queue.get()
                if item == _SENTINEL:
                    break
                yield item
        finally:
            if not task.done():
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await task


# ---- Request Models ----

class CreateKBRequest(BaseModel):
    name: str = Field(..., max_length=200)
    description: str | None = None
    chunk_size: int = Field(default=1000, ge=200, le=8000)
    chunk_overlap: int = Field(default=200, ge=0, le=2000)
    embedding_model: str = Field(default="openai/text-embedding-3-small", max_length=100)


class UploadTextRequest(BaseModel):
    content: str = Field(..., max_length=10_000_000)
    filename: str | None = None


class QueryRequest(BaseModel):
    question: str = Field(..., max_length=10000)
    top_k: int | None = None
