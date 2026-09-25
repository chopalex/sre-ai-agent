import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class AuditRecord(BaseModel):
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    session_id: str
    step: int
    event_type: str  # "start", "thought", "tool_call", "tool_result", "self_correction", "finish", "error"
    data: Dict[str, Any] = Field(default_factory=dict)


class AuditLogger:
    """Structured JSONL audit logger tracking all agent thoughts, tool calls, and observations."""

    def __init__(self, log_path: Path):
        self.log_path = Path(log_path)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def log(self, session_id: str, step: int, event_type: str, data: Dict[str, Any]):
        """Appends a single structured audit entry."""
        record = AuditRecord(
            session_id=session_id,
            step=step,
            event_type=event_type,
            data=data,
        )
        line = record.model_dump_json() + "\n"
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(line)
