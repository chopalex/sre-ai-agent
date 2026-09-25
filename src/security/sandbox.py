import asyncio
import os
import sys
import time
from typing import Optional
from pydantic import BaseModel
from .validator import CommandValidator, SecurityResult, RiskLevel


class ExecutionResult(BaseModel):
    command: str
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: float
    timed_out: bool = False
    security: SecurityResult


class SafeCommandExecutor:
    """Safely executes validated system commands with time and memory boundaries."""

    def __init__(
        self,
        validator: Optional[CommandValidator] = None,
        timeout_seconds: int = 15,
        max_output_bytes: int = 1048576,  # 1MB
        security_enabled: bool = True,
    ):
        self.validator = validator or CommandValidator()
        self.timeout_seconds = timeout_seconds
        self.max_output_bytes = max_output_bytes
        self.security_enabled = security_enabled

    async def execute(self, command: str) -> ExecutionResult:
        """Validates security policy and executes command asynchronously."""
        # Step 1: Security Validation
        if self.security_enabled:
            sec_res = self.validator.validate(command)
            if not sec_res.allowed:
                return ExecutionResult(
                    command=command,
                    exit_code=126,  # Standard "Command cannot execute" code
                    stdout="",
                    stderr=f"SECURITY_GUARDRAIL_BLOCKED: {sec_res.reason}",
                    duration_ms=0.0,
                    timed_out=False,
                    security=sec_res,
                )
        else:
            sec_res = SecurityResult(
                allowed=True,
                risk_level=RiskLevel.SAFE,
                reason="Security bypass configured.",
                command=command,
            )

        start_time = time.perf_counter()
        timed_out = False
        stdout_text = ""
        stderr_text = ""
        exit_code = -1

        try:
            # Cross-platform execution (Windows PowerShell / Linux sh)
            if sys.platform == "win32":
                proc = await asyncio.create_subprocess_shell(
                    command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    shell=True,
                )
            else:
                proc = await asyncio.create_subprocess_shell(
                    command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    executable="/bin/bash",
                )

            try:
                stdout_data, stderr_data = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=self.timeout_seconds,
                )
                exit_code = proc.returncode if proc.returncode is not None else -1

                # Decode and truncate to max output bytes
                stdout_text = stdout_data[: self.max_output_bytes].decode("utf-8", errors="replace")
                stderr_text = stderr_data[: self.max_output_bytes].decode("utf-8", errors="replace")

            except asyncio.TimeoutError:
                timed_out = True
                exit_code = 124  # Standard timeout exit code
                stderr_text = f"Execution timed out after {self.timeout_seconds} seconds."
                try:
                    proc.kill()
                    await proc.wait()
                except ProcessLookupError:
                    pass

        except Exception as exc:
            exit_code = 1
            stderr_text = f"Execution exception: {str(exc)}"

        elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)

        return ExecutionResult(
            command=command,
            exit_code=exit_code,
            stdout=stdout_text,
            stderr=stderr_text,
            duration_ms=elapsed_ms,
            timed_out=timed_out,
            security=sec_res,
        )
