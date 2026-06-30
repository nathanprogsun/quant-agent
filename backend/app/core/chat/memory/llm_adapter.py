"""LLM adapter for the MemoryUpdater (P4.5 wiring).

Wraps a ``ChatOpenAI`` instance into the ``async (prompt: str) -> str`` callable
expected by ``MemoryUpdater``. The model is constructed lazily on first call so
that wiring the subsystem (lifespan / conftest) does not require API credentials
to be present at import/fixture time — only an actual memory-extraction run does.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

if TYPE_CHECKING:
    from langchain_openai import ChatOpenAI as _ChatOpenAI

    from app.settings import Settings


class MemoryLLMAdapter:
    """Async callable wrapping ChatOpenAI for memory extraction prompts."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._model: _ChatOpenAI | None = None

    def _get_model(self) -> _ChatOpenAI:
        if self._model is None:
            self._model = ChatOpenAI(
                model=self._settings.model,
                api_key=SecretStr(self._settings.openai_api_key.get_secret_value()),
                base_url=self._settings.openai_base_url,
                streaming=False,
            )
        return self._model

    async def __call__(self, prompt: str) -> str:
        response = await self._get_model().ainvoke([HumanMessage(content=prompt)])
        content = response.content
        return content if isinstance(content, str) else str(content)


__all__ = ["MemoryLLMAdapter"]
