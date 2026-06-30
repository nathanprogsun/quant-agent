"""read_file tool — progressive-disclosure skill body loader.

Resolves ``<container_path>/<file_path>`` against a whitelist of container
roots (the skill storage roots). Path traversal outside the container is
rejected. Used by the LLM to fetch a SKILL.md body on demand rather than
eagerly loading all skill bodies into the prompt.
"""

from __future__ import annotations

from pathlib import Path

from langchain_core.callbacks import CallbackManagerForToolRun
from langchain_core.tools import BaseTool, ToolException
from pydantic import BaseModel, Field

_DEFAULT_FILE_PATH = "SKILL.md"


class ReadFileInput(BaseModel):
    """Input schema for ReadFileTool."""

    container_path: str = Field(
        description="Absolute path of the skill container (the skill's container_path)."
    )
    file_path: str = Field(
        default=_DEFAULT_FILE_PATH,
        description="Relative path within the container (default: SKILL.md).",
    )


class ReadFileTool(BaseTool):
    """Read a file from a whitelisted skill container."""

    name: str = "read_file"
    description: str = (
        "Read a file (default: SKILL.md) from a skill container to load its "
        "body on demand. Pass the skill's container_path and an optional "
        "relative file_path. Path traversal outside the container is rejected."
    )
    args_schema: type[BaseModel] = ReadFileInput

    # Whitelist of resolved container roots.
    containers: list[Path] = Field(default_factory=list)

    def _run(
        self,
        container_path: str,
        file_path: str = _DEFAULT_FILE_PATH,
        run_manager: CallbackManagerForToolRun | None = None,
    ) -> str:
        """Read a file from a whitelisted container synchronously."""
        return self._read(container_path, file_path)

    async def _arun(
        self,
        container_path: str,
        file_path: str = _DEFAULT_FILE_PATH,
        run_manager: CallbackManagerForToolRun | None = None,
    ) -> str:
        """Read a file from a whitelisted container asynchronously."""
        return self._read(container_path, file_path)

    # ── core ───────────────────────────────────────────────────

    def _read(self, container_path: str, file_path: str) -> str:
        target = self._resolve_safe(container_path, file_path)
        try:
            text = target.read_text(encoding="utf-8")
        except OSError as e:
            raise ToolException(f"Cannot read {target}: {e}") from e
        return self._strip_frontmatter(text)

    def _resolve_safe(self, container_path: str, file_path: str) -> Path:
        """Resolve <container>/<file> and reject traversal outside container."""
        container = Path(container_path).resolve()
        # Container must be within (or equal to) one of the whitelisted roots.
        if not self._is_within_whitelist(container):
            raise ToolException(f"Container {container} is not within any whitelisted skill root")
        if not container.is_dir():
            raise ToolException(f"Container does not exist: {container}")
        # Reject absolute file_path (would escape the container) and resolve safely.
        candidate = (container / file_path).resolve()
        try:
            candidate.relative_to(container)
        except ValueError as e:
            raise ToolException(f"Path traversal outside container rejected: {file_path}") from e
        # Final guard: resolved target must still be within the whitelist root.
        if not self._is_within_whitelist(candidate):
            raise ToolException(f"Resolved path outside whitelist: {candidate}")
        return candidate

    def _is_within_whitelist(self, path: Path) -> bool:
        if not self.containers:
            return False
        for root in self.containers:
            resolved_root = Path(root).resolve()
            try:
                path.relative_to(resolved_root)
                return True
            except ValueError:
                continue
        return False

    @staticmethod
    def _strip_frontmatter(text: str) -> str:
        """Return SKILL.md body without the YAML frontmatter block."""
        if not text.startswith("---"):
            return text
        parts = text.split("---", 2)
        if len(parts) < 3:
            return text
        return parts[2].lstrip("\n")
