import shutil
import sys
import time
from typing import Any, Dict
from .base import BaseTool, ToolResult
from ..security.sandbox import SafeCommandExecutor


class SystemDiagTool(BaseTool):
    """Specialized SRE Diagnostic Tool for disk, memory, process and network metrics."""

    name = "system_diagnostic"
    description = (
        "Inspects system health metrics: disk space ('disk'), memory usage ('memory'), "
        "running processes ('process'), or network interfaces ('network')."
    )
    parameters = {
        "type": "object",
        "properties": {
            "target": {
                "type": "string",
                "enum": ["disk", "memory", "process", "network"],
                "description": "Subsystem to diagnose",
            },
            "path": {
                "type": "string",
                "description": "Optional path for disk diagnosis (default: '/')",
                "default": "/",
            },
        },
        "required": ["target"],
    }

    def __init__(self, executor: SafeCommandExecutor):
        self.executor = executor

    async def execute(self, **kwargs) -> ToolResult:
        target = kwargs.get("target", "disk").lower()
        path = kwargs.get("path", "/")
        start = time.perf_counter()

        try:
            if target == "disk":
                return await self._diag_disk(path, start)
            elif target == "memory":
                return await self._diag_memory(start)
            elif target == "process":
                return await self._diag_process(start)
            elif target == "network":
                return await self._diag_network(start)
            else:
                return ToolResult(
                    tool_name=self.name,
                    success=False,
                    output="",
                    error=f"Unsupported diagnostic target: {target}",
                    duration_ms=round((time.perf_counter() - start) * 1000, 2),
                )
        except Exception as exc:
            return ToolResult(
                tool_name=self.name,
                success=False,
                output="",
                error=f"Exception during {target} diagnostic: {str(exc)}",
                duration_ms=round((time.perf_counter() - start) * 1000, 2),
            )

    async def _diag_disk(self, path: str, start: float) -> ToolResult:
        # Cross-platform Python disk usage
        try:
            total, used, free = shutil.disk_usage(path)
            pct_used = round((used / total) * 100, 1)
            py_summary = (
                f"Disk Usage Summary for '{path}':\n"
                f"  Total: {round(total / (1024**3), 2)} GB\n"
                f"  Used:  {round(used / (1024**3), 2)} GB ({pct_used}%)\n"
                f"  Free:  {round(free / (1024**3), 2)} GB"
            )
        except Exception:
            py_summary = f"Could not inspect path {path} directly via shutil."

        # If on Linux or sh is available, augment with df -h
        cmd = "df -h" if sys.platform != "win32" else "wmic logicaldisk get caption,size,freespace"
        exec_res = await self.executor.execute(cmd)

        output = py_summary
        if exec_res.stdout:
            output += f"\n\nSystem Command Output ({cmd}):\n{exec_res.stdout.strip()}"

        return ToolResult(
            tool_name=self.name,
            success=True,
            output=output,
            duration_ms=round((time.perf_counter() - start) * 1000, 2),
            metadata={"target": "disk", "path": path},
        )

    async def _diag_memory(self, start: float) -> ToolResult:
        cmd = "free -m" if sys.platform != "win32" else "wmic OS get FreePhysicalMemory,TotalVisibleMemorySize /Value"
        exec_res = await self.executor.execute(cmd)

        if exec_res.exit_code == 0 and exec_res.stdout:
            output = f"Memory Diagnostic:\n{exec_res.stdout.strip()}"
            success = True
            error = None
        else:
            output = exec_res.stdout
            success = False
            error = exec_res.stderr or "Failed to query system memory metrics."

        return ToolResult(
            tool_name=self.name,
            success=success,
            output=output,
            error=error,
            duration_ms=round((time.perf_counter() - start) * 1000, 2),
            metadata={"target": "memory"},
        )

    async def _diag_process(self, start: float) -> ToolResult:
        cmd = "ps aux --sort=-%mem | head -n 10" if sys.platform != "win32" else "tasklist | head -n 15"
        exec_res = await self.executor.execute(cmd)

        return ToolResult(
            tool_name=self.name,
            success=exec_res.exit_code == 0,
            output=f"Top Resource-Consuming Processes:\n{exec_res.stdout.strip()}",
            error=exec_res.stderr if exec_res.exit_code != 0 else None,
            duration_ms=round((time.perf_counter() - start) * 1000, 2),
            metadata={"target": "process"},
        )

    async def _diag_network(self, start: float) -> ToolResult:
        cmd = "ss -tulwn" if sys.platform != "win32" else "netstat -an"
        exec_res = await self.executor.execute(cmd)

        return ToolResult(
            tool_name=self.name,
            success=exec_res.exit_code == 0,
            output=f"Network Sockets & Ports:\n{exec_res.stdout.strip()[:1500]}",
            error=exec_res.stderr if exec_res.exit_code != 0 else None,
            duration_ms=round((time.perf_counter() - start) * 1000, 2),
            metadata={"target": "network"},
        )
