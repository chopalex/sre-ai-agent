import asyncio
import sys
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.markdown import Markdown

from .config import settings
from .security.validator import CommandValidator
from .security.sandbox import SafeCommandExecutor
from .tools import SystemDiagTool, SafeBashTool, SafePythonTool, HttpProbeTool, RunbookSearchTool
from .rag.retriever import RAGPipeline
from .llm.client import create_llm_client
from .logger.audit import AuditLogger
from .agent.loop import AgentLoop

# Ensure UTF-8 output on Windows consoles
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

console = Console()


def create_agent():
    validator = CommandValidator()
    executor = SafeCommandExecutor(
        validator=validator,
        timeout_seconds=settings.command_timeout_seconds,
        max_output_bytes=settings.max_command_output_bytes,
        security_enabled=settings.security_enabled,
    )

    rag = RAGPipeline(
        docs_dir=settings.docs_dir,
        top_k=settings.rag_top_k,
        threshold=settings.rag_similarity_threshold,
    )
    rag.index()

    tools = [
        SystemDiagTool(executor=executor),
        SafeBashTool(executor=executor),
        SafePythonTool(timeout_seconds=5),
        HttpProbeTool(default_timeout=5.0),
        RunbookSearchTool(rag_pipeline=rag),
    ]

    llm = create_llm_client(settings)
    audit = AuditLogger(log_path=settings.audit_log_file)

    agent = AgentLoop(
        llm=llm,
        tools=tools,
        audit_logger=audit,
        max_steps=settings.agent_max_steps,
    )

    return agent, rag


async def run_query(agent: AgentLoop, query: str):
    console.print(f"\n[bold cyan][Инженер]:[/bold cyan] {query}\n")

    with console.status("[bold green]Агент анализирует инцидент и подбирает инструменты...[/bold green]"):
        res = await agent.run(query)

    # Render steps table
    if res.steps:
        table = Table(title="[bold yellow]Журнал выполнения шагов (ReAct Loop)[/bold yellow]", show_header=True)
        table.add_column("Шаг", style="cyan", width=6)
        table.add_column("Инструмент", style="magenta", width=18)
        table.add_column("Статус", width=12)
        table.add_column("Время (мс)", justify="right", width=12)

        for s in res.steps:
            tool_name = s.tool_call.name if s.tool_call else "-"
            if s.observation:
                status = "[green]SUCCESS[/green]" if s.observation.success else "[red]FAILURE[/red]"
            else:
                status = "[blue]THOUGHT[/blue]"

            if s.was_corrected:
                status += " [yellow](Self-Correct)[/yellow]"

            table.add_row(
                str(s.step_number),
                tool_name,
                status,
                str(s.duration_ms),
            )
        console.print(table)

    # Render citations if any
    valid_citations = [c for c in res.citations if c and c.strip()]
    if valid_citations:
        citations_text = " • ".join(valid_citations)
        console.print(Panel(citations_text, title="[bold blue]Использованные цитаты из Runbooks[/bold blue]", border_style="blue"))

    # Render final answer
    console.print(Panel(Markdown(res.final_answer), title="[bold green]Итоговое заключение SRE Агента[/bold green]", border_style="green"))
    console.print(f"[dim]Общее время: {res.total_duration_ms} мс | Сессия: {res.session_id}[/dim]\n")


def print_banner(rag: RAGPipeline):
    banner = f"""[bold cyan]Local SRE / Ops AI Agent (v0.1.0)[/bold cyan]
[dim]• Провайдер LLM:[/dim] [yellow]{settings.llm_provider}[/yellow] ({settings.ollama_model if settings.llm_provider=='ollama' else settings.openai_model})
[dim]• Режим безопасности:[/dim] [green]{'ВКЛЮЧЕН (AST/Regex Guardrails)' if settings.security_enabled else 'ОТКЛЮЧЕН'}[/green]
[dim]• Индексировано ранбуков:[/dim] [bold]{len(rag.store.chunks)} секций[/bold] из [dim]{settings.docs_dir}[/dim]
[dim]• Команды: 'exit' для выхода, или введите инцидент (напр. 'Заканчивается диск', 'nginx 502', 'rm -rf /')[/dim]
"""
    console.print(Panel(banner, border_style="cyan"))


async def main_async():
    agent, rag = create_agent()

    if len(sys.argv) > 1:
        query = " ".join(sys.argv[1:])
        await run_query(agent, query)
        return

    print_banner(rag)

    while True:
        try:
            query = console.input("[bold green]sre-agent>[/bold green] ").strip()
            if not query:
                continue
            if query.lower() in ("exit", "quit", "q"):
                console.print("[dim]Выход.[/dim]")
                break
            await run_query(agent, query)
        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]Сессия завершена.[/dim]")
            break


def main():
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
