"""Task tool for subagent delegation."""

from __future__ import annotations

from langchain_core.callbacks import CallbackManagerForToolRun
from langchain_core.tools import BaseTool, ToolException
from pydantic import BaseModel, Field


class TaskInput(BaseModel):
    """Input schema for TaskTool."""

    task_type: str = Field(
        description="Type of task to delegate (e.g., 'research', 'coding', 'review')"
    )
    prompt: str = Field(description="The prompt/instruction for the subagent to execute")
    description: str = Field(description="Human-readable description of the task")


class TaskTool(BaseTool):
    """Tool for delegating tasks to subagents.

    This tool allows the main agent to spawn subagents for specific
    tasks such as research, coding, review, or analysis.

    The tool returns the result of the subagent execution as a string.
    """

    name: str = "task"
    description: str = "Delegate a specific task to a subagent. Use when you need help with specialized tasks like research, coding, review, or analysis."
    args_schema: type[BaseModel] = TaskInput

    def _run(
        self,
        task_type: str,
        prompt: str,
        description: str,
        run_manager: CallbackManagerForToolRun | None = None,
    ) -> str:
        """Execute the task delegation.

        Args:
            task_type: Type of task to delegate.
            prompt: The prompt for the subagent.
            description: Description of the task.
            run_manager: Callback manager for tool execution.

        Returns:
            Result from the subagent execution.
        """
        raise ToolException(
            "TaskTool._run is not implemented. Use _arun for async execution."
        )

    async def _arun(
        self,
        task_type: str,
        prompt: str,
        description: str,
        run_manager: CallbackManagerForToolRun | None = None,
    ) -> str:
        """Async execute the task delegation.

        Args:
            task_type: Type of task to delegate.
            prompt: The prompt for the subagent.
            description: Description of the task.
            run_manager: Callback manager for tool execution.

        Returns:
            Result from the subagent execution.
        """
        # TODO: Implement actual subagent delegation
        # This is a placeholder that returns a structured response
        # In production, this would spawn a subagent and return its result
        result = {
            "status": "delegated",
            "task_type": task_type,
            "description": description,
            "prompt": prompt,
            "note": "Subagent delegation not yet implemented",
        }
        return str(result)
