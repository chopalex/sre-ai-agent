from fastapi import APIRouter, Depends, HTTPException, Request
from .schemas import (
    HealthResponse,
    AgentQueryRequest,
    AgentQueryResponse,
    AgentStepResponse,
    CommandValidateRequest,
    CommandValidateResponse,
    DirectDiagRequest,
    RAGSearchRequest,
)
from ..config import settings
from ..tools.base import ToolResult

router = APIRouter(prefix="/api/v1")


@router.get("/health", response_model=HealthResponse)
async def health_check(request: Request):
    """Health status and configuration inspection."""
    rag_pipe = request.app.state.rag
    indexed_count = len(rag_pipe.store.chunks) if rag_pipe.is_indexed else 0

    return HealthResponse(
        status="ok",
        version="0.1.0",
        llm_provider=settings.llm_provider,
        model=settings.ollama_model if settings.llm_provider == "ollama" else settings.openai_model,
        security_enabled=settings.security_enabled,
        runbooks_indexed=indexed_count,
    )


@router.post("/agent/run", response_model=AgentQueryResponse)
async def run_agent(req: AgentQueryRequest, request: Request):
    """Runs autonomous ReAct SRE agent loop on user incident query."""
    agent_loop = request.app.state.agent

    try:
        run_res = await agent_loop.run(
            query=req.query,
            session_id=req.session_id,
        )

        steps_resp = []
        for s in run_res.steps:
            steps_resp.append(
                AgentStepResponse(
                    step_number=s.step_number,
                    thought=s.thought,
                    tool_name=s.tool_call.name if s.tool_call else None,
                    tool_args=s.tool_call.arguments if s.tool_call else None,
                    tool_success=s.observation.success if s.observation else None,
                    duration_ms=s.duration_ms,
                    was_corrected=s.was_corrected,
                )
            )

        return AgentQueryResponse(
            session_id=run_res.session_id,
            query=run_res.query,
            final_answer=run_res.final_answer,
            citations=run_res.citations,
            steps=steps_resp,
            duration_ms=run_res.total_duration_ms,
            prompt_tokens=run_res.total_prompt_tokens,
            completion_tokens=run_res.total_completion_tokens,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Agent loop error: {str(exc)}")


@router.post("/security/validate", response_model=CommandValidateResponse)
async def validate_command(req: CommandValidateRequest, request: Request):
    """Validates command against AST & Regex Guardrail without executing."""
    validator = request.app.state.validator
    sec_res = validator.validate(req.command)

    return CommandValidateResponse(
        command=req.command,
        allowed=sec_res.allowed,
        risk_level=sec_res.risk_level.value,
        reason=sec_res.reason,
    )


@router.post("/rag/search")
async def search_runbooks(req: RAGSearchRequest, request: Request):
    """Directly searches SRE runbooks with citations."""
    rag_pipe = request.app.state.rag
    res = rag_pipe.query(req.query, top_k=req.top_k)

    return {
        "query": res.query,
        "citations": res.citations,
        "matches_count": len(res.results),
        "results": [
            {
                "citation": r.citation,
                "score": r.score,
                "section": r.chunk.section_title,
                "file": r.chunk.source_file,
                "lines": f"L{r.chunk.start_line}-L{r.chunk.end_line}",
                "content": r.chunk.content,
            }
            for r in res.results
        ],
    }


@router.post("/system/diagnose")
async def direct_system_diagnose(req: DirectDiagRequest, request: Request):
    """Directly invokes safe system diagnostic tool."""
    diag_tool = request.app.state.diag_tool
    tool_res: ToolResult = await diag_tool.execute(target=req.target, path=req.path)

    return {
        "target": req.target,
        "success": tool_res.success,
        "output": tool_res.output,
        "error": tool_res.error,
        "duration_ms": tool_res.duration_ms,
    }
