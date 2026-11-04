"""Authenticated document ingestion and retrieval endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from backend.core.security import authenticate_http
from backend.memory.rag import DocumentIngestor, IngestionError, get_default_retriever

router = APIRouter(prefix="/rag", tags=["rag"])


class DocumentUpload(BaseModel):
    filename: str = Field(min_length=1, max_length=240)
    text: str = Field(min_length=1)
    content_type: str | None = None
    source_id: str | None = Field(default=None, max_length=128)
    access_policy: str = "private"


class RetrievalQuery(BaseModel):
    query: str = Field(min_length=1, max_length=2_000)
    top_k: int = Field(default=5, ge=1, le=20)


def _claims(request: Request) -> dict:
    claims = authenticate_http(request)
    if not claims or not claims.get("sub"):
        raise HTTPException(status_code=401, detail="Authentication required")
    return claims


def _tenant(claims: dict) -> str:
    return str(claims.get("tenant_id", claims.get("tid", claims["sub"])))


@router.post("/documents")
async def upload_document(request: Request, document: DocumentUpload):
    claims = _claims(request)
    retriever = get_default_retriever()
    try:
        result = await DocumentIngestor(store=retriever.store).ingest(
            document.text.encode("utf-8"),
            filename=document.filename,
            content_type=document.content_type,
            source_id=document.source_id,
            user_id=str(claims["sub"]),
            tenant_id=_tenant(claims),
            access_policy=document.access_policy,
        )
        return result
    except IngestionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/query")
async def query_documents(request: Request, query: RetrievalQuery):
    claims = _claims(request)
    try:
        return await get_default_retriever().retrieve(
            query.query,
            user_id=str(claims["sub"]),
            tenant_id=_tenant(claims),
            top_k=query.top_k,
        )
    except (ValueError, IngestionError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/documents/{source_id}")
async def delete_document(request: Request, source_id: str):
    claims = _claims(request)
    if not source_id or len(source_id) > 128:
        raise HTTPException(status_code=400, detail="Invalid source ID")
    await get_default_retriever().store.delete_source(
        user_id=str(claims["sub"]), tenant_id=_tenant(claims), source_id=source_id,
    )
    return {"deleted": True, "source_id": source_id}
