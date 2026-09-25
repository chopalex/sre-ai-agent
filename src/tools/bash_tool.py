import time
from typing import Any, Dict
from .base import BaseTool, ToolResult
from ..security.sandbox import SafeCommandExecutor


class SafeBashTool(BaseTool):
    """Executes validated shell commands within strict security boundaries."""

    name = "execute_bash"
    description = (
        "Executes a safe shell command for SRE diagnostics (e.g. 'df -h', 'du -sh /var/log', "
        "'ss -tulwn', 'uptime', 'journalctl -n 20'). Harmful/destructive commands are strictly blocked."
    )
    parameters = {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "Shell command to execute within security sandbox",
            }
        },
        "required": ["command"],
    }

    def __init__(self, executor: SafeCommandExecutor):
        self.executor = executor

    async def execute(self, **kwargs) -> ToolResult:
        command = kwargs.get("command", "").strip()
        start = time.perf_counter()

        if not command:
            return ToolResult(
                tool_name=self.name,
                success=False,
                output="",
                error="No command provided for execution.",
                duration_ms=0.0,
            )

        res = await self.executor.execute(command)
        elapsed_ms = round((time.perf_counter() - start) * 1000, 2)

        output = res.stdout
        if res.stderr and res.exit_code != 0:
            output = f"{res.stdout}\n[STDERR]:\n{res.stderr}".strip()

        success = res.exit_code == 0 and not res.timed_out

        return ToolResult(
            tool_name=self.name,
            success=success,
            output=output if output else "(Command produced no output)",
            error=res.stderr if not success else None,
            duration_ms=elapsed_ms,
            metadata={
                "command": command,
                "exit_code": res.exit_code,
                "timed_out": res.timed_out,
                "risk_level": res.security.risk_level.value,
            },
        )
