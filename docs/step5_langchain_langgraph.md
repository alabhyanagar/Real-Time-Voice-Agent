# Step 5: LangChain providers and LangGraph boundary

The LLM path now uses LangChain’s common chat model interface. Provider selection comes from `LLM_PROVIDER` and model selection from `LLM_MODEL`, with provider defaults for Groq, Gemini, Anthropic, and local OpenAI-compatible servers.

- `backend/llm/providers.py` lazily constructs the selected provider adapter.
- `backend/llm/graph.py` compiles a response graph with an explicit node for future tools, memory, confirmation interrupts, and retrieval.
- `backend/services/llm_service.py` uses LangChain messages and streams provider-neutral text chunks through the graph-owned model boundary to TTS.
- Missing cloud credentials produce a spoken configuration message instead of crashing WebSocket startup.

Tool routing, Redis checkpoints, and RAG nodes are later graph additions.
