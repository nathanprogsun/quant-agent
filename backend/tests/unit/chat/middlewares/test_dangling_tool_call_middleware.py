"""Tests for ``DanglingToolCallMiddleware``.

Ports ``deerflow.tests.test_dangling_tool_call_middleware`` ≥ 30 cases.
Adapts to quant-agent's custom ``AgentMiddleware`` ABC: instead of
``ModelRequest.override(messages=...)`` we mutate ``request.messages``
in place.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.core.chat.middlewares.dangling_tool_call_middleware import (
    DanglingToolCallMiddleware,
)


# ── fixtures ──────────────────────────────────────────────────────


def _ai_with_tool_calls(tool_calls: list[dict]) -> AIMessage:
    return AIMessage(content="", tool_calls=tool_calls)


def _ai_with_invalid_tool_calls(invalid_tool_calls: list[dict]) -> AIMessage:
    return AIMessage(content="", tool_calls=[], invalid_tool_calls=invalid_tool_calls)


def _tool_msg(tool_call_id: str, name: str = "test_tool") -> ToolMessage:
    return ToolMessage(content="result", tool_call_id=tool_call_id, name=name)


def _tc(name: str = "bash", tc_id: str = "call_1") -> dict:
    return {"name": name, "id": tc_id, "args": {}}


def _invalid_tc(
    name: str = "write_file",
    tc_id: str = "write_file:36",
    error: str = "Failed to parse tool arguments: malformed JSON",
) -> dict:
    return {
        "type": "invalid_tool_call",
        "name": name,
        "id": tc_id,
        "args": '{"description":"write report","path":"/mnt/user-data/outputs/report.md","content":"bad {"json"}"}',
        "error": error,
    }


# ── _build_patched_messages: no-patch ────────────────────────────


class TestBuildPatchedMessagesNoPatch:
    def test_empty_messages(self) -> None:
        mw = DanglingToolCallMiddleware()
        assert mw._build_patched_messages([]) is None

    def test_no_ai_messages(self) -> None:
        mw = DanglingToolCallMiddleware()
        msgs = [HumanMessage(content="hello")]
        assert mw._build_patched_messages(msgs) is None

    def test_ai_without_tool_calls(self) -> None:
        mw = DanglingToolCallMiddleware()
        msgs = [AIMessage(content="hello")]
        assert mw._build_patched_messages(msgs) is None

    def test_all_tool_calls_responded(self) -> None:
        mw = DanglingToolCallMiddleware()
        msgs = [
            _ai_with_tool_calls([_tc("bash", "call_1")]),
            _tool_msg("call_1", "bash"),
        ]
        assert mw._build_patched_messages(msgs) is None


# ── _build_patched_messages: patching ─────────────────────────────


class TestBuildPatchedMessagesPatching:
    def test_single_dangling_call(self) -> None:
        mw = DanglingToolCallMiddleware()
        msgs = [_ai_with_tool_calls([_tc("bash", "call_1")])]
        patched = mw._build_patched_messages(msgs)
        assert patched is not None
        assert len(patched) == 2
        assert isinstance(patched[1], ToolMessage)
        assert patched[1].tool_call_id == "call_1"
        assert patched[1].status == "error"

    def test_multiple_dangling_calls_same_message(self) -> None:
        mw = DanglingToolCallMiddleware()
        msgs = [_ai_with_tool_calls([_tc("bash", "call_1"), _tc("read", "call_2")])]
        patched = mw._build_patched_messages(msgs)
        assert patched is not None
        assert len(patched) == 3
        tool_msgs = [m for m in patched if isinstance(m, ToolMessage)]
        assert len(tool_msgs) == 2
        assert {tm.tool_call_id for tm in tool_msgs} == {"call_1", "call_2"}

    def test_patch_inserted_after_offending_ai_message(self) -> None:
        mw = DanglingToolCallMiddleware()
        msgs = [
            HumanMessage(content="hi"),
            _ai_with_tool_calls([_tc("bash", "call_1")]),
            HumanMessage(content="still here"),
        ]
        patched = mw._build_patched_messages(msgs)
        assert patched is not None
        assert isinstance(patched[0], HumanMessage)
        assert isinstance(patched[1], AIMessage)
        assert isinstance(patched[2], ToolMessage)
        assert patched[2].tool_call_id == "call_1"
        assert isinstance(patched[3], HumanMessage)

    def test_mixed_responded_and_dangling(self) -> None:
        mw = DanglingToolCallMiddleware()
        msgs = [
            _ai_with_tool_calls([_tc("bash", "call_1"), _tc("read", "call_2")]),
            _tool_msg("call_1", "bash"),
        ]
        patched = mw._build_patched_messages(msgs)
        assert patched is not None
        synthetic = [m for m in patched if isinstance(m, ToolMessage) and m.status == "error"]
        assert len(synthetic) == 1
        assert synthetic[0].tool_call_id == "call_2"

    def test_multiple_ai_messages_each_patched(self) -> None:
        mw = DanglingToolCallMiddleware()
        msgs = [
            _ai_with_tool_calls([_tc("bash", "call_1")]),
            HumanMessage(content="next turn"),
            _ai_with_tool_calls([_tc("read", "call_2")]),
        ]
        patched = mw._build_patched_messages(msgs)
        assert patched is not None
        synthetic = [m for m in patched if isinstance(m, ToolMessage)]
        assert len(synthetic) == 2

    def test_synthetic_message_content(self) -> None:
        mw = DanglingToolCallMiddleware()
        msgs = [_ai_with_tool_calls([_tc("bash", "call_1")])]
        patched = mw._build_patched_messages(msgs)
        tool_msg = patched[1]
        assert "interrupted" in tool_msg.content.lower()
        assert tool_msg.name == "bash"

    def test_raw_provider_tool_calls_are_patched(self) -> None:
        mw = DanglingToolCallMiddleware()
        msgs = [
            AIMessage(
                content="",
                tool_calls=[],
                additional_kwargs={
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {"name": "bash", "arguments": '{"command":"ls"}'},
                        }
                    ]
                },
            )
        ]
        patched = mw._build_patched_messages(msgs)
        assert patched is not None
        assert len(patched) == 2
        assert isinstance(patched[1], ToolMessage)
        assert patched[1].tool_call_id == "call_1"
        assert patched[1].name == "bash"
        assert patched[1].status == "error"

    def test_non_adjacent_tool_result_is_moved_next_to_tool_call(self) -> None:
        middleware = DanglingToolCallMiddleware()
        msgs = [
            _ai_with_tool_calls([_tc("bash", "call_1")]),
            HumanMessage(content="interruption"),
            _tool_msg("call_1", "bash"),
        ]
        patched = middleware._build_patched_messages(msgs)
        assert patched is not None
        assert isinstance(patched[0], AIMessage)
        assert isinstance(patched[1], ToolMessage)
        assert patched[1].tool_call_id == "call_1"
        assert isinstance(patched[2], HumanMessage)

    def test_multiple_tool_results_stay_grouped_after_ai_tool_call(self) -> None:
        mw = DanglingToolCallMiddleware()
        msgs = [
            _ai_with_tool_calls([_tc("bash", "call_1"), _tc("read", "call_2")]),
            HumanMessage(content="interruption"),
            _tool_msg("call_2", "read"),
            _tool_msg("call_1", "bash"),
        ]

        patched = mw._build_patched_messages(msgs)

        assert patched is not None
        assert isinstance(patched[0], AIMessage)
        assert isinstance(patched[1], ToolMessage)
        assert isinstance(patched[2], ToolMessage)
        assert [patched[1].tool_call_id, patched[2].tool_call_id] == ["call_1", "call_2"]
        assert isinstance(patched[3], HumanMessage)

    def test_non_tool_message_inserted_between_partial_tool_results_is_regrouped(self) -> None:
        mw = DanglingToolCallMiddleware()
        msgs = [
            _ai_with_tool_calls([_tc("bash", "call_1"), _tc("read", "call_2")]),
            _tool_msg("call_1", "bash"),
            HumanMessage(content="interruption"),
            _tool_msg("call_2", "read"),
        ]

        patched = mw._build_patched_messages(msgs)

        assert patched is not None
        assert isinstance(patched[0], AIMessage)
        assert isinstance(patched[1], ToolMessage)
        assert isinstance(patched[2], ToolMessage)
        assert [patched[1].tool_call_id, patched[2].tool_call_id] == ["call_1", "call_2"]
        assert isinstance(patched[3], HumanMessage)

    def test_valid_adjacent_tool_results_are_unchanged(self) -> None:
        mw = DanglingToolCallMiddleware()
        msgs = [
            _ai_with_tool_calls([_tc("bash", "call_1")]),
            _tool_msg("call_1", "bash"),
            HumanMessage(content="next"),
        ]

        assert mw._build_patched_messages(msgs) is None

    def test_reused_tool_call_ids_across_ai_turns_keep_their_own_tool_results(self) -> None:
        mw = DanglingToolCallMiddleware()
        msgs = [
            HumanMessage(content="summary", name="summary", additional_kwargs={"hide_from_ui": True}),
            _ai_with_tool_calls(
                [
                    _tc("web_search", "web_search:11"),
                    _tc("web_search", "web_search:12"),
                    _tc("web_search", "web_search:13"),
                ]
            ),
            _tool_msg("web_search:11", "web_search"),
            _tool_msg("web_search:12", "web_search"),
            _tool_msg("web_search:13", "web_search"),
            _ai_with_tool_calls(
                [
                    _tc("web_search", "web_search:9"),
                    _tc("web_search", "web_search:10"),
                    _tc("web_search", "web_search:11"),
                ]
            ),
            _tool_msg("web_search:9", "web_search"),
            _tool_msg("web_search:10", "web_search"),
            _tool_msg("web_search:11", "web_search"),
        ]

        assert mw._build_patched_messages(msgs) is None

    def test_reused_tool_call_id_patches_second_dangling_occurrence(self) -> None:
        mw = DanglingToolCallMiddleware()
        msgs = [
            _ai_with_tool_calls([_tc("web_search", "web_search:11")]),
            _tool_msg("web_search:11", "web_search"),
            _ai_with_tool_calls([_tc("web_search", "web_search:11")]),
        ]

        patched = mw._build_patched_messages(msgs)

        assert patched is not None
        assert isinstance(patched[1], ToolMessage)
        assert patched[1].tool_call_id == "web_search:11"
        assert patched[1].status == "success"
        assert isinstance(patched[3], ToolMessage)
        assert patched[3].tool_call_id == "web_search:11"
        assert patched[3].status == "error"

    def test_reused_tool_call_id_consumes_later_result_for_first_dangling_occurrence(self) -> None:
        mw = DanglingToolCallMiddleware()
        result = _tool_msg("web_search:11", "web_search")
        msgs = [
            _ai_with_tool_calls([_tc("web_search", "web_search:11")]),
            _ai_with_tool_calls([_tc("web_search", "web_search:11")]),
            result,
        ]

        patched = mw._build_patched_messages(msgs)

        assert patched is not None
        assert patched[1] is result
        assert patched[1].status == "success"
        assert isinstance(patched[3], ToolMessage)
        assert patched[3].tool_call_id == "web_search:11"
        assert patched[3].status == "error"

    def test_tool_results_are_grouped_with_their_own_ai_turn_across_multiple_ai_messages(self) -> None:
        mw = DanglingToolCallMiddleware()
        msgs = [
            _ai_with_tool_calls([_tc("bash", "call_1")]),
            HumanMessage(content="interruption"),
            _ai_with_tool_calls([_tc("read", "call_2")]),
            _tool_msg("call_1", "bash"),
            _tool_msg("call_2", "read"),
        ]

        patched = mw._build_patched_messages(msgs)

        assert patched is not None
        assert isinstance(patched[0], AIMessage)
        assert isinstance(patched[1], ToolMessage)
        assert patched[1].tool_call_id == "call_1"
        assert isinstance(patched[2], HumanMessage)
        assert isinstance(patched[3], AIMessage)
        assert isinstance(patched[4], ToolMessage)
        assert patched[4].tool_call_id == "call_2"

    def test_orphan_tool_message_is_preserved_during_grouping(self) -> None:
        mw = DanglingToolCallMiddleware()
        orphan = _tool_msg("orphan_call", "orphan")
        msgs = [
            _ai_with_tool_calls([_tc("bash", "call_1")]),
            orphan,
            HumanMessage(content="interruption"),
            _tool_msg("call_1", "bash"),
        ]

        patched = mw._build_patched_messages(msgs)

        assert patched is not None
        assert isinstance(patched[0], AIMessage)
        assert isinstance(patched[1], ToolMessage)
        assert patched[1].tool_call_id == "call_1"
        assert patched[2] is orphan
        assert isinstance(patched[3], HumanMessage)
        assert patched.count(orphan) == 1

    def test_invalid_tool_call_is_patched(self) -> None:
        mw = DanglingToolCallMiddleware()
        msgs = [_ai_with_invalid_tool_calls([_invalid_tc()])]
        patched = mw._build_patched_messages(msgs)
        assert patched is not None
        assert len(patched) == 2
        assert isinstance(patched[1], ToolMessage)
        assert patched[1].tool_call_id == "write_file:36"
        assert patched[1].name == "write_file"
        assert patched[1].status == "error"
        assert "write_file failed before execution" in patched[1].content
        assert "no file was written" in patched[1].content
        assert "very large Markdown file in a single tool call" in patched[1].content
        assert "Do not retry the same large `write_file` payload" in patched[1].content
        assert "split the file into smaller sections" in patched[1].content
        assert "normal assistant text" in patched[1].content
        assert "Failed to parse tool arguments" in patched[1].content
        assert 'bad {"json"}' not in patched[1].content

    def test_non_write_file_invalid_tool_call_uses_generic_recovery_message(self) -> None:
        mw = DanglingToolCallMiddleware()
        msgs = [_ai_with_invalid_tool_calls([_invalid_tc(name="search", tc_id="search:1")])]

        patched = mw._build_patched_messages(msgs)

        assert patched is not None
        assert patched[1].tool_call_id == "search:1"
        assert patched[1].name == "search"
        assert "arguments were invalid" in patched[1].content
        assert "Failed to parse tool arguments" in patched[1].content
        assert "write_file failed before execution" not in patched[1].content

    def test_valid_and_invalid_tool_calls_are_both_patched(self) -> None:
        mw = DanglingToolCallMiddleware()
        msgs = [
            AIMessage(
                content="",
                tool_calls=[_tc("bash", "call_1")],
                invalid_tool_calls=[_invalid_tc()],
            )
        ]
        patched = mw._build_patched_messages(msgs)
        assert patched is not None
        tool_msgs = [m for m in patched if isinstance(m, ToolMessage)]
        assert len(tool_msgs) == 2
        assert {tm.tool_call_id for tm in tool_msgs} == {"call_1", "write_file:36"}

    def test_invalid_tool_call_already_responded_is_not_patched(self) -> None:
        mw = DanglingToolCallMiddleware()
        msgs = [
            _ai_with_invalid_tool_calls([_invalid_tc()]),
            _tool_msg("write_file:36", "write_file"),
        ]
        assert mw._build_patched_messages(msgs) is None


# ── wrap_model_call (sync) ────────────────────────────────────────


class TestWrapModelCall:
    def test_no_patch_passthrough(self) -> None:
        from app.core.chat.agent.model_call import ModelCallRequest

        mw = DanglingToolCallMiddleware()
        request = ModelCallRequest(messages=[AIMessage(content="hello")], tools=None)
        seen: dict = {}

        async def handler(req: ModelCallRequest) -> Any:
            seen["called_with_messages"] = req.messages
            return "response"

        import asyncio

        result = asyncio.run(mw.awrap_model_call(request, handler))
        assert result == "response"
        assert seen["called_with_messages"] is request.messages

    def test_patched_request_forwarded(self) -> None:
        from app.core.chat.agent.model_call import ModelCallRequest

        mw = DanglingToolCallMiddleware()
        request = ModelCallRequest(
            messages=[_ai_with_tool_calls([_tc("bash", "call_1")])], tools=None
        )

        seen: dict = {}

        async def handler(req: ModelCallRequest) -> Any:
            seen["messages"] = req.messages
            return "response"

        import asyncio

        result = asyncio.run(mw.awrap_model_call(request, handler))
        assert result == "response"
        assert len(seen["messages"]) == 2
        assert isinstance(seen["messages"][1], ToolMessage)
        assert seen["messages"][1].tool_call_id == "call_1"
        # The original request object was mutated in place; caller's
        # reference points to the patched list.
        assert request.messages is seen["messages"]

    def test_wrap_model_call_sync_passthrough(self) -> None:
        from app.core.chat.agent.model_call import ModelCallRequest

        mw = DanglingToolCallMiddleware()
        request = ModelCallRequest(messages=[AIMessage(content="hello")], tools=None)
        seen: dict = {}

        def handler(req: ModelCallRequest) -> str:
            seen["called"] = True
            return "sync-ok"

        result = mw.wrap_model_call(request, handler)
        assert result == "sync-ok"
        assert seen["called"] is True


# ── reasoning-model scenario ──────────────────────────────────────


class TestReasoningModelSafety:
    def test_synthetic_tool_message_keeps_causal_position(self) -> None:
        """Synthetic ToolMessages must appear immediately after the
        offending AIMessage — critical for OpenAI-compatible reasoning
        model specs that require strict tool-result adjacency."""
        mw = DanglingToolCallMiddleware()
        msgs = [
            HumanMessage(content="hi"),
            _ai_with_tool_calls([_tc("bash", "call_1")]),
            HumanMessage(content="next"),
        ]
        patched = mw._build_patched_messages(msgs)
        assert patched is not None
        # patched[0] = HumanMessage, [1] = AIMessage, [2] = synthetic
        # ToolMessage, [3] = HumanMessage. Adjacent 1-2 is required.
        assert patched[1].type == "ai"
        assert patched[2].type == "tool"
        assert patched[3].type == "human"

    def test_no_patch_when_toolcall_id_attribute_present(self) -> None:
        """If a response message has tool_calls but ALL have matching
        ToolMessages, no synthetic injection."""
        mw = DanglingToolCallMiddleware()
        msgs = [
            _ai_with_tool_calls([_tc("bash", "c"), _tc("read", "d")]),
            _tool_msg("c", "bash"),
            _tool_msg("d", "read"),
        ]
        assert mw._build_patched_messages(msgs) is None

    def test_message_tool_calls_normalization(self) -> None:
        """`_message_tool_calls` extracts structured tool_calls."""
        mw = DanglingToolCallMiddleware()
        ai = _ai_with_tool_calls([_tc("bash", "c1"), _tc("read", "c2")])
        calls = mw._message_tool_calls(ai)
        assert len(calls) == 2
        assert {c["id"] for c in calls} == {"c1", "c2"}
        assert {c["name"] for c in calls} == {"bash", "read"}

    def test_message_tool_calls_extracts_from_additional_kwargs(self) -> None:
        """If ``tool_calls`` is empty but ``additional_kwargs['tool_calls']``
        is populated, normalization walks the raw provider payload."""
        mw = DanglingToolCallMiddleware()
        ai = AIMessage(
            content="",
            tool_calls=[],
            additional_kwargs={
                "tool_calls": [
                    {
                        "id": "raw1",
                        "type": "function",
                        "function": {"name": "bash", "arguments": '{"k":1}'},
                    }
                ]
            },
        )
        calls = mw._message_tool_calls(ai)
        assert len(calls) == 1
        assert calls[0]["id"] == "raw1"
        assert calls[0]["name"] == "bash"

    def test_message_tool_calls_extracts_invalid_tool_calls(self) -> None:
        """``invalid_tool_calls`` is normalized into the dangling list."""
        mw = DanglingToolCallMiddleware()
        ai = _ai_with_invalid_tool_calls([_invalid_tc()])
        calls = mw._message_tool_calls(ai)
        assert len(calls) == 1
        assert calls[0]["id"] == "write_file:36"
        assert calls[0]["name"] == "write_file"
        assert calls[0]["invalid"] is True
        assert "Failed to parse" in calls[0]["error"]

    def test_message_tool_calls_returns_empty_for_plain_ai(self) -> None:
        mw = DanglingToolCallMiddleware()
        ai = AIMessage(content="hi")
        assert mw._message_tool_calls(ai) == []


# ── large-error cap (write_file special-case) ─────────────────────


class TestWriteFileSpecialCase:
    def test_capped_error(self) -> None:
        """Issue #2894 — write_file malformed payload: capped at 500 chars."""
        mw = DanglingToolCallMiddleware()
        msgs = [
            _ai_with_invalid_tool_calls(
                [
                    _invalid_tc(
                        error="x" * 5000,
                    )
                ]
            )
        ]
        patched = mw._build_patched_messages(msgs)
        assert patched is not None
        # The error text in the synthetic ToolMessage is capped well below
        # the 5000-char input.
        # (write_file content is large because of the canned guidance
        # text; we only assert the input echo does NOT appear in full.)
        assert "x" * 5000 not in patched[1].content

    def test_no_capped_error_for_non_write_file(self) -> None:
        mw = DanglingToolCallMiddleware()
        msgs = [
            _ai_with_invalid_tool_calls(
                [_invalid_tc(name="search", error="x" * 100, tc_id="search:x")]
            )
        ]
        patched = mw._build_patched_messages(msgs)
        assert patched is not None
        # Generic recovery — small enough to include the input echo.
        assert "x" * 100 in patched[1].content


