"""Middleware for explicit slash skill activation.

When the last user HumanMessage starts with ``/<skill-name>``, this middleware
loads the named skill's body from disk, injects a hidden HumanMessage carrying
a ``<slash_skill_activation>`` block (with html-escaped content and SHA-256 of
the body) before the user message, then delegates to the handler. Progressive
disclosure: the body is loaded only on activation, not eagerly into the system
prompt.

Reserved names (bootstrap, help, memory, models, new, status) and unknown skills
are skipped. Disabled skills produce an informative AIMessage error.
"""

from __future__ import annotations

import asyncio
import hashlib
import html
import logging
import re
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, override

from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from app.skills.storage.local_skill_storage import LocalSkillStorage

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

RESERVED_SLASH_SKILL_NAMES: frozenset[str] = frozenset(
    {"bootstrap", "help", "memory", "models", "new", "status"}
)

_SLASH_SKILL_RE = re.compile(r"^/([a-z0-9]+(?:-[a-z0-9]+)*)(?:\s+|$)")

_SLASH_SKILL_ACTIVATION_KEY = "slash_skill_activation"
_SLASH_SKILL_ACTIVATION_TARGET_ID_KEY = "slash_skill_activation_target_id"
_SUMMARY_MESSAGE_NAME = "summary"


@dataclass(frozen=True, slots=True)
class _Activation:
    skill_name: str
    category: str
    container_file_path: str
    skill_content: str
    content_hash: str
    remaining_text: str


@dataclass(frozen=True, slots=True)
class _ActivationResolution:
    activation: _Activation | None = None
    failure_message: str | None = None


def _is_user_activation_target(message: object) -> bool:
    if not isinstance(message, HumanMessage):
        return False
    if message.name == _SUMMARY_MESSAGE_NAME:
        return False
    return not message.additional_kwargs.get("hide_from_ui")


def is_slash_skill_activation_reminder(message: object) -> bool:
    """Return whether a message is a hidden slash-skill activation context block."""
    return isinstance(message, HumanMessage) and bool(
        message.additional_kwargs.get(_SLASH_SKILL_ACTIVATION_KEY)
    )


