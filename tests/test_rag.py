import asyncio
import json

from backend.memory.rag import DocumentIngestor, QueryRewriter, RAGRetriever, RAGStore, build_cited_context


def test_document_ingestion_retrieval_isolated_and_cited(tmp_path):
    async def run():
        store = RAGStore(path=str(tmp_path / "chroma"))
        ingestor = DocumentIngestor(store=store, chunk_size=80, chunk_overlap=10)
        private = await ingestor.ingest(
            b"The private project codename is Aurora.",
            filename="private.md",
            user_id="user-a",
            tenant_id="tenant-1",
            access_policy="private",
        )
        shared = await ingestor.ingest(
            b"The tenant onboarding window is Monday at nine.",
            filename="onboarding.txt",
            user_id="user-a",
            tenant_id="tenant-1",
            access_policy="tenant",
        )
        retriever = RAGRetriever(store=store)
        own = await retriever.retrieve("What is the project codename?", user_id="user-a", tenant_id="tenant-1")
        assert own["citations"]
        assert own["citations"][0]["source_id"] in {private["source_id"], shared["source_id"]}
        assert "<retrieved_untrusted_data>" in own["context"][0]["text"]

        other = await retriever.retrieve("What is the project codename?", user_id="user-b", tenant_id="tenant-1")
        assert all(item["metadata"].get("source_id") != private["source_id"] for item in other["results"])
        assert any(item["metadata"].get("source_id") == shared["source_id"] for item in other["results"])

        wrong_tenant = await retriever.retrieve("What is the project codename?", user_id="user-a", tenant_id="tenant-2")
        assert wrong_tenant["results"] == []

    asyncio.run(run())


def test_query_rewriter_only_rewrites_references_and_is_bounded():
    async def run():
        rewriter = QueryRewriter()
        assert await rewriter.rewrite("What is the capital of France?", []) == "What is the capital of France?"
        rewritten = await rewriter.rewrite("What does it say?", [{"role": "user", "content": "The deployment guide is here."}])
        assert "deployment guide" in rewritten
        assert len(rewritten) <= 1_000

    asyncio.run(run())


def test_citation_builder_preserves_source_metadata():
    context, citations = build_cited_context([{
        "text": "untrusted text",
        "score": 0.9,
        "metadata": {"source_id": "source-1", "filename": "guide.md", "chunk_index": 0},
    }])
    assert citations[0]["citation_id"] == "S1"
    assert citations[0]["filename"] == "guide.md"
    assert "S1" in context[0]["text"]
