import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agents.knowledge.chunker import TextChunker, extract_text_from_pdf
from agents.knowledge.models import KnowledgeBase, KnowledgeDocument
from agents.knowledge.vector_store import VectorStore
from workbench.core.config import WorkbenchConfig
from workbench.core.router import OpenRouterClient

logger = logging.getLogger(__name__)

_progress: dict[str, tuple[int, int]] = {}


def get_ingestion_progress(kb_id: str) -> tuple[int, int] | None:
    return _progress.get(kb_id)


class IngestPipeline:
    """Orchestrates document ingestion: chunk → embed → store."""

    def __init__(
        self,
        kb_id: str,
        or_api_key: str,
        session: AsyncSession,
        config: WorkbenchConfig,
    ) -> None:
        self._kb_id = kb_id
        self._api_key = or_api_key
        self._session = session
        self._config = config

    async def ingest_document(self, doc: KnowledgeDocument, content: str) -> None:
        kb = await self._get_kb()
        if kb is None:
            raise ValueError(f"Knowledge base {self._kb_id} not found")

        await self._set_doc_status(doc, "processing")
        chunker = TextChunker()
        chunks = chunker.chunk(content, kb.chunk_size, kb.chunk_overlap)
        await self._set_doc_chunk_count(doc, len(chunks))

        if not chunks:
            await self._finish_doc(doc, kb, 0)
            return

        _progress[self._kb_id] = (0, len(chunks))

        try:
            client = OpenRouterClient(api_key=self._api_key)
            try:
                embeddings = await client.get_embeddings_batch(
                    chunks, model=kb.embedding_model, concurrency=8
                )
            finally:
                await client.close()

            metadata = [
                {
                    "doc_id": str(doc.id),
                    "kb_id": str(kb.id),
                    "filename": doc.filename,
                    "chunk_index": i,
                }
                for i in range(len(chunks))
            ]

            store = VectorStore(str(kb.id), self._config.data_dir)
            stored = await store.add_documents(
                str(doc.id), chunks, embeddings, metadata
            )

            _progress[self._kb_id] = (stored, len(chunks))
            await self._finish_doc(doc, kb, stored)
        except Exception:
            logger.exception("Ingestion failed for document %s", doc.id)
            await self._fail_doc(doc, kb)
            _progress.pop(self._kb_id, None)
            raise

    async def ingest_file(self, doc: KnowledgeDocument, file_bytes: bytes, filename: str) -> None:
        if filename.lower().endswith(".pdf"):
            content = extract_text_from_pdf(file_bytes)
        else:
            content = file_bytes.decode("utf-8", errors="replace")
        await self.ingest_document(doc, content)

    async def _get_kb(self) -> KnowledgeBase | None:
        result = await self._session.execute(
            select(KnowledgeBase).where(KnowledgeBase.id == self._kb_id)
        )
        return result.scalar_one_or_none()

    async def _set_doc_status(self, doc: KnowledgeDocument, status: str) -> None:
        doc.status = status
        await self._session.flush()

    async def _set_doc_chunk_count(self, doc: KnowledgeDocument, count: int) -> None:
        doc.chunk_count = count
        await self._session.flush()

    async def _finish_doc(
        self, doc: KnowledgeDocument, kb: KnowledgeBase, chunk_count: int
    ) -> None:
        doc.status = "ready"
        doc.chunk_count = chunk_count
        kb.document_count = (kb.document_count or 0) + 1
        kb.chunk_count = (kb.chunk_count or 0) + chunk_count
        await self._session.flush()
        _progress.pop(self._kb_id, None)

    async def _fail_doc(self, doc: KnowledgeDocument, kb: KnowledgeBase) -> None:
        doc.status = "error"
        await self._session.flush()
        _progress.pop(self._kb_id, None)
