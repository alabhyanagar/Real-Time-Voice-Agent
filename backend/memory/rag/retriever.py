"""ChromaDB adapter with a persistent local fallback for unsupported runtimes."""

from __future__ import annotations

import json
import math
import threading
from pathlib import Path
from typing import Any

from backend.core.config import settings

from .citations import build_cited_context
from .query_rewriter import QueryRewriter


class RetrievalError(ValueError):
    """Raised when retrieval cannot safely be completed."""


def _embedding(text: str, dimensions: int = 64) -> list[float]:
    values = [0.0] * dimensions
    for token in text.lower().split():
        index = int.from_bytes(__import__("hashlib").sha256(token.encode()).digest()[:4], "big") % dimensions
        values[index] += 1.0
    norm = math.sqrt(sum(value * value for value in values)) or 1.0
    return [value / norm for value in values]


def _cosine(left: list[float], right: list[float]) -> float:
    return sum(a * b for a, b in zip(left, right))


class RAGStore:
    def __init__(self, *, path: str | None = None, collection_name: str = "voice_agent_documents", max_document_bytes: int | None = None):
        self.path = Path(path or settings.CHROMA_PATH)
        self.collection_name = collection_name
        self.max_document_bytes = max_document_bytes or settings.RAG_MAX_DOCUMENT_BYTES
        self._lock = threading.RLock()
        self._chroma = None
        self._fallback_path = self.path / "rag_fallback.json"
        try:
            import chromadb
            self.path.mkdir(parents=True, exist_ok=True)
            self._chroma = chromadb.PersistentClient(path=str(self.path))
            self.collection = self._chroma.get_or_create_collection(name=collection_name, metadata={"hnsw:space": "cosine"})
        except Exception:
            self.collection = None
            self.path.mkdir(parents=True, exist_ok=True)

    def _fallback_records(self) -> list[dict[str, object]]:
        if not self._fallback_path.exists():
            return []
        try:
            value = json.loads(self._fallback_path.read_text(encoding="utf-8"))
            return value if isinstance(value, list) else []
        except (OSError, ValueError):
            return []

    def _write_fallback(self, records: list[dict[str, object]]) -> None:
        temporary = self._fallback_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(records, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        temporary.replace(self._fallback_path)

    async def upsert(self, records: list[dict[str, object]]) -> None:
        if not records:
            return
        if self.collection is not None:
            self.collection.upsert(
                ids=[str(record["id"]) for record in records],
                documents=[str(record["text"]) for record in records],
                metadatas=[record["metadata"] for record in records],
                embeddings=[_embedding(str(record["text"])) for record in records],
            )
            return
        with self._lock:
            existing = [record for record in self._fallback_records() if record.get("id") not in {item["id"] for item in records}]
            self._write_fallback(existing + [{**record, "embedding": _embedding(str(record["text"]))} for record in records])

    async def delete_source(self, *, user_id: str, tenant_id: str, source_id: str) -> None:
        if self.collection is not None:
            self.collection.delete(where={"$and": [{"user_id": user_id}, {"tenant_id": tenant_id}, {"source_id": source_id}]})
            return
        with self._lock:
            keep = [record for record in self._fallback_records() if not (record.get("metadata", {}).get("user_id") == user_id and record.get("metadata", {}).get("tenant_id") == tenant_id and record.get("metadata", {}).get("source_id") == source_id)]
            self._write_fallback(keep)

    async def query(self, *, user_id: str, tenant_id: str, query: str, top_k: int = 5) -> list[dict[str, object]]:
        if not query.strip() or top_k <= 0:
            return []
        top_k = min(top_k, 20)
        if self.collection is not None:
            result = self.collection.query(
                query_embeddings=[_embedding(query)],
                n_results=top_k,
                where={"$and": [{"tenant_id": tenant_id}, {"$or": [{"user_id": user_id}, {"access_policy": "tenant"}]}]},
            )
            documents = (result.get("documents") or [[]])[0]
            metadatas = (result.get("metadatas") or [[]])[0]
            distances = (result.get("distances") or [[]])[0]
            return [{"text": text, "metadata": metadata or {}, "score": 1.0 - float(distance)} for text, metadata, distance in zip(documents, metadatas, distances)]
        with self._lock:
            records = [
                record for record in self._fallback_records()
                if record.get("metadata", {}).get("tenant_id") == tenant_id
                and (
                    record.get("metadata", {}).get("user_id") == user_id
                    or record.get("metadata", {}).get("access_policy") == "tenant"
                )
            ]
        query_vector = _embedding(query)
        ranked = sorted((({**record, "score": _cosine(query_vector, record.get("embedding", _embedding(str(record.get("text", "")))))} for record in records)), key=lambda item: float(item["score"]), reverse=True)
        return [{"text": record.get("text", ""), "metadata": record.get("metadata", {}), "score": record.get("score", 0.0)} for record in ranked[:top_k]]


class RAGRetriever:
    def __init__(self, store: RAGStore | None = None, rewriter: QueryRewriter | None = None):
        self.store = store or RAGStore()
        self.rewriter = rewriter or QueryRewriter()

    async def retrieve(self, query: str, *, user_id: str, tenant_id: str, conversation: list[dict[str, str]] | None = None, top_k: int = 5) -> dict[str, object]:
        rewritten = await self.rewriter.rewrite(query, conversation)
        results = await self.store.query(user_id=user_id, tenant_id=tenant_id, query=rewritten, top_k=top_k)
        context, citations = build_cited_context(results)
        return {"query": query, "rewritten_query": rewritten, "results": results, "context": context, "citations": citations}


_default_retriever: RAGRetriever | None = None


def get_default_retriever() -> RAGRetriever:
    global _default_retriever
    if _default_retriever is None:
        _default_retriever = RAGRetriever()
    return _default_retriever
