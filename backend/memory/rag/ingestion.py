"""Safe document extraction, normalization, chunking, and indexing."""

from __future__ import annotations

import hashlib
import html
import json
import re
from datetime import datetime, timezone
from html.parser import HTMLParser

from backend.core.config import settings

from .retriever import RAGStore


class IngestionError(ValueError):
    """Raised when a document cannot be safely indexed."""


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)

    def text(self) -> str:
        return " ".join(self.parts)


def normalize_text(text: str) -> str:
    text = text.replace("\x00", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _extract(raw: bytes, filename: str, content_type: str | None) -> tuple[str, str]:
    suffix = filename.lower().rsplit(".", 1)[-1] if "." in filename else "txt"
    document_type = content_type or suffix
    if suffix == "pdf" or content_type == "application/pdf":
        try:
            from pypdf import PdfReader
            import io

            text = "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(raw)).pages)
        except ImportError as exc:
            raise IngestionError("PDF ingestion requires the optional pypdf dependency") from exc
        except Exception as exc:
            raise IngestionError("PDF text extraction failed") from exc
    else:
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise IngestionError("Only UTF-8 text documents are supported") from exc
        if suffix in {"html", "htm"} or content_type == "text/html":
            parser = _TextExtractor()
            parser.feed(text)
            text = html.unescape(parser.text())
        elif suffix == "json" or content_type == "application/json":
            try:
                text = json.dumps(json.loads(text), ensure_ascii=False, indent=2)
            except json.JSONDecodeError as exc:
                raise IngestionError("JSON document is invalid") from exc
    text = normalize_text(text)
    if not text:
        raise IngestionError("Document contains no indexable text")
    return text, document_type


def chunk_text(text: str, *, size: int = 900, overlap: int = 120) -> list[str]:
    if size <= 0 or overlap < 0 or overlap >= size:
        raise ValueError("Chunk size and overlap are invalid")
    chunks = []
    start = 0
    while start < len(text):
        end = min(len(text), start + size)
        if end < len(text):
            boundary = text.rfind(" ", start, end)
            if boundary > start + size // 2:
                end = boundary
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return chunks


class DocumentIngestor:
    def __init__(self, store: RAGStore | None = None, *, chunk_size: int | None = None, chunk_overlap: int | None = None):
        self.store = store or RAGStore()
        self.chunk_size = chunk_size or settings.RAG_CHUNK_SIZE
        self.chunk_overlap = settings.RAG_CHUNK_OVERLAP if chunk_overlap is None else chunk_overlap

    async def ingest(
        self,
        raw: bytes,
        *,
        filename: str,
        user_id: str,
        tenant_id: str,
        source_id: str | None = None,
        content_type: str | None = None,
        access_policy: str = "private",
    ) -> dict[str, object]:
        if not raw or len(raw) > self.store.max_document_bytes:
            raise IngestionError("Document is empty or exceeds the configured size limit")
        if not filename or len(filename) > 240 or any(ord(char) < 32 for char in filename):
            raise IngestionError("Document filename is invalid")
        if access_policy not in {"private", "tenant"}:
            raise IngestionError("Unsupported document access policy")
        text, document_type = _extract(raw, filename, content_type)
        source_id = source_id or hashlib.sha256((user_id + ":" + filename + ":" + text).encode()).hexdigest()[:32]
        if len(source_id) > 128 or not re.fullmatch(r"[A-Za-z0-9._:-]+", source_id):
            raise IngestionError("Source ID is invalid")
        chunks = chunk_text(text, size=self.chunk_size, overlap=self.chunk_overlap)
        uploaded_at = datetime.now(timezone.utc).isoformat()
        records = [
            {
                "id": f"{source_id}:{index}",
                "text": chunk,
                "metadata": {
                    "user_id": user_id,
                    "tenant_id": tenant_id,
                    "source_id": source_id,
                    "filename": filename,
                    "document_type": document_type,
                    "uploaded_at": uploaded_at,
                    "access_policy": access_policy,
                    "chunk_index": index,
                },
            }
            for index, chunk in enumerate(chunks)
        ]
        await self.store.upsert(records)
        return {"source_id": source_id, "filename": filename, "document_type": document_type, "chunks": len(records), "uploaded_at": uploaded_at}