def _message_content_to_text(content: Any) -> str:
    """Extract text from LangChain message content shapes."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "\n".join(part for part in parts if part)
    return str(content)


def _get_original_user_content_text(content: Any, additional_kwargs: Any) -> str:
    original = (additional_kwargs or {}).get("original_user_content")
    if isinstance(original, str):
        return original
    return _message_content_to_text(content)


class SkillActivationMiddleware(AgentMiddleware[AgentState]):
    """Inject full SKILL.md content when the user explicitly types /skill-name."""

    def __init__(
        self,
        *,
        storage: LocalSkillStorage,
        available_skills: set[str] | None = None,
    ) -> None:
        super().__init__()
        self._storage = storage
        self._available_skills = set(available_skills) if available_skills is not None else None

    def _resolve_activation(self, text: str) -> _ActivationResolution | None:
        match = _SLASH_SKILL_RE.match(text)
        if match is None:
            return None

        name = match.group(1)
        if name in RESERVED_SLASH_SKILL_NAMES:
            return None

        skills = self._storage.load_skills()
        skill = next((candidate for candidate in skills if candidate.name == name), None)
        if skill is None:
            return _ActivationResolution(failure_message=f"Skill `/{name}` is not installed.")
        if not skill.enabled:
            return _ActivationResolution(failure_message=f"Skill `/{name}` is installed but disabled. Enable it before using slash activation.")
        if self._available_skills is not None and name not in self._available_skills:
            return _ActivationResolution(failure_message=f"Skill `/{name}` is not available for this agent.")

        remaining_text = text[match.end():].lstrip()
        try:
            skill_content = self._storage.read_body(skill)
        except OSError:
            logger.exception("Failed to read slash-activated skill %s", name)
            return _ActivationResolution(failure_message=f"Skill `/{name}` could not be loaded safely. Please check the skill installation.")

        content_hash = hashlib.sha256(skill_content.encode("utf-8")).hexdigest()
        return _ActivationResolution(
            activation=_Activation(
                skill_name=name,
                category=str(skill.category),
                container_file_path=str(Path(skill.container_path) / "SKILL.md"),
                skill_content=skill_content,
                content_hash=content_hash,
                remaining_text=remaining_text,
            )
        )

    @staticmethod
    def _build_activation_reminder(activation: _Activation) -> str:
        user_request = activation.remaining_text or (
            "No additional task text was provided after the slash skill command. "
            "Ask the user what they want to do with this skill if the next step is unclear."
        )
        escaped_user_request = html.escape(user_request, quote=False)
        escaped_skill_content = html.escape(activation.skill_content, quote=False)
        escaped_skill_name = html.escape(activation.skill_name, quote=True)
        escaped_category = html.escape(activation.category, quote=True)
        escaped_path = html.escape(activation.container_file_path, quote=True)
        escaped_content_hash = html.escape(activation.content_hash, quote=True)
        return (
            f"<slash_skill_activation>\n"
            f"The user explicitly activated the `{activation.skill_name}` skill for this turn.\n"
            f"Treat the task text as:\n"
            f"<user_request>\n{escaped_user_request}\n</user_request>\n"
            f"\n"
            f"Follow this skill before choosing a general workflow. "
            f"Load supporting resources from the same skill directory only when needed.\n"
            f"\n"
            f'<skill name="{escaped_skill_name}" category="{escaped_category}" '
            f'path="{escaped_path}" sha256="{escaped_content_hash}">\n'
            f'<skill_content encoding="xml-escaped">\n'
            f"{escaped_skill_content}\n"
            f"</skill_content>\n"
            f"</skill>\n"
            f"</slash_skill_activation>"
        )

    @staticmethod
    def _has_existing_activation_for_target(
        messages: list[BaseMessage], target_index: int, target: HumanMessage
    ) -> bool:
        if target_index <= 0:
            return False

        if target.id:
            for previous in messages[:target_index]:
                if not is_slash_skill_activation_reminder(previous):
                    continue
                target_id = previous.additional_kwargs.get(_SLASH_SKILL_ACTIVATION_TARGET_ID_KEY)
                if target_id == target.id or previous.id == f"{target.id}__slash_activation":
                    return True

        previous = messages[target_index - 1]
        return is_slash_skill_activation_reminder(previous)

    def _find_activation_target(
        self, messages: list[BaseMessage]
    ) -> tuple[int, HumanMessage, _ActivationResolution] | None:
        if not messages:
            return None

        target_index = next(
            (
                idx
                for idx in range(len(messages) - 1, -1, -1)
                if _is_user_activation_target(messages[idx])
            ),
            None,
        )
        if target_index is None:
            return None

        target = messages[target_index]
        if not isinstance(target, HumanMessage):
            return None
        if self._has_existing_activation_for_target(list(messages), target_index, target):
            return None

        content = _get_original_user_content_text(target.content, target.additional_kwargs)
        resolution = self._resolve_activation(content)
        if resolution is None:
            return None
        return target_index, target, resolution

    @staticmethod
    def _make_activation_message(target: HumanMessage, activation_content: str) -> HumanMessage:
        stable_id = target.id or str(uuid.uuid4())
        additional_kwargs: dict[str, Any] = {
            "hide_from_ui": True,
            _SLASH_SKILL_ACTIVATION_KEY: True,
        }
        if target.id:
            additional_kwargs[_SLASH_SKILL_ACTIVATION_TARGET_ID_KEY] = target.id
        return HumanMessage(
            content=activation_content,
            id=f"{stable_id}__slash_activation",
            additional_kwargs=additional_kwargs,
        )

    def _prepare_model_request(
        self, request: ModelRequest, *, hook: str
    ) -> ModelRequest | AIMessage | None:
        target_and_resolution = self._find_activation_target(list(request.messages))
        if target_and_resolution is None:
            return None

        target_index, target, resolution = target_and_resolution
        if resolution.failure_message:
            return AIMessage(content=resolution.failure_message)

        activation = resolution.activation
        if activation is None:
            return None

        logger.info(
            "SkillActivationMiddleware: activating slash skill %s category=%s path=%s hash=%s",
            activation.skill_name,
            activation.category,
            activation.container_file_path,
            activation.content_hash,
        )
        activation_msg = self._make_activation_message(
            target, self._build_activation_reminder(activation)
        )
        messages = list(request.messages)
        messages.insert(target_index, activation_msg)
        return request.override(messages=messages)

    @override
    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelResponse | AIMessage:
        prepared = self._prepare_model_request(request, hook="wrap_model_call")
        if prepared is None:
            return handler(request)
        if isinstance(prepared, AIMessage):
            return prepared
        return handler(prepared)

    @override
    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse | AIMessage:
        prepared = await asyncio.to_thread(
            self._prepare_model_request, request, hook="awrap_model_call"
        )
        if prepared is None:
            return await handler(request)
        if isinstance(prepared, AIMessage):
            return prepared
        return await handler(prepared)


__all__ = ["RESERVED_SLASH_SKILL_NAMES", "SkillActivationMiddleware", "is_slash_skill_activation_reminder"]
