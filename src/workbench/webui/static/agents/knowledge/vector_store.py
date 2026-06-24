import asyncio
import logging
import threading
from pathlib import Path
from typing import ClassVar

import chromadb
from chromadb.config import Settings as ChromaSettings

logger = logging.getLogger(__name__)


class VectorStore:
    """Async-safe ChromaDB wrapper for a single knowledge base.

    All ChromaDB operations run in a thread pool because the ChromaDB
    client is synchronous.
    """

    _client_lock = threading.Lock()
    _clients: ClassVar[dict[str, chromadb.PersistentClient]] = {}

    def __init__(self, kb_id: str, data_dir: str) -> None:
        self._kb_id = kb_id
        self._collection_name = f"kb_{kb_id}"
        store_path = str(Path(data_dir) / "knowledge" / kb_id / "chroma")
        Path(store_path).mkdir(parents=True, exist_ok=True)

        with self._client_lock:
            key = store_path
            if key not in self._clients:
                self._clients[key] = chromadb.PersistentClient(
                    path=store_path,
                    settings=ChromaSettings(anonymized_telemetry=False),
                )
            self._client = self._clients[key]

    def _get_or_create_collection(self):
        return self._client.get_or_create_collection(name=self._collection_name)

    async def add_documents(
        self,
        doc_id: str,
        chunks: list[str],
        embeddings: list[list[float]],
        metadata: list[dict],
    ) -> int:
        if not chunks:
            return 0

        ids = [f"{doc_id}_{i}" for i in range(len(chunks))]

        def _add():
            collection = self._get_or_create_collection()
            collection.add(
                ids=ids,
                documents=chunks,
                embeddings=embeddings,
                metadatas=metadata,
            )

        await asyncio.to_thread(_add)
        logger.info("Added %d chunks to collection %s", len(chunks), self._collection_name)
        return len(chunks)

    async def query(
        self, query_embedding: list[float], top_k: int = 5
    ) -> list[dict]:
        if top_k < 1:
            return []

        def _query():
            collection = self._get_or_create_collection()
            results = collection.query(
                query_embeddings=[query_embedding],
                n_results=min(top_k, self._count()),
            )
            outs: list[dict] = []
            if not results.get("ids") or not results["ids"][0]:
                return outs
            for i in range(len(results["ids"][0])):
                outs.append({
                    "id": results["ids"][0][i],
                    "text": results.get("documents", [[""]])[0][i],
                    "metadata": results.get("metadatas", [[{}]])[0][i],
                    "score": results.get("distances", [[1.0]])[0][i],
                })
            return outs

        return await asyncio.to_thread(_query)

    async def delete_document(self, doc_id: str) -> None:
        def _delete():
            collection = self._get_or_create_collection()
            try:
                results = collection.get(
                    where={"doc_id": doc_id},
                    include=[],
                )
                if results.get("ids"):
                    collection.delete(ids=results["ids"])
                    logger.info(
                        "Deleted %d chunks for doc %s in %s",
                        len(results["ids"]), doc_id, self._collection_name,
                    )
            except Exception:
                logger.exception("Error deleting doc %s from vector store", doc_id)

        await asyncio.to_thread(_delete)

    async def delete_collection(self) -> None:
        def _delete():
            try:
                self._client.delete_collection(name=self._collection_name)
                logger.info("Deleted collection %s", self._collection_name)
            except Exception:
                logger.debug("Collection %s already deleted or not found", self._collection_name)

        await asyncio.to_thread(_delete)

    async def count(self) -> int:
        def _count():
            return self._count()

        return await asyncio.to_thread(_count)

    def _count(self) -> int:
        try:
            collection = self._get_or_create_collection()
            return collection.count()
        except Exception:
            return 0
