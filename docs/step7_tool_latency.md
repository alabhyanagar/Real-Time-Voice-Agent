# Step 7: Tool execution latency and safety

Tool calls now execute through a policy-aware LangGraph node.

- Each registered tool emits `requested`, `running`, `completed`, or `failed` status events.
- Every tool call is bounded by its `ToolDefinition.timeout_seconds` value.
- The graph enforces `MAX_TOOL_CALLS_PER_TURN`.
- Tools marked `requires_confirmation=True` produce a `tool_confirmation` event and are not executed.
- The orchestrator starts cancellable filler audio when a tool is requested and stops it when the tool finishes, fails, or the user barges in.
- Cancelling the response task propagates through tool execution and stops the filler task.

The current filler uses the configured TTS service for “Let me check that.” A later latency pass can replace it with pre-rendered PCM. The starter calculator and clock tools remain non-sensitive; external sensors, databases, and mutations should be registered with explicit confirmation policies.
