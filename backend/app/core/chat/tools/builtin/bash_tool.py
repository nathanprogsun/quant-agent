"""Bash tool for command execution."""

from __future__ import annotations

import asyncio
import shlex
from typing import Any

from langchain_core.callbacks import CallbackManagerForToolRun
from langchain_core.tools import BaseTool, ToolException
from pydantic import BaseModel, Field


class BashInput(BaseModel):
    """Input schema for BashTool."""

    command: str = Field(description="The bash command to execute")
    timeout: int = Field(
        default=30,
        description="Timeout in seconds for command execution (max 300)",
    )


class BashTool(BaseTool):
    """Tool for executing bash commands.

    This tool allows the agent to execute bash commands on the system.
    Commands are executed with a timeout to prevent hanging.

    SECURITY: Only use this tool in trusted environments with proper
    input validation. Malicious commands can cause significant damage.
    """

    name: str = "bash"
    description: str = "Execute a bash command on the system. Use for system operations, running scripts, or interacting with the file system."
    args_schema: type[BaseModel] = BashInput

    def _run(
        self,
        command: str,
        timeout: int = 30,
        run_manager: CallbackManagerForToolRun | None = None,
    ) -> str:
        """Execute a bash command synchronously.

        Args:
            command: The bash command to execute.
            timeout: Timeout in seconds (max 300).
            run_manager: Callback manager for tool execution.

        Returns:
            Combined stdout and stderr output from the command.
        """
        raise ToolException(
            "BashTool._run is not implemented. Use _arun for async execution."
        )

    async def _arun(
        self,
        command: str,
        timeout: int = 30,
        run_manager: CallbackManagerForToolRun | None = None,
    ) -> str:
        """Async execute a bash command.

        Args:
            command: The bash command to execute.
            timeout: Timeout in seconds (max 300).
            run_manager: Callback manager for tool execution.

        Returns:
            Combined stdout and stderr output from the command.

        Raises:
            ToolException: If command execution fails or times out.
        """
        # Enforce maximum timeout
        timeout = min(timeout, 300)

        try:
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout,
                )
            except asyncio.TimeoutError:
                process.kill()
                raise ToolException(f"Command timed out after {timeout} seconds")

            output_parts = []

            if stdout:
                output_parts.append(stdout.decode("utf-8", errors="replace"))
            if stderr:
                output_parts.append(stderr.decode("utf-8", errors="replace"))

            result = "\n".join(output_parts)

            if process.returncode != 0:
                result = f"[Exit code: {process.returncode}]\n{result}"

            return result

        except ToolException:
            raise
        except Exception as e:
            raise ToolException(f"Command execution failed: {str(e)}")
