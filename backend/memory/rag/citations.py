"""Citation formatting and untrusted-context boundaries."""

from __future__ import annotations


def build_citations(results: list[dict[str, object]]) -> list[dict[str, object]]:
    citations = []
    for index, result in enumerate(results, start=1):
        metadata = result.get("metadata", {}) or {}
        citations.append({
            "citation_id": f"S{index}",
            "source_id": metadata.get("source_id"),
            "filename": metadata.get("filename"),
            "document_type": metadata.get("document_type"),
            "chunk_index": metadata.get("chunk_index"),
            "score": result.get("score"),
        })
    return citations


def build_cited_context(results: list[dict[str, object]]) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    citations = build_citations(results)
    context = []
    for citation, result in zip(citations, results):
        # Delimit retrieved text as untrusted data; it must not override system
        # instructions or authorize tools.
        context.append({
            "text": f"[{citation['citation_id']}] <retrieved_untrusted_data> {str(result.get('text', ''))} </retrieved_untrusted_data>",
            "citation_id": citation["citation_id"],
        })
    return context, citations
