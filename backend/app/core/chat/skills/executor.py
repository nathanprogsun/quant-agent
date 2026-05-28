"""Skill executor - invokes LLM with skill prompt templates."""

from __future__ import annotations

from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from app.core.chat.skills.registry import SkillDefinition, get_skill_registry


class SkillExecutionError(Exception):
    """Raised when skill execution fails."""

    pass


class SkillExecutor:
    """Executes skills by invoking LLMs with skill prompt templates.

    Handles:
    - Prompt rendering with parameters
    - Tool availability checking
    - LLM invocation
    """

    def __init__(self, llm: BaseChatModel) -> None:
        """Initialize SkillExecutor.

        Args:
            llm: Chat LLM to use for skill execution.
        """
        self._llm = llm
        self._registry = get_skill_registry()

    async def execute(
        self,
        skill_name: str,
        parameters: dict[str, Any],
        system_prompt: str | None = None,
    ) -> str:
        """Execute a skill with given parameters.

        Args:
            skill_name: Name of skill to execute.
            parameters: Skill parameters.
            system_prompt: Optional system prompt to prepend.

        Returns:
            LLM response content.

        Raises:
            SkillExecutionError: If skill not found or execution fails.
        """
        skill = self._registry.get(skill_name)
        if not skill:
            raise SkillExecutionError(f"Skill not found: {skill_name}")

        # Render prompt template with parameters
        prompt = self._render_prompt(skill, parameters)

        # Build messages
        messages = []
        if system_prompt:
            messages.append(SystemMessage(content=system_prompt))
        messages.append(HumanMessage(content=prompt))

        # Invoke LLM
        try:
            result: ChatResult = await self._llm.agenerate([messages])
            generations = result.generations
            if not generations or not generations[0]:
                raise SkillExecutionError("LLM returned no generations")
            chat_gen: ChatGeneration = generations[0][0]
            return chat_gen.message.content or ""
        except Exception as e:
            raise SkillExecutionError(f"LLM invocation failed: {e}") from e

    def _render_prompt(self, skill: SkillDefinition, parameters: dict[str, Any]) -> str:
        """Render skill prompt template with parameters.

        Args:
            skill: Skill definition.
            parameters: Parameters to inject.

        Returns:
            Rendered prompt string.

        Raises:
            SkillExecutionError: If required parameter is missing.
        """
        # Validate required parameters
        for param_def in skill.parameters:
            if param_def.required and param_def.name not in parameters:
                raise SkillExecutionError(
                    f"Missing required parameter: {param_def.name}"
                )

        # Build template context with defaults
        context: dict[str, Any] = {}
        for param_def in skill.parameters:
            value = parameters.get(param_def.name, param_def.default)
            context[param_def.name] = value if value is not None else ""

        # Render template
        try:
            return skill.prompt_template.format(**context)
        except KeyError as e:
            raise SkillExecutionError(f"Invalid parameter in template: {e}") from e

    def get_skill_tools(self, skill_name: str) -> list[str]:
        """Get list of tool names required by a skill.

        Args:
            skill_name: Name of skill.

        Returns:
            List of required tool names.

        Raises:
            SkillExecutionError: If skill not found.
        """
        skill = self._registry.get(skill_name)
        if not skill:
            raise SkillExecutionError(f"Skill not found: {skill_name}")
        return skill.tools.copy()

    def get_skill(self, skill_name: str) -> SkillDefinition | None:
        """Get skill definition by name.

        Args:
            skill_name: Name of skill.

        Returns:
            Skill definition or None if not found.
        """
        return self._registry.get(skill_name)