"""SkillActivationMiddleware — /<skill-name> slash injection.

When the last user HumanMessage starts with ``/<skill-name>``, this
middleware loads the named skill's body from disk, injects a hidden
HumanMessage carrying a ``<slash_skill_activation>`` block (with the
SHA-256 of the body) before the user message, then delegates to the
handler. Progressive disclosure: the body is loaded only on activation,
not eagerly into the system prompt.

Reserved names (bootstrap, help, memory, models, new, status) and
unknown skills are no-ops. Path traversal in the skill name is rejected.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

from langchain_core.messages import BaseMessage, HumanMessage

from app.core.chat.agent.model_call import ModelCallRequest
from app.core.chat.middlewares.base import AgentMiddleware
from app.skills.exceptions import SkillPathTraversalError
from app.skills.storage.local_skill_storage import LocalSkillStorage
from app.skills.types import Skill

RESERVED_SKILL_NAMES: frozenset[str] = frozenset(
    {"bootstrap", "help", "memory", "models", "new", "status"}
)

_SLASH_RE = re.compile(r"^/(?P<name>[^\s]+)(?:\s+(?P<rest>.*))?$")
_SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
_TRAVERSAL_MARKER = ".."


class SkillActivationMiddleware(AgentMiddleware):
    """Inject a skill activation block when a user message starts with /<name>."""

    def __init__(self, storage: LocalSkillStorage) -> None:
        self._storage = storage

    async def awrap_model_call(
        self,
        request: Any,
        handler: Any,
    ) -> Any:
        """Intercept the model call to inject a slash-skill activation block."""
        if not isinstance(request, ModelCallRequest):
            return await handler(request)

        injected = self._maybe_inject(request.messages)
        if injected is not None:
            request.messages = injected
        return await handler(request)

    # ── core ───────────────────────────────────────────────────

    def _maybe_inject(self, messages: list[BaseMessage]) -> list[BaseMessage] | None:
        """Return a new message list with the activation block, or None."""
        if not messages:
            return None
        target = _last_human_message(messages)
        if target is None:
            return None
        content = target.content
        if not isinstance(content, str):
            return None
        match = _SLASH_RE.match(content)
        if not match:
            return None
        name = match.group("name")
        if not name or name in RESERVED_SKILL_NAMES:
            return None
        if _TRAVERSAL_MARKER in name or not _SAFE_NAME_RE.match(name):
            raise SkillPathTraversalError(f"Unsafe skill name rejected: {name!r}")

        skill = self._find_skill(name)
        if skill is None:
            return None
        body = self._storage.read_body(skill)
        activation = _activation_message(skill, body, anchor_id=target.id)
        idx = messages.index(target)
        return [*messages[:idx], activation, target, *messages[idx + 1 :]]

    def _find_skill(self, name: str) -> Skill | None:
        for skill in self._storage.load_skills():
            if skill.name == name:
                return skill
        return None


def _last_human_message(messages: list[BaseMessage]) -> HumanMessage | None:
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            return msg
    return None


def _activation_message(skill: Skill, body: str, *, anchor_id: str | None) -> HumanMessage:
    """Build the hidden activation HumanMessage with a SHA-256 of the body."""
    body_hash = hashlib.sha256(body.encode("utf-8")).hexdigest()
    content = (
        "<slash_skill_activation "
        f'name="{skill.name}" body_hash="{body_hash}">\n'
        f"<skill_name>{skill.name}</skill_name>\n"
        f"<description>{skill.description}</description>\n"
        f"<body_hash>{body_hash}</body_hash>\n"
        "</slash_skill_activation>"
    )
    suffix = "__activation" if anchor_id else ""
    return HumanMessage(
        content=content,
        id=f"{anchor_id}{suffix}" if anchor_id else None,
        additional_kwargs={"hide_from_ui": True, "slash_skill_activation": skill.name},
    )


__all__ = ["RESERVED_SKILL_NAMES", "SkillActivationMiddleware"]
