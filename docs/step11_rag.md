# Step 11 — ChromaDB RAG and citations

Step 11 adds tenant-aware document retrieval without allowing retrieved text to
override system instructions or authorize tools.

## Components

- `backend/memory/rag/ingestion.py`
  - UTF-8 text, Markdown, JSON, CSV, and HTML extraction.
  - Optional PDF extraction through `pypdf`.
  - Null/whitespace normalization and bounded overlapping chunks.
  - Metadata on every chunk: user ID, tenant ID, source ID, document type,
    upload timestamp, filename, chunk index, and access policy.
- `backend/memory/rag/retriever.py`
  - Persistent ChromaDB collection with hashed deterministic embeddings.
  - A JSON-backed local fallback for Python runtimes without a compatible
    Chroma/onnxruntime wheel.
  - User and tenant ACL filters; `private` documents are user-only and `tenant`
    documents are available to users in the same tenant.
  - Bounded top-k retrieval and cosine reranking.
- `backend/memory/rag/query_rewriter.py`
  - Rewrites only reference-bearing queries such as “it”, “that”, “above”, or
    “the previous document”.
  - Optional async fast-model callback; deterministic bounded fallback otherwise.
- `backend/memory/rag/citations.py`
  - Stable `[S1]` citation IDs and source metadata.
  - `<retrieved_untrusted_data>` delimiters for prompt injection boundaries.

## API

Authenticated routes are mounted under `/api/v1/rag`:

- `POST /documents` — index a text document with metadata and ACL policy.
- `POST /query` — retrieve authorized chunks and citations.
- `DELETE /documents/{source_id}` — delete the authenticated user's source.

The authenticated JWT supplies `user_id` and `tenant_id` (`tenant_id`, `tid`, or
the user ID fallback). Those values are never accepted from request bodies.

## Live voice integration

Each final user transcript is retrieved against the user's tenant before the
LLM call. The LangGraph system prompt labels results as untrusted reference
data, and the gateway emits a citations UI card plus `rag_retrieval_ms` and
result-count telemetry. Retrieved context is not written into short-term
conversation memory.

## Verification

`tests/test_rag.py` covers ingestion, chunking, private/tenant isolation,
wrong-tenant rejection, reference-only rewriting, bounded output, and citation
metadata. ChromaDB is used automatically when available; the fallback keeps
tests and Python 3.15 development functional until its native dependency has a
compatible wheel.
