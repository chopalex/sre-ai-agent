from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from ..llm.provider import ToolCall
from ..tools.base import ToolResult


class AgentStep(BaseModel):
    step_number: int
    thought: str = ""
    tool_call: Optional[ToolCall] = None
    observation: Optional[ToolResult] = None
    duration_ms: float = 0.0
    was_corrected: bool = False


class AgentRunResult(BaseModel):
    session_id: str
    query: str
    final_answer: str
    steps: List[AgentStep] = Field(default_factory=list)
    citations: List[str] = Field(default_factory=list)
    success: bool = True
    total_duration_ms: float = 0.0
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
