"""Input validation unit tests."""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.common.runs.manager import MultitaskStrategy
from app.common.runs.schemas import DisconnectMode
from app.web.api.thread.schema import MAX_MESSAGES, MessageInput, RunCreateRequest
from app.web.api.thread.services import MAX_MESSAGE_LENGTH, normalize_input

# ── MessageInput model tests ─────────────────────────────────


class TestMessageInput:
    """Tests for MessageInput Pydantic model."""

    def test_valid_user_message(self) -> None:
        msg = MessageInput(role="user", content="Hello")
        assert msg.role == "user"
        assert msg.content == "Hello"

    def test_valid_assistant_message(self) -> None:
        msg = MessageInput(role="assistant", content="Hi there")
        assert msg.role == "assistant"

    def test_valid_system_message(self) -> None:
        msg = MessageInput(role="system", content="You are a helpful assistant")
        assert msg.role == "system"

    def test_rejects_invalid_role(self) -> None:
        with pytest.raises(ValidationError):
            MessageInput(role="admin", content="Hello")  # type: ignore[arg-type]

    def test_empty_content_is_valid(self) -> None:
        msg = MessageInput(role="user", content="")
        assert msg.content == ""

    def test_content_at_max_length(self) -> None:
        content = "a" * MAX_MESSAGE_LENGTH
        msg = MessageInput(role="user", content=content)
        assert len(msg.content) == MAX_MESSAGE_LENGTH

    def test_content_exceeds_max_length(self) -> None:
        content = "a" * (MAX_MESSAGE_LENGTH + 1)
        with pytest.raises(ValidationError):
            MessageInput(role="user", content=content)


# ── RunCreateRequest model tests ─────────────────────────────


class TestRunCreateRequest:
    """Tests for RunCreateRequest Pydantic model."""

    def test_default_values(self) -> None:
        req = RunCreateRequest()
        assert req.on_disconnect == DisconnectMode.CANCEL
        assert req.multitask_strategy == MultitaskStrategy.REJECT
        assert req.input == {"messages": []}
        assert req.stream_mode == ["values", "messages-tuple"]

    def test_valid_disconnect_mode_cancel(self) -> None:
        req = RunCreateRequest(on_disconnect=DisconnectMode.CANCEL)
        assert req.on_disconnect == DisconnectMode.CANCEL

    def test_valid_disconnect_mode_keep_alive(self) -> None:
        req = RunCreateRequest(on_disconnect="keep_alive")  # type: ignore[arg-type]
        assert req.on_disconnect == DisconnectMode.CONTINUE

    def test_valid_disconnect_mode_continue_alias(self) -> None:
        req = RunCreateRequest(on_disconnect="continue")  # type: ignore[arg-type]
        assert req.on_disconnect == DisconnectMode.CONTINUE

    def test_rejects_invalid_disconnect_mode(self) -> None:
        with pytest.raises(ValidationError):
            RunCreateRequest(on_disconnect="invalid_mode")  # type: ignore[arg-type]

    def test_valid_multitask_strategy_reject(self) -> None:
        req = RunCreateRequest(multitask_strategy=MultitaskStrategy.REJECT)
        assert req.multitask_strategy == MultitaskStrategy.REJECT

    def test_valid_multitask_strategy_enums(self) -> None:
        for strategy in MultitaskStrategy:
            req = RunCreateRequest(multitask_strategy=strategy)
            assert req.multitask_strategy == strategy

    def test_rejects_invalid_multitask_strategy(self) -> None:
        with pytest.raises(ValidationError):
            RunCreateRequest(multitask_strategy="invalid_strategy")  # type: ignore[arg-type]

    def test_valid_input_with_messages(self) -> None:
        messages = [{"role": "user", "content": "Hello"}]
        req = RunCreateRequest(input={"messages": messages})
        assert req.input["messages"] == messages

    def test_input_messages_at_max_count(self) -> None:
        messages = [{"role": "user", "content": f"msg {i}"} for i in range(MAX_MESSAGES)]
        req = RunCreateRequest(input={"messages": messages})
        assert len(req.input["messages"]) == MAX_MESSAGES

    def test_input_messages_exceeds_max_count(self) -> None:
        messages = [{"role": "user", "content": f"msg {i}"} for i in range(MAX_MESSAGES + 1)]
        with pytest.raises(ValidationError, match="messages 数组长度不能超过"):
            RunCreateRequest(input={"messages": messages})

    def test_empty_messages_array_is_valid(self) -> None:
        req = RunCreateRequest(input={"messages": []})
        assert req.input["messages"] == []


# ── normalize_input function tests ───────────────────────────


class TestNormalizeInput:
    """Tests for normalize_input function."""

    def test_empty_messages(self) -> None:
        result = normalize_input({"messages": []})
        assert result == {"messages": []}

    def test_no_messages_key(self) -> None:
        result = normalize_input({})
        assert result == {"messages": []}

    def test_valid_user_message(self) -> None:
        raw = {"messages": [{"role": "user", "content": "Hello"}]}
        result = normalize_input(raw)
        assert len(result["messages"]) == 1

    def test_valid_assistant_message(self) -> None:
        raw = {"messages": [{"role": "assistant", "content": "Hi"}]}
        result = normalize_input(raw)
        assert len(result["messages"]) == 1

    def test_rejects_invalid_role(self) -> None:
        raw = {"messages": [{"role": "admin", "content": "Hello"}]}
        with pytest.raises(HTTPException) as exc_info:
            normalize_input(raw)
        assert exc_info.value.status_code == 400
        assert exc_info.value.detail == "请求参数无效"

    def test_rejects_message_exceeding_max_length(self) -> None:
        content = "a" * (MAX_MESSAGE_LENGTH + 1)
        raw = {"messages": [{"role": "user", "content": content}]}
        with pytest.raises(HTTPException) as exc_info:
            normalize_input(raw)
        assert exc_info.value.status_code == 400
        assert exc_info.value.detail == "请求参数无效"

    def test_message_at_max_length_passes(self) -> None:
        content = "a" * MAX_MESSAGE_LENGTH
        raw = {"messages": [{"role": "user", "content": content}]}
        result = normalize_input(raw)
        assert len(result["messages"]) == 1

    def test_rejects_unsupported_message_type(self) -> None:
        raw = {"messages": [42]}
        with pytest.raises(HTTPException) as exc_info:
            normalize_input(raw)
        assert exc_info.value.status_code == 400
        assert exc_info.value.detail == "请求参数无效"

    def test_standard_roles_pass(self) -> None:
        for role in ("user", "assistant", "system"):
            raw = {"messages": [{"role": role, "content": "test"}]}
            result = normalize_input(raw)
            assert len(result["messages"]) == 1

    def test_multiple_valid_messages(self) -> None:
        raw = {
            "messages": [
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Hi"},
                {"role": "user", "content": "How are you?"},
            ]
        }
        result = normalize_input(raw)
        assert len(result["messages"]) == 3
