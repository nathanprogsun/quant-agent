"""Tests for the read_file tool (skill body loader)."""

from __future__ import annotations

from pathlib import Path

import pytest
from langchain_core.tools import ToolException

from app.core.chat.tools.builtin.read_file_tool import ReadFileInput, ReadFileTool


def _make_container(root: Path, name: str = "demo", body: str = "# body content") -> Path:
    container = root / name
    container.mkdir(parents=True, exist_ok=True)
    (container / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: d\n---\n{body}", encoding="utf-8"
    )
    return container


def test_read_skill_md_returns_body(tmp_path: Path) -> None:
    container = _make_container(tmp_path, body="the body text")
    tool = ReadFileTool(containers=[tmp_path])
    result = tool._run(container_path=str(container), file_path="SKILL.md")
    assert result == "the body text"


def test_read_default_file_path_is_skill_md(tmp_path: Path) -> None:
    container = _make_container(tmp_path, body="default body")
    tool = ReadFileTool(containers=[tmp_path])
    result = tool._run(container_path=str(container))
    assert result == "default body"


def test_read_strips_frontmatter(tmp_path: Path) -> None:
    container = _make_container(tmp_path, body="only body")
    tool = ReadFileTool(containers=[tmp_path])
    result = tool._run(container_path=str(container))
    assert "---" not in result
    assert result == "only body"


def test_path_traversal_rejected(tmp_path: Path) -> None:
    container = _make_container(tmp_path)
    tool = ReadFileTool(containers=[tmp_path])
    with pytest.raises(ToolException) as exc:
        tool._run(container_path=str(container), file_path="../../../etc/passwd")
    assert "traversal" in str(exc.value).lower() or "outside" in str(exc.value).lower()


def test_container_outside_whitelist_rejected(tmp_path: Path) -> None:
    container = _make_container(tmp_path)
    other = tmp_path / "other"
    other.mkdir()
    tool = ReadFileTool(containers=[other])
    with pytest.raises(ToolException):
        tool._run(container_path=str(container), file_path="SKILL.md")


def test_unknown_container_rejected(tmp_path: Path) -> None:
    tool = ReadFileTool(containers=[tmp_path])
    with pytest.raises(ToolException):
        tool._run(container_path="/nonexistent/path", file_path="SKILL.md")


async def test_arun_returns_body(tmp_path: Path) -> None:
    container = _make_container(tmp_path, body="async body")
    tool = ReadFileTool(containers=[tmp_path])
    result = await tool._arun(container_path=str(container), file_path="SKILL.md")
    assert result == "async body"


def test_read_file_input_schema() -> None:
    schema = ReadFileInput.model_fields
    assert "container_path" in schema
    assert "file_path" in schema
