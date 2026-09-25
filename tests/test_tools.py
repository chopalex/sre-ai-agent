import pytest
from src.security.validator import CommandValidator
from src.security.sandbox import SafeCommandExecutor
from src.tools.system_diag import SystemDiagTool
from src.tools.bash_tool import SafeBashTool
from src.tools.python_tool import SafePythonTool
from src.tools.http_probe import HttpProbeTool


@pytest.fixture
def executor():
    val = CommandValidator()
    return SafeCommandExecutor(validator=val, timeout_seconds=5)


@pytest.mark.asyncio
async def test_system_diag_disk(executor):
    tool = SystemDiagTool(executor=executor)
    res = await tool.execute(target="disk")
    assert res.success is True
    assert "Disk Usage" in res.output or "Total:" in res.output


@pytest.mark.asyncio
async def test_system_diag_cpu(executor):
    tool = SystemDiagTool(executor=executor)
    res = await tool.execute(target="cpu")
    assert res.success is True
    assert "CPU" in res.output or "Utilization" in res.output


@pytest.mark.asyncio
async def test_safe_bash_tool_allowed(executor):
    tool = SafeBashTool(executor=executor)
    res = await tool.execute(command="echo 'ops_healthcheck'")
    assert res.success is True
    assert "ops_healthcheck" in res.output


@pytest.mark.asyncio
async def test_safe_bash_tool_blocked(executor):
    tool = SafeBashTool(executor=executor)
    res = await tool.execute(command="rm -rf /")
    assert res.success is False
    assert "SECURITY_GUARDRAIL_BLOCKED" in res.error


@pytest.mark.asyncio
async def test_safe_python_tool_computation():
    tool = SafePythonTool()
    res = await tool.execute(code="total = 1000\nused = 850\nprint(f'{used/total*100}%')")
    assert res.success is True
    assert "85.0%" in res.output


@pytest.mark.asyncio
async def test_safe_python_tool_blocks_os_import():
    tool = SafePythonTool()
    res = await tool.execute(code="import os\nprint(os.listdir('.'))")
    assert res.success is False
    assert "blocked in sandbox" in res.error
