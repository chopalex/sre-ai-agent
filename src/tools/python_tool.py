import io
import math
import sys
import time
from typing import Any, Dict
from contextlib import redirect_stdout, redirect_stderr
from .base import BaseTool, ToolResult


class SafePythonTool(BaseTool):
    """Executes safe Python snippets in an in-memory restricted environment."""

    name = "execute_python"
    description = (
        "Executes a Python code snippet for data analysis, parsing JSON, calculating percentages, "
        "or filtering metrics. Restricted sandbox without direct disk/network writing."
    )
    parameters = {
        "type": "object",
        "properties": {
            "code": {
                "type": "string",
                "description": "Python code snippet to execute. Output will be captured from print() statements.",
            }
        },
        "required": ["code"],
    }

    def __init__(self, timeout_seconds: int = 5):
        self.timeout_seconds = timeout_seconds

    async def execute(self, **kwargs) -> ToolResult:
        code = kwargs.get("code", "").strip()
        start = time.perf_counter()

        if not code:
            return ToolResult(
                tool_name=self.name,
                success=False,
                output="",
                error="Empty Python code snippet received.",
                duration_ms=0.0,
            )

        # Block malicious modules in python snippet
        forbidden_tokens = ["import os", "import sys", "import subprocess", "import shutil", "__import__", "open("]
        for token in forbidden_tokens:
            if token in code:
                return ToolResult(
                    tool_name=self.name,
                    success=False,
                    output="",
                    error=f"Python execution security error: '{token}' is blocked in sandbox.",
                    duration_ms=round((time.perf_counter() - start) * 1000, 2),
                )

        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()

        # Safe environment
        safe_globals = {
            "__builtins__": {
                "print": print,
                "range": range,
                "len": len,
                "int": int,
                "float": float,
                "str": str,
                "bool": bool,
                "list": list,
                "dict": dict,
                "set": set,
                "tuple": tuple,
                "sum": sum,
                "min": min,
                "max": max,
                "round": round,
                "sorted": sorted,
                "enumerate": enumerate,
                "zip": zip,
                "abs": abs,
            },
            "math": math,
        }

        try:
            with redirect_stdout(stdout_buf), redirect_stderr(stderr_buf):
                exec(code, safe_globals)

            out_text = stdout_buf.getvalue()
            err_text = stderr_buf.getvalue()

            success = True
            output = out_text.strip() if out_text.strip() else "(Code executed successfully without print output)"
            error = err_text.strip() if err_text.strip() else None

        except Exception as exc:
            success = False
            output = ""
            error = f"{type(exc).__name__}: {str(exc)}"

        elapsed_ms = round((time.perf_counter() - start) * 1000, 2)

        return ToolResult(
            tool_name=self.name,
            success=success,
            output=output,
            error=error,
            duration_ms=elapsed_ms,
        )
