from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ..config import settings
from ..security.validator import CommandValidator
from ..security.sandbox import SafeCommandExecutor
from ..tools import SystemDiagTool, SafeBashTool, SafePythonTool, HttpProbeTool, RunbookSearchTool
from ..rag.retriever import RAGPipeline
from ..llm.client import create_llm_client
from ..logger.audit import AuditLogger
from ..agent.loop import AgentLoop
from .routes import router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown initialization."""
    # 1. Initialize Security
    validator = CommandValidator()
    executor = SafeCommandExecutor(
        validator=validator,
        timeout_seconds=settings.command_timeout_seconds,
        max_output_bytes=settings.max_command_output_bytes,
        security_enabled=settings.security_enabled,
    )

    # 2. Initialize RAG Knowledge base
    rag = RAGPipeline(
        docs_dir=settings.docs_dir,
        top_k=settings.rag_top_k,
        threshold=settings.rag_similarity_threshold,
    )
    rag.index()

    # 3. Initialize Tools
    diag_tool = SystemDiagTool(executor=executor)
    bash_tool = SafeBashTool(executor=executor)
    py_tool = SafePythonTool(timeout_seconds=5)
    http_tool = HttpProbeTool(default_timeout=5.0)
    rag_tool = RunbookSearchTool(rag_pipeline=rag)

    all_tools = [diag_tool, bash_tool, py_tool, http_tool, rag_tool]

    # 4. Initialize LLM Client & Audit Logger
    llm = create_llm_client(settings)
    audit_logger = AuditLogger(log_path=settings.audit_log_file)

    # 5. Initialize ReAct Agent
    agent = AgentLoop(
        llm=llm,
        tools=all_tools,
        audit_logger=audit_logger,
        max_steps=settings.agent_max_steps,
    )

    # Save to app state
    app.state.validator = validator
    app.state.executor = executor
    app.state.rag = rag
    app.state.diag_tool = diag_tool
    app.state.tools = all_tools
    app.state.llm = llm
    app.state.audit_logger = audit_logger
    app.state.agent = agent

    yield


app = FastAPI(
    title="SRE / Ops AI Agent API",
    description="Production-grade API wrapper for Local LLM Agent with Security Guardrails and RAG Runbooks.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
