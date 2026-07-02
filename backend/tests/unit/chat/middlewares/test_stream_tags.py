"""Tests for stream_tags module."""

from __future__ import annotations

from app.core.chat.middlewares.stream_tags import TAG_NOSTREAM, apply_no_stream_tag


class _FakeModel:
    """Minimal stand-in for a langchain Runnable."""

    def __init__(self, tags: list[str] | None = None) -> None:
        self.config = {"tags": list(tags or [])}

    def with_config(self, **kwargs: object) -> _FakeModel:
        new = _FakeModel(tags=list(self.config.get("tags", [])))
        new.config.update(kwargs)
        return new


def test_tag_nostream_constant() -> None:
    assert TAG_NOSTREAM == "nostream"


def test_apply_no_stream_tag_adds_tag() -> None:
    model = _FakeModel(tags=["existing"])
    out = apply_no_stream_tag(model)
    assert TAG_NOSTREAM in out.config["tags"]
    assert "existing" in out.config["tags"]


def test_apply_no_stream_tag_idempotent() -> None:
    model = _FakeModel(tags=[TAG_NOSTREAM])
    out = apply_no_stream_tag(model)
    # Same object because tag already present
    assert out is model


def test_apply_no_stream_tag_empty_initial() -> None:
    model = _FakeModel()
    out = apply_no_stream_tag(model)
    assert TAG_NOSTREAM in out.config["tags"]


def test_apply_no_stream_tag_handles_non_runnable() -> None:
    class _Bare:
        pass

    bare = _Bare()
    assert apply_no_stream_tag(bare) is bare
