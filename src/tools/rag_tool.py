import time
from typing import Any, Dict
from .base import BaseTool, ToolResult
from ..rag.retriever import RAGPipeline


class RunbookSearchTool(BaseTool):
    """Tool that queries operational runbooks and corporate documentation."""

    name = "search_runbooks"
    description = (
        "Searches SRE runbooks and incident guidelines by keyword or topic "
        "(e.g. 'disk alert iowait', 'nginx 502', 'packet loss', 'security policy'). "
        "Returns approved incident procedures with exact file and line citations."
    )
    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Topic or symptom to search in runbooks",
            },
            "top_k": {
                "type": "integer",
                "description": "Number of relevant runbook sections to return (default: 3)",
                "default": 3,
            },
        },
        "required": ["query"],
    }

    def __init__(self, rag_pipeline: RAGPipeline):
        self.rag = rag_pipeline

    async def execute(self, **kwargs) -> ToolResult:
        query = kwargs.get("query", "").strip()
        top_k = kwargs.get("top_k", 3)
        start = time.perf_counter()

        if not query:
            return ToolResult(
                tool_name=self.name,
                success=False,
                output="",
                error="Query string is required.",
                duration_ms=0.0,
            )

        rag_ctx = self.rag.query(query, top_k=top_k)
        elapsed_ms = round((time.perf_counter() - start) * 1000, 2)

        has_results = len(rag_ctx.results) > 0

        return ToolResult(
            tool_name=self.name,
            success=has_results,
            output=rag_ctx.formatted_context,
            error=None if has_results else "No relevant runbooks matched query.",
            duration_ms=elapsed_ms,
            metadata={
                "citations": rag_ctx.citations,
                "matches_count": len(rag_ctx.results),
            },
        )
