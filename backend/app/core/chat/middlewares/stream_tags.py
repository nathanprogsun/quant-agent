"""Stream tags for LLM invocations.

``TAG_NOSTREAM`` marks a model invocation as "not for streaming" so
downstream stream handlers (SSE / LangGraph stream mode) can suppress
emission of intermediate LLM tokens for that call. Used by internal
"meta" LLM calls (summarization, title generation) whose output should
not appear as AI assistant messages in the user-visible stream.
"""

from __future__ import annotations

TAG_NOSTREAM = "nostream"


def apply_no_stream_tag(model: object) -> object:
    """Return ``model`` with the ``TAG_NOSTREAM`` tag added to its config.

    No-op when the model object does not expose ``with_config`` (the
    standard langchain Runnable interface).
    """
    with_config = getattr(model, "with_config", None)
    if with_config is None:
        return model
    config = getattr(model, "config", None) or {}
    existing_tags = list(config.get("tags", []) or [])
    if TAG_NOSTREAM in existing_tags:
        return model
    return with_config(tags=[*existing_tags, TAG_NOSTREAM])
