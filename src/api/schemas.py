from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "0.1.0"
    llm_provider: str
    model: str
    security_enabled: bool
    runbooks_indexed: int


class AgentQueryRequest(BaseModel):
    query: str = Field(..., description="Infrastructure incident or diagnostic query", min_length=2)
    session_id: Optional[str] = Field(None, description="Optional custom session identifier")
    max_steps: Optional[int] = Field(None, ge=1, le=15, description="Max ReAct iterations")


class AgentStepResponse(BaseModel):
    step_number: int
    thought: str
    tool_name: Optional[str] = None
    tool_args: Optional[Dict[str, Any]] = None
    tool_success: Optional[bool] = None
    duration_ms: float
    was_corrected: bool


class AgentQueryResponse(BaseModel):
    session_id: str
    query: str
    final_answer: str
    citations: List[str]
    steps: List[AgentStepResponse]
    duration_ms: float
    prompt_tokens: int
    completion_tokens: int


class CommandValidateRequest(BaseModel):
    command: str = Field(..., min_length=1)


class CommandValidateResponse(BaseModel):
    command: str
    allowed: bool
    risk_level: str
    reason: str


class DirectDiagRequest(BaseModel):
    target: str = Field("disk", pattern="^(disk|memory|process|network)$")
    path: str = "/"


class RAGSearchRequest(BaseModel):
    query: str = Field(..., min_length=2)
    top_k: int = 3
