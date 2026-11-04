# Step 6: Structured tools and LangGraph routing

The agent now has an explicit tool allow-list and a LangGraph tool loop.

## Registered starter tools

- `calculate(operation, left, right)` performs add, subtract, multiply, or divide with division-by-zero handling.
- `get_current_time(timezone_name)` returns an ISO timestamp for an IANA timezone.

Both tools use LangChain structured schemas generated from typed function signatures. No arbitrary Python execution, shell access, network access, or database mutation is exposed.

## Routing

`ToolRegistry` owns the allow-list and policy metadata. `VoiceAgentGraph` binds the registered tools to the selected chat model, routes tool calls to LangGraph’s `ToolNode`, and returns tool results to the model for the final response. Tool calls are bounded by `MAX_TOOL_CALLS_PER_TURN` through the graph recursion limit.

The registry is the extension point for ESP32 sensors, MERN APIs, and other project tools. Those tools should be added only with explicit input schemas, timeouts, authorization policy, and confirmation requirements where needed.

Tool-enabled turns currently complete the graph loop before yielding the final response. The existing direct model stream remains available for a no-tool graph; latency filler audio and parallel tool execution are planned for the tool latency step.
