"""Title middleware - generates conversation titles."""

from __future__ import annotations

import logging
import re
from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langgraph.runtime import Runtime
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from app.settings import get_settings

logger = logging.getLogger(__name__)

_TITLE_PROMPT = """你是会话标题生成器。根据下面用户与助手的首轮对话，生成一个简洁的中文标题。

要求：
- 仅输出标题本身，不要引号、标点结尾或解释
- 不超过 20 个汉字
- 概括对话主题；问候语（如 hi/hello）应归纳为「新对话」或具体意图
- 必须使用简体中文
"""

_GREETING_ONLY = frozenset({"hi", "hello", "hey", "test", "yo", "hola"})


class TitleMiddleware(AgentMiddleware):
    """Generates a concise Chinese title after the first complete user/assistant turn."""

    def __init__(self, *, max_chars: int = 20) -> None:
        self._max_chars = max_chars

    async def aafter_model(self, state: dict[str, Any], runtime: Runtime) -> dict[str, Any] | None:
        if state.get("title"):
            return None

        messages = state.get("messages", [])
        if len(messages) < 2:
            return None

        last = messages[-1]
        if not isinstance(last, AIMessage) or last.tool_calls:
            return None

        user_text = _latest_human_text(messages)
        if not user_text:
            return None

        ai_text = _message_text(last)
        title = await self._generate_title(user_text, ai_text)
        if title:
            return {"title": title}
        return None

    async def _generate_title(self, user_text: str, ai_text: str) -> str | None:
        fallback = _fallback_title(user_text, ai_text, max_chars=self._max_chars)
        try:
            settings = get_settings()
            model = ChatOpenAI(
                model=settings.model,
                api_key=SecretStr(settings.openai_api_key.get_secret_value()),
                base_url=settings.openai_base_url,
                temperature=0.2,
            )
            response = await model.ainvoke(
                [
                    SystemMessage(content=_TITLE_PROMPT),
                    HumanMessage(content=f"用户：{user_text}\n助手：{ai_text or '（无回复）'}"),
                ]
            )
            generated = _normalize_title(_message_text(response), max_chars=self._max_chars)
            return generated or fallback
        except Exception:
            logger.exception("Title generation failed; using fallback")
            return fallback


def _latest_human_text(messages: list[Any]) -> str:
    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            text = _message_text(message)
            if text:
                return text
    return ""


def _message_text(message: Any) -> str:
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                text = block.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return " ".join(parts).strip()
    return str(content).strip()


def _normalize_title(raw: str, *, max_chars: int) -> str | None:
    title = raw.strip().strip("\"'「」[]")
    title = re.sub(r"\s+", " ", title)
    if not title:
        return None
    if len(title) > max_chars:
        title = title[:max_chars].rstrip()
    return title or None


def _fallback_title(user_text: str, ai_text: str, *, max_chars: int) -> str:
    cleaned = user_text.strip()
    if cleaned.lower() in _GREETING_ONLY or len(cleaned) <= 3:
        return "新对话"

    first_line = cleaned.splitlines()[0].strip()
    if len(first_line) > max_chars:
        return first_line[: max_chars - 1].rstrip() + "…"

    if ai_text and len(first_line) < 8:
        ai_line = ai_text.splitlines()[0].strip()
        if ai_line:
            combined = f"{first_line} · {ai_line[:12]}"
            if len(combined) > max_chars:
                return combined[: max_chars - 1].rstrip() + "…"
            return combined

    return first_line or "新对话"