# ── idempotency / repeated call safety ─────────────────────────────


class TestIdempotency:
    def test_repeated_call_no_op_after_first_patch(self) -> None:
        """After the first patch re-injects missing ToolMessages, a
        second pass should see no dangling ids."""
        mw = DanglingToolCallMiddleware()
        msgs = [_ai_with_tool_calls([_tc("bash", "call_1")])]
        patched = mw._build_patched_messages(msgs)
        assert patched is not None
        assert mw._build_patched_messages(patched) is None


# ── selection rules ───────────────────────────────────────────────


def test_default_no_state_required() -> None:
    """The middleware does NOT require state — purely inspects ``request.messages``."""
    from app.core.chat.agent.model_call import ModelCallRequest

    mw = DanglingToolCallMiddleware()
    request = ModelCallRequest(messages=[AIMessage(content="hi")], tools=None)
    seen: dict = {}

    async def handler(req):
        seen["called"] = True
        return "ok"

    import asyncio

    asyncio.run(mw.awrap_model_call(request, handler))
    assert seen["called"] is True


def test_message_tool_calls_handles_non_dict_entries_gracefully() -> None:
    """Non-dict entries in tool_calls / invalid_tool_calls are skipped."""
    mw = DanglingToolCallMiddleware()
    # Mix of dict (valid) and non-dict entries — pydantic validation
    # would refuse, so the test reaches into attributes directly via
    # ``object.__setattr__`` to simulate a degraded provider payload.
    ai = AIMessage(content="", tool_calls=[{"name": "bash", "id": "c1", "args": {}}])
    object.__setattr__(
        ai,
        "tool_calls",
        ["not a dict", {"name": "bash", "id": "c1", "args": {}}, 42],
    )
    object.__setattr__(ai, "invalid_tool_calls", ["definitely not a dict"])
    calls = mw._message_tool_calls(ai)
    assert len(calls) == 1
    assert calls[0]["name"] == "bash"
    assert calls[0]["id"] == "c1"


def test_max_recovery_error_length_constant() -> None:
    from app.core.chat.middlewares.dangling_tool_call_middleware import (
        _MAX_RECOVERY_ERROR_DETAIL_LEN,
    )

    assert _MAX_RECOVERY_ERROR_DETAIL_LEN == 500
