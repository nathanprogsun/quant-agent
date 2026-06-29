"""LLM factory for jq_kb — returns native LlamaIndex LLMs (not LangChain).

We need native LlamaIndex LLMs because:
- ``QueryFusionRetriever`` detects LangChain models and tries to install
  ``llama-index-llms-langchain`` as a wrapper (extra dep we don't want)
- ``HyDEQueryTransform``, ``TitleExtractor``, etc. all expect native LLMs
- Better observability via LlamaIndex callback manager

For the rest of the agent (LangGraph tools) we keep using LangChain
``ChatOpenAI`` — see ``app.core.chat.llm``.

``ProxyOpenAI`` subclasses LlamaIndex's OpenAI to skip the hardcoded
model-name validation (our proxy serves custom names like ``MiniMax-M3``).
"""

from __future__ import annotations

from functools import lru_cache

import tiktoken
from llama_index.core.base.llms.types import LLMMetadata
from llama_index.llms.openai import OpenAI as LlamaIndexOpenAI
from llama_index.llms.openai.utils import (
    is_function_calling_model,
)
from openai import OpenAI as OpenAIClient

from app.settings import get_settings

# Reasonable default for proxy-served models whose context window we don't know.
_DEFAULT_CONTEXT_WINDOW = 32_000


class ProxyOpenAI(LlamaIndexOpenAI):  # type: ignore[misc]  # LlamaIndexOpenAI typed as Any (stub missing)
    """LlamaIndex OpenAI subclass that tolerates proxy-served model names.

    Upstream ``OpenAI.metadata`` calls ``openai_modelname_to_contextsize``
    and ``_tokenizer`` uses ``tiktoken.encoding_for_model`` — both raise
    ``ValueError``/``KeyError`` for any model not in their hardcoded
    whitelists. Our proxy can serve arbitrary model names, so we
    provide safe defaults.
    """

    @property
    def _tokenizer(self) -> tiktoken.Encoding:
        # Fall back to cl100k_base for any unknown proxy-served model.
        try:
            return tiktoken.encoding_for_model(self._get_model_name())
        except KeyError:
            return tiktoken.get_encoding("cl100k_base")

    @property
    def metadata(self) -> LLMMetadata:
        model_name = self._get_model_name()
        # For proxy-served models, hardcode is_chat_model=True so
        # LlamaIndex routes to /chat/completions. Upstream's
        # is_chat_model() only knows OpenAI's whitelisted names.
        return LLMMetadata(
            context_window=_DEFAULT_CONTEXT_WINDOW,
            num_output=self.max_tokens or -1,
            is_chat_model=True,
            is_function_calling_model=is_function_calling_model(model=model_name),
            model_name=self.model,
            system_role=("user" if self.model == "o1" else "system"),
        )


@lru_cache(maxsize=1)
def _get_openai_client() -> OpenAIClient:
    """Build an OpenAI-compatible client pointed at our proxy."""
    settings = get_settings()
    return OpenAIClient(
        api_key=settings.openai_api_key.get_secret_value(),
        base_url=settings.openai_base_url,
    )


@lru_cache(maxsize=1)
def get_llm(*, temperature: float = 0.0) -> ProxyOpenAI:
    """Return native LlamaIndex OpenAI-compatible LLM.

    Uses ``ProxyOpenAI`` to skip the model-name whitelist check
    (our proxy serves custom names like ``MiniMax-M3``).
    """
    settings = get_settings()
    return ProxyOpenAI(
        model=settings.model,
        api_key=settings.openai_api_key.get_secret_value(),
        api_base=settings.openai_base_url,
        temperature=temperature,
        openai_client=_get_openai_client(),
    )


def get_judge_llm() -> ProxyOpenAI:
    return get_llm(temperature=0.0)
