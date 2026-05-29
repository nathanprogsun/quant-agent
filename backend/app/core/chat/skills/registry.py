"""Skill registry - central registration and management of agent skills."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class SkillParameter(BaseModel):
    """Definition of a skill parameter."""

    name: str = Field(..., description="Parameter name")
    description: str = Field(..., description="Parameter description")
    type: str = Field(..., description="Parameter type (string, number, boolean, object)")
    required: bool = Field(default=False, description="Whether parameter is required")
    default: Any | None = Field(default=None, description="Default value if optional")


class SkillDefinition(BaseModel):
    """Definition of a skill that can be registered and executed.

    A skill encapsulates:
    - name: unique identifier
    - description: what the skill does
    - version: semantic version
    - parameters: expected input parameters
    - prompt_template: template for LLM invocation
    - tools: list of tool names required by this skill
    - max_iterations: max agentic loops (default 5)
    """

    name: str = Field(..., description="Unique skill name")
    description: str = Field(..., description="Human-readable description")
    version: str = Field(default="1.0.0", description="Semantic version")
    parameters: list[SkillParameter] = Field(default_factory=list, description="Input parameters")
    prompt_template: str = Field(..., description="Prompt template for LLM execution")
    tools: list[str] = Field(default_factory=list, description="Required tool names")
    max_iterations: int = Field(default=5, ge=1, le=50, description="Max agentic iterations")


class SkillRegistry:
    """Central registry for skill definitions.

    Provides registration, lookup, and management of skills
    that can be executed by the agent system.
    """

    def __init__(self) -> None:
        self._skills: dict[str, SkillDefinition] = {}

    def register(self, skill: SkillDefinition) -> None:
        """Register a new skill or overwrite existing one.

        Args:
            skill: Skill definition to register.
        """
        self._skills[skill.name] = skill

    def get(self, name: str) -> SkillDefinition | None:
        """Get skill by name.

        Args:
            name: Skill name to look up.

        Returns:
            Skill definition if found, None otherwise.
        """
        return self._skills.get(name)

    def list_all(self) -> list[SkillDefinition]:
        """List all registered skills.

        Returns:
            List of all skill definitions.
        """
        return list(self._skills.values())

    def unregister(self, name: str) -> bool:
        """Unregister a skill by name.

        Args:
            name: Skill name to remove.

        Returns:
            True if skill was removed, False if not found.
        """
        if name in self._skills:
            del self._skills[name]
            return True
        return False

    def exists(self, name: str) -> bool:
        """Check if skill exists.

        Args:
            name: Skill name to check.

        Returns:
            True if skill exists, False otherwise.
        """
        return name in self._skills


# Singleton instance
_registry: SkillRegistry | None = None


def get_skill_registry() -> SkillRegistry:
    """Get the global SkillRegistry singleton.

    Returns:
        Global SkillRegistry instance.
    """
    global _registry
    if _registry is None:
        _registry = SkillRegistry()
        _register_default_skills(_registry)
    return _registry


def _register_default_skills(registry: SkillRegistry) -> None:
    """Register default built-in skills.

    Args:
        registry: SkillRegistry instance to register defaults.
    """
    # Research skill
    registry.register(
        SkillDefinition(
            name="research",
            description="Conduct deep research on a topic using web search and synthesis",
            version="1.0.0",
            parameters=[
                SkillParameter(
                    name="query",
                    description="Research question or topic",
                    type="string",
                    required=True,
                ),
                SkillParameter(
                    name="depth",
                    description="Research depth (shallow, medium, deep)",
                    type="string",
                    required=False,
                    default="medium",
                ),
            ],
            prompt_template="""Conduct research on the following topic and provide a comprehensive summary:

Topic: {query}
Depth: {depth}

Research should include:
1. Key facts and definitions
2. Different perspectives or approaches
3. Supporting evidence and examples
4. Potential implications or applications

Provide a well-structured response with clear sections.""",
            tools=["web_search", "web_fetch"],
            max_iterations=5,
        )
    )

    # Code review skill
    registry.register(
        SkillDefinition(
            name="code_review",
            description="Review code for bugs, security issues, and improvement suggestions",
            version="1.0.0",
            parameters=[
                SkillParameter(
                    name="code",
                    description="Source code to review",
                    type="string",
                    required=True,
                ),
                SkillParameter(
                    name="language",
                    description="Programming language",
                    type="string",
                    required=True,
                ),
                SkillParameter(
                    name="focus",
                    description="Review focus (security, performance, style, general)",
                    type="string",
                    required=False,
                    default="general",
                ),
            ],
            prompt_template="""Review the following {language} code and provide feedback:

```{language}
{code}
```

Focus areas: {focus}

Provide feedback on:
1. Potential bugs or errors
2. Security vulnerabilities
3. Performance issues
4. Code quality and style
5. Improvement suggestions

Be specific and provide examples where applicable.""",
            tools=["bash"],
            max_iterations=3,
        )
    )

    # Task planning skill
    registry.register(
        SkillDefinition(
            name="task_planning",
            description="Break down a complex task into actionable steps",
            version="1.0.0",
            parameters=[
                SkillParameter(
                    name="goal",
                    description="The goal or objective to plan",
                    type="string",
                    required=True,
                ),
                SkillParameter(
                    name="constraints",
                    description="Any constraints or limitations",
                    type="string",
                    required=False,
                    default="",
                ),
            ],
            prompt_template="""Create a detailed execution plan for the following goal:

Goal: {goal}
Constraints: {constraints}

Break down this goal into:
1. Clear, actionable steps (numbered)
2. Dependencies between steps
3. Estimated time for each step
4. Potential risks and mitigations

Format as a structured markdown plan.""",
            tools=["task"],
            max_iterations=2,
        )
    )
