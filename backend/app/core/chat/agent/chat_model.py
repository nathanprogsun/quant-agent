"""Cached ChatOpenAI factory for chat components.

Shared by ``lead_agent.make_lead_agent`` and ``title_middleware.TitleMiddleware``
to avoid reconstructing identical ``ChatOpenAI`` clients on every call.
"""

from __future__ import annotations

from functools import lru_cache

from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from app.settings import get_settings


@lru_cache(maxsize=4)
def _get_chat_model(model_name: str, temperature: float) -> ChatOpenAI:
    """Build and cache a ChatOpenAI instance keyed by (model_name, temperature)."""
    settings = get_settings()
    return ChatOpenAI(
        model=model_name,
        api_key=SecretStr(settings.openai_api_key.get_secret_value()),
        base_url=settings.openai_base_url,
        temperature=temperature,
    )
