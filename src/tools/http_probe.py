import time
from typing import Any, Dict, Optional
import httpx
from .base import BaseTool, ToolResult


class HttpProbeTool(BaseTool):
    """Probes HTTP/HTTPS endpoints for status codes, latency, and response bodies."""

    name = "http_probe"
    description = (
        "Performs an HTTP health check on a local or remote URL. "
        "Returns HTTP status code, latency in milliseconds, and headers/body snippet."
    )
    parameters = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "URL to probe (e.g. 'http://localhost:8000/health')",
            },
            "method": {
                "type": "string",
                "enum": ["GET", "HEAD", "POST"],
                "default": "GET",
            },
            "timeout_seconds": {
                "type": "number",
                "default": 5.0,
            },
        },
        "required": ["url"],
    }

    def __init__(self, default_timeout: float = 5.0):
        self.default_timeout = default_timeout

    async def execute(self, **kwargs) -> ToolResult:
        url = kwargs.get("url", "").strip()
        method = kwargs.get("method", "GET").upper()
        timeout = kwargs.get("timeout_seconds", self.default_timeout)
        start = time.perf_counter()

        if not url:
            return ToolResult(
                tool_name=self.name,
                success=False,
                output="",
                error="URL parameter is required.",
                duration_ms=0.0,
            )

        try:
            async with httpx.AsyncClient(timeout=timeout, verify=False) as client:
                res = await client.request(method=method, url=url)
                elapsed_ms = round((time.perf_counter() - start) * 1000, 2)

                body_snippet = res.text[:500] if res.text else "(empty body)"

                output = (
                    f"HTTP Probe Response for {url}:\n"
                    f"  Status:  {res.status_code} {res.reason_phrase}\n"
                    f"  Latency: {elapsed_ms} ms\n"
                    f"  Content-Type: {res.headers.get('content-type', 'unknown')}\n"
                    f"  Snippet: {body_snippet}"
                )

                return ToolResult(
                    tool_name=self.name,
                    success=res.status_code < 400,
                    output=output,
                    error=f"HTTP Error {res.status_code}" if res.status_code >= 400 else None,
                    duration_ms=elapsed_ms,
                    metadata={"status_code": res.status_code, "url": url},
                )
        except Exception as exc:
            elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
            return ToolResult(
                tool_name=self.name,
                success=False,
                output="",
                error=f"Connection error to {url}: {str(exc)}",
                duration_ms=elapsed_ms,
                metadata={"url": url},
            )
