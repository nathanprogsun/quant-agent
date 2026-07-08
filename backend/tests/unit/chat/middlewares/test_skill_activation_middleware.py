"""Tests for SkillActivationMiddleware — /<skill-name> slash injection."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.core.chat.agent.model_call import ModelCallRequest
from app.core.chat.middlewares.skill_activation_middleware import (
    RESERVED_SLASH_SKILL_NAMES,
    SkillActivationMiddleware,
)
from app.skills.storage.local_skill_storage import LocalSkillStorage


def _seed(root: Path, name: str, body: str = "skill body text") -> None:
    container = root / "public" / name
    container.mkdir(parents=True, exist_ok=True)
    (container / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: desc for {name}\n---\n{body}",
        encoding="utf-8",
    )


def _make_storage(
    tmp_path: Path, name: str = "deep-research", body: str = "do research"
) -> LocalSkillStorage:
    _seed(tmp_path, name, body=body)
    return LocalSkillStorage(root=tmp_path)


async def _capture_handler(seen: dict[str, Any]):
    async def handler(request: ModelCallRequest) -> str:
        seen["messages"] = list(request.messages)
        return "ok"

    return handler


@pytest.mark.asyncio
async def test_slash_command_injects_activation_message(tmp_path: Path) -> None:
    storage = _make_storage(tmp_path, name="deep-research", body="do deep research")
    mw = SkillActivationMiddleware(storage=storage)
    seen: dict[str, Any] = {}
    request = ModelCallRequest(
        messages=[
            SystemMessage(content="sys"),
            HumanMessage(content="/deep-research summarize AI", id="u1"),
        ]
    )
    result = await mw.awrap_model_call(request, await _capture_handler(seen))
    assert result == "ok"
    injected = [m for m in seen["messages"] if isinstance(m, HumanMessage) and m.id != "u1"]
    assert len(injected) == 1, [m.content for m in seen["messages"]]
    content = injected[0].content
    assert "<slash_skill_activation" in content
    assert "deep-research" in content
    expected_hash = hashlib.sha256(b"do deep research").hexdigest()
    assert expected_hash in content


@pytest.mark.asyncio
async def test_reserved_names_rejected(tmp_path: Path) -> None:
    storage = _make_storage(tmp_path)
    mw = SkillActivationMiddleware(storage=storage)
    seen: dict[str, Any] = {}
    request = ModelCallRequest(messages=[HumanMessage(content="/help me", id="u1")])
    await mw.awrap_model_call(request, await _capture_handler(seen))
    # No injection for reserved name
    assert len([m for m in seen["messages"] if isinstance(m, HumanMessage)]) == 1


@pytest.mark.asyncio
async def test_empty_skill_name_is_noop(tmp_path: Path) -> None:
    storage = _make_storage(tmp_path)
    mw = SkillActivationMiddleware(storage=storage)
    seen: dict[str, Any] = {}
    request = ModelCallRequest(messages=[HumanMessage(content="just text", id="u1")])
    await mw.awrap_model_call(request, await _capture_handler(seen))
    assert len(seen["messages"]) == 1


@pytest.mark.asyncio
async def test_unknown_skill_returns_error(tmp_path: Path) -> None:
    storage = _make_storage(tmp_path)
    mw = SkillActivationMiddleware(storage=storage)
    request = ModelCallRequest(messages=[HumanMessage(content="/nonexistent thing", id="u1")])
    result = await mw.awrap_model_call(request, await _capture_handler({}))
    assert isinstance(result, AIMessage)
    assert "not installed" in str(result.content)


@pytest.mark.asyncio
async def test_path_traversal_in_skill_name_blocked(tmp_path: Path) -> None:
    storage = _make_storage(tmp_path)
    mw = SkillActivationMiddleware(storage=storage)
    seen: dict[str, Any] = {}
    request = ModelCallRequest(messages=[HumanMessage(content="/../etc/passwd", id="u1")])
    await mw.awrap_model_call(request, await _capture_handler(seen))
    assert len(seen["messages"]) == 1


@pytest.mark.asyncio
async def test_activation_message_is_hidden(tmp_path: Path) -> None:
    storage = _make_storage(tmp_path, name="deep-research", body="b")
    mw = SkillActivationMiddleware(storage=storage)
    seen: dict[str, Any] = {}
    request = ModelCallRequest(messages=[HumanMessage(content="/deep-research x", id="u1")])
    await mw.awrap_model_call(request, await _capture_handler(seen))
    injected = [m for m in seen["messages"] if isinstance(m, HumanMessage) and m.id != "u1"]
    assert injected[0].additional_kwargs.get("hide_from_ui") is True


def test_reserved_names_contract() -> None:
    assert (
        frozenset({"bootstrap", "help", "memory", "models", "new", "status"})
        == RESERVED_SLASH_SKILL_NAMES
    )
