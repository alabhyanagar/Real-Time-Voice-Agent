# Step 8 — Tool-Free LangGraph Conversational Agent

Step 8 introduces the structured LangGraph boundary used by the realtime voice
pipeline. The graph is intentionally tool-free; concrete tool selection and
approval behavior remains the Step 9 checkpoint.

## Graph

```text
START
  ↓
load_context
  ↓
call_model
  ↓
stream_response
  ↓
finalize_turn
  ↓
END
```

The implementation is split into the planned modules:

- `backend/agent/state.py` — raw structured state and identity fields.
- `backend/agent/nodes.py` — context normalization, provider message conversion,
  and turn finalization.
- `backend/agent/routing.py` — named stage routing helpers.
- `backend/agent/prompts.py` — provider-neutral spoken response prompt.
- `backend/agent/policies.py` — bounded conversation input policy.
- `backend/agent/graph.py` — compiled LangGraph plus cancellation-aware token
  streaming runner.

## Runtime behavior

`LLMService` now uses `backend.agent.VoiceAgentGraph`. Provider-specific models
are still created through the Step 6 factory. Each streamed token is yielded to
the existing orchestrator, which forwards it to sentence-level TTS. Cancelling
the orchestrator task cancels provider streaming and records a `CANCELLED`
error in the graph state.

The graph preserves placeholders for tool calls, tool results, and approval
state so later tool work can extend the state without changing the session
protocol. No tool is bound or executed in this step.

## Verification

- Provider-free streaming test covers chunk ordering and identity propagation.
- Compiled graph test covers finalization and verifies tool collections remain
  empty.
- The full project suite passes with `python -m pytest -q` (15 tests).
