import asyncio

from backend.memory.memory_policy import MemoryPolicy
from backend.memory.redis_window import RedisMemoryWindow


def test_memory_survives_reconnect_is_bounded_and_summarizes_old_turns():
    async def run():
        memory = RedisMemoryWindow(policy=MemoryPolicy(max_turns=3, max_tokens=128, ttl_seconds=60, summary_max_chars=200))
        for index in range(5):
            await memory.append_turn(
                "user-1",
                "session-reconnect",
                role="user" if index % 2 == 0 else "assistant",
                content=f"message-{index} " + ("context " * 12),
                turn_id=f"turn-{index}",
            )
        recovered = await memory.load("user-1", "session-reconnect")
        assert len(recovered.messages) <= 3
        assert recovered.summary
        exported = await memory.export_session("user-1", "session-reconnect")
        assert exported["session_id"] == "session-reconnect"
        assert len(exported["messages"]) <= 3

    asyncio.run(run())


def test_memory_isolated_by_user_and_supports_state_cancellation_and_delete():
    async def run():
        memory = RedisMemoryWindow(policy=MemoryPolicy(max_turns=15, max_tokens=128, ttl_seconds=60, summary_max_chars=200))
        await memory.append_turn("user-a", "shared-session", role="user", content="private A", turn_id="turn-a")
        await memory.append_turn("user-b", "shared-session", role="user", content="private B", turn_id="turn-b")
        assert (await memory.load("user-a", "shared-session")).messages[0]["content"] == "private A"
        assert (await memory.load("user-b", "shared-session")).messages[0]["content"] == "private B"

        await memory.set_session_state("user-a", "shared-session", state="speaking", generation_id="generation-a")
        await memory.cancel_generation("user-a", "shared-session", "generation-a")
        state = await memory.load("user-a", "shared-session")
        assert state.state == "speaking"
        assert await memory.is_cancelled("user-a", "shared-session", "generation-a") is True
        assert await memory.is_cancelled("user-a", "shared-session", "generation-other") is False

        exported = await memory.export_user("user-a")
        assert [item["session_id"] for item in exported["sessions"]] == ["shared-session"]
        await memory.delete_session("user-a", "shared-session")
        assert (await memory.load("user-a", "shared-session")).messages == []
        assert (await memory.export_user("user-a"))["sessions"] == []

    asyncio.run(run())


def test_memory_rejects_unsafe_identity():
    async def run():
        memory = RedisMemoryWindow()
        try:
            await memory.load("user\nother", "session")
        except ValueError as exc:
            assert "identity" in str(exc)
        else:
            raise AssertionError("unsafe user identity must be rejected")

    asyncio.run(run())
