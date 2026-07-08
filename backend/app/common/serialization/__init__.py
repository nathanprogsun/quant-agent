"""LangGraph chunk serialization utilities.

Two concerns live here:

1. ``serialize_langgraph_chunk`` — unpacks a raw ``astream`` item into a
   ``(mode, data)`` tuple. Used by the worker loop before mode-aware
   serialization.
2. ``serialize(obj, *, mode=)`` and friends — convert LangChain / LangGraph
   objects into JSON-serialisable structures with mode-specific handling:

   * ``messages`` — obj is ``(message_chunk, metadata_dict)``; returns
     ``[chunk_dump, metadata_dict]``.
   * ``values`` — obj is the full state dict; strips internal ``__pregel_*``
     keys and base64 ``data:`` image blocks from ``hide_from_ui`` messages
     so they never reach the SSE wire.
   * everything else — recursive ``model_dump()`` / ``dict()`` fallback.

The image stripping mirrors deer-flow's ``strip_data_url_image_blocks``:
internal model context that carries full base64 image payloads would bloat
response bodies and expose data: URLs with no UI value, so they are dropped
from hidden messages only. Text blocks, https image URLs, and non-hidden
messages are left untouched so ordering and count are preserved.
"""

from __future__ import annotations

from typing import Any


def serialize_langgraph_chunk(
    item: Any,
    stream_modes: list[str] | None = None,
) -> tuple[str, Any]:
    """Parse LangGraph astream output into (mode, data).

    Handles three formats:
    - 2-tuple: (mode, data) — standard
    - 3-tuple: (namespace, mode, data) — subgraph
    - single value: data — defaults to "values" mode

    Args:
        item: Raw chunk from agent.astream().
        stream_modes: Accepted mode names. If set, non-matching modes
            are wrapped as "values".

    Returns:
        (mode, data) tuple.
    """
    if isinstance(item, tuple):
        if len(item) == 3:
            _, mode, data = item
            if not stream_modes or mode in stream_modes:
                return mode, data
        elif len(item) == 2:
            mode, data = item
            if not stream_modes or mode in stream_modes:
                return mode, data
    return "values", item


# ---------------------------------------------------------------------------
# Mode-aware serialization
# ---------------------------------------------------------------------------


def _serialize_lc_object(obj: Any) -> Any:
    """Recursively serialize a LangChain object to a JSON-serialisable dict.

    Primitives pass through unchanged. Containers recurse. Pydantic v2
    models prefer ``model_dump()``; Pydantic v1 / older objects fall back
    to ``.dict()``. The last resort is ``str()`` so a non-serialisable object
    never crashes the SSE publish path.
    """
    if obj is None:
        return None
    if isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, dict):
        return {k: _serialize_lc_object(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_serialize_lc_object(item) for item in obj]
    # Pydantic v2
    if hasattr(obj, "model_dump"):
        try:
            return obj.model_dump()
        except Exception:
            pass
    # Pydantic v1 / older objects
    if hasattr(obj, "dict"):
        try:
            return obj.dict()
        except Exception:
            pass
    try:
        return str(obj)
    except Exception:
        return repr(obj)


def serialize_channel_values(channel_values: dict[str, Any]) -> dict[str, Any]:
    """Serialize channel values, stripping internal LangGraph keys.

    Only ``__pregel_*`` keys are removed — everything else (``messages``,
    ``title``, ``__interrupt__`` for the SDK) is preserved and recursively
    serialized.
    """
    result: dict[str, Any] = {}
    for key, value in channel_values.items():
        if key.startswith("__pregel_"):
            continue
        result[key] = _serialize_lc_object(value)
    return result


def strip_data_url_image_blocks(messages: list[Any]) -> list[Any]:
    """Remove ``data:``-scheme ``image_url`` blocks from hide_from_ui messages.

    Accepts a heterogeneous list (dicts, plain strings, None) for robustness
    against malformed channel values; non-dict entries pass through
    untouched so ordering and count are preserved.
    """
    result: list[dict[str, Any]] = []
    for msg in messages:
        if not isinstance(msg, dict):
            result.append(msg)
            continue

        additional_kwargs = msg.get("additional_kwargs")
        if not (
            isinstance(additional_kwargs, dict) and additional_kwargs.get("hide_from_ui") is True
        ):
            result.append(msg)
            continue

        content = msg.get("content")
        if not isinstance(content, list):
            result.append(msg)
            continue

        filtered = [
            block
            for block in content
            if not (
                isinstance(block, dict)
                and block.get("type") == "image_url"
                and isinstance(block.get("image_url"), dict)
                and str(block["image_url"].get("url", "")).startswith("data:")
            )
        ]
        result.append({**msg, "content": filtered})
    return result


def serialize_channel_values_for_api(channel_values: dict[str, Any]) -> dict[str, Any]:
    """Serialize channel values and strip base64 image data from messages.

    Convenience wrapper combining :func:`serialize_channel_values` with
    :func:`strip_data_url_image_blocks`. Use this in all REST/SSE paths
    that return channel values to the frontend so ``data:``-scheme base64
    image payloads are never sent over the wire.
    """
    result = serialize_channel_values(channel_values)
    if isinstance(result.get("messages"), list):
        result["messages"] = strip_data_url_image_blocks(result["messages"])
    return result


def serialize_messages_tuple(obj: Any) -> Any:
    """Serialize a messages-mode tuple ``(chunk, metadata)``.

    Returns ``[chunk_dump, metadata_dict]`` for a 2-tuple or a 2-list; if
    the second element is a dict it is preserved verbatim, otherwise it is
    serialized. Everything else is serialized directly (matching the
    non-tuple fallback for ``messages`` mode).
    """
    if isinstance(obj, (tuple, list)) and len(obj) == 2:
        chunk, metadata = obj
        metadata_out = (
            metadata if isinstance(metadata, dict) else _serialize_lc_object(metadata) or {}
        )
        return [_serialize_lc_object(chunk), metadata_out]
    return _serialize_lc_object(obj)


def serialize(obj: Any, *, mode: str = "") -> Any:
    """Serialize LangChain objects with mode-specific handling.

    * ``messages`` — obj is ``(message_chunk, metadata_dict)``; returns
      ``[chunk_dump, metadata_dict]``.
    * ``values`` — obj is the full state dict; strips ``__pregel_*`` keys
      and base64 ``data:`` image blocks from ``hide_from_ui`` messages.
    * everything else — recursive ``model_dump()`` / ``dict()`` fallback.
    """
    if mode == "messages":
        return serialize_messages_tuple(obj)
    if mode == "values":
        if isinstance(obj, dict):
            return serialize_channel_values_for_api(obj)
        return _serialize_lc_object(obj)
    return _serialize_lc_object(obj)


__all__ = [
    "serialize",
    "serialize_channel_values",
    "serialize_channel_values_for_api",
    "serialize_langgraph_chunk",
    "serialize_messages_tuple",
    "strip_data_url_image_blocks",
]
