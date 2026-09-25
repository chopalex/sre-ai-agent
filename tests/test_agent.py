from pathlib import Path
import pytest
from src.security.validator import CommandValidator
from src.security.sandbox import SafeCommandExecutor
from src.tools.system_diag import SystemDiagTool
from src.tools.bash_tool import SafeBashTool
from src.tools.rag_tool import RunbookSearchTool
from src.rag.retriever import RAGPipeline
from src.llm.client import MockLLMClient
from src.logger.audit import AuditLogger
from src.agent.loop import AgentLoop


@pytest.fixture
def agent_suite(tmp_path):
    # Setup sample runbooks
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "runbook_disk_alert.md").write_text(
        "# Disk Alert Runbook\n\n## Первичная диагностика\nИспользуйте `df -h` для проверки.",
        encoding="utf-8",
    )

    rag = RAGPipeline(docs_dir=docs_dir, top_k=2)
    rag.index()

    val = CommandValidator()
    executor = SafeCommandExecutor(validator=val)

    tools = [
        SystemDiagTool(executor=executor),
        SafeBashTool(executor=executor),
        RunbookSearchTool(rag_pipeline=rag),
    ]

    llm = MockLLMClient()
    audit_file = tmp_path / "audit.jsonl"
    audit = AuditLogger(log_path=audit_file)

    agent = AgentLoop(llm=llm, tools=tools, audit_logger=audit, max_steps=5)
    return agent, audit_file


@pytest.mark.asyncio
async def test_agent_full_loop_and_citations(agent_suite):
    agent, audit_file = agent_suite

    res = await agent.run("На сервере заканчивается место на диске!")

    assert res.success is True
    assert len(res.steps) >= 2
    # Verify citations are captured
    assert len(res.citations) > 0 or "runbook_disk_alert" in res.final_answer
    assert "Отчёт" in res.final_answer or "диагностике" in res.final_answer

    # Verify audit log was recorded
    assert audit_file.exists()
    lines = audit_file.read_text(encoding="utf-8").splitlines()
    assert len(lines) >= 3


def test_openrouter_client_factory():
    from src.config import Settings
    from src.llm.client import create_llm_client, OpenAICompatibleClient

    cfg = Settings(
        llm_provider="openrouter",
        openai_api_key="sk-or-test-key",
        openai_model="meta-llama/llama-3.3-70b-instruct",
    )
    client = create_llm_client(cfg)
    assert isinstance(client, OpenAICompatibleClient)
    assert client.base_url == "https://openrouter.ai/api/v1"
    assert client.api_key == "sk-or-test-key"
    assert client.model == "meta-llama/llama-3.3-70b-instruct"
    assert "HTTP-Referer" in client.extra_headers
    assert "X-Title" in client.extra_headers
