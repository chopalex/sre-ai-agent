from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class ToolResult(BaseModel):
    """Normalized result returned by any agent tool."""
    tool_name: str
    success: bool
    output: str
    error: Optional[str] = None
    duration_ms: float = 0.0
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def to_observation_text(self) -> str:
        """Format for LLM agent observation."""
        status = "SUCCESS" if self.success else "FAILURE"
        out = f"[{self.tool_name} {status}]\n{self.output}"
        if self.error:
            out += f"\nError Details: {self.error}"
        return out


class BaseTool(ABC):
    """Abstract base tool for LLM agent integration."""

    name: str
    description: str
    parameters: Dict[str, Any]

    @abstractmethod
    async def execute(self, **kwargs) -> ToolResult:
        """Executes the tool with given arguments."""
        pass

    def to_schema(self) -> Dict[str, Any]:
        """Returns JSON schema for Function Calling (OpenAI / Ollama format)."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }
