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
    box_title = "[bold green]Итоговое заключение SRE Агента[/bold green]" if res.success else "[bold red]Предупреждение / Ошибка[/bold red]"
    box_style = "green" if res.success else "red"
    console.print(Panel(Markdown(res.final_answer), title=box_title, border_style=box_style))
    console.print(
        f"[dim]📡 Провайдер: [bold cyan]{res.llm_provider}[/bold cyan] | "
        f"Модель: [bold magenta]{res.llm_model}[/bold magenta] | "
        f"Токены: {res.total_prompt_tokens} in / {res.total_completion_tokens} out | "
        f"Время: {res.total_duration_ms} мс | Сессия: {res.session_id}[/dim]\n"
    )


async def run_check():
    """Diagnostic check of LLM provider and OpenRouter connection."""
    import httpx

    console.print("\n[bold cyan]=== Диагностика подключения к LLM ===[/bold cyan]\n")
    console.print(f"[dim]• Конфигурация:[/dim] LLM_PROVIDER = [yellow]{settings.llm_provider}[/yellow]")
    console.print(f"[dim]• Базовый URL:[/dim]  {settings.openai_base_url}")
    console.print(f"[dim]• Целевая модель:[/dim] [bold]{settings.openai_model}[/bold]")

    if settings.llm_provider == "mock":
        console.print("\n[yellow]⚠️ Внимание:[/yellow] Активен режим [bold]MOCK[/bold] (локальная заглушка).")
        console.print("Запросы к внешним API не выполняются. Чтобы включить OpenRouter, укажите в `.env`:")
        console.print("  [green]LLM_PROVIDER=openrouter[/green]")
        console.print("  [green]OPENAI_API_KEY=sk-or-v1-...[/green]\n")
        return

    if settings.llm_provider == "openrouter":
        key = settings.openai_api_key or ""
        masked_key = key[:10] + "..." + key[-4:] if len(key) > 16 else "НЕ_УКАЗАН"
        console.print(f"[dim]• API Ключ:[/dim]     {masked_key}")

        if not key or "sk-or-v1-" not in key:
            console.print("[red]❌ Ошибка:[/red] Укажите валидный ключ OpenRouter (начинается с 'sk-or-v1-') в файле .env")
            return

        with console.status("[bold green]1/2 Проверка авторизации на openrouter.ai...[/bold green]"):
            try:
                async with httpx.AsyncClient(timeout=10) as client:
                    auth_resp = await client.get(
                        "https://openrouter.ai/api/v1/auth/key",
                        headers={"Authorization": f"Bearer {key}"},
                    )
            except Exception as e:
                console.print(f"[red]❌ Ошибка соединения:[/red] {e}")
                return

        if auth_resp.status_code == 200:
            kdata = auth_resp.json().get("data", {})
            free_limits = kdata.get("free_model_daily_requests", {})
            console.print(f"[green]✓ Авторизация успешна:[/green] аккаунт активен")
            if free_limits:
                console.print(
                    f"  [cyan]Лимит бесплатных запросов:[/cyan] {free_limits.get('remaining', '?')}/{free_limits.get('limit', '?')} в сутки"
                )
        else:
            console.print(f"[red]❌ Ошибка авторизации ({auth_resp.status_code}):[/red] {auth_resp.text}")
            return

        with console.status(f"[bold green]2/2 Тестовый запрос к модели {settings.openai_model}...[/bold green]"):
            payload = {
                "model": settings.openai_model,
                "messages": [{"role": "user", "content": "Привет! Ответь одним словом: 'РАБОТАЕТ'"}],
                "temperature": 0.1,
            }
            headers = {
                "Authorization": f"Bearer {key}",
                "HTTP-Referer": settings.openrouter_site_url,
                "X-Title": settings.openrouter_app_name,
            }
            try:
                import time
                t0 = time.perf_counter()
                async with httpx.AsyncClient(timeout=httpx.Timeout(20.0, connect=8.0)) as client:
                    chat_resp = await client.post(
                        "https://openrouter.ai/api/v1/chat/completions",
                        json=payload,
                        headers=headers,
                    )
                dt = round((time.perf_counter() - t0) * 1000, 2)
            except Exception as e:
                console.print(f"[red]❌ Ошибка отправки запроса:[/red] {e}")
                return

        if chat_resp.status_code == 200:
            data = chat_resp.json()
            returned_model = data.get("model", settings.openai_model)
            reply = data["choices"][0]["message"]["content"].strip()
            console.print(f"[green]✓ Успешный ответ от OpenRouter ({dt} мс)![/green]")
            console.print(f"  [dim]• Модель в ответе:[/dim] [bold magenta]{returned_model}[/bold magenta]")
            console.print(f"  [dim]• Текст ответа:[/dim]    [bold]{reply}[/bold]")
            console.print(f"\n[green]Все проверки пройдены! Агент готов к реальным запросам.[/green]")
            console.print(f"[dim]Журнал активности в реальном времени:[/dim] https://openrouter.ai/activity\n")
        elif chat_resp.status_code == 429:
            err = chat_resp.json().get("error", {}).get("message", chat_resp.text)
            console.print(f"[yellow]⚠️ Модель перегружена (HTTP 429):[/yellow] {err}")
            console.print("  [dim]Совет: бесплатный пул этой модели сейчас занят. Попробуйте модель из стабильного списка:[/dim]")
            console.print("  • [cyan]cohere/north-mini-code:free[/cyan]")
            console.print("  • [cyan]liquid/lfm-2.5-2.6b:free[/cyan]")
            console.print("  • [cyan]nvidia/nemotron-3.5-lightning:free[/cyan]")
            console.print("  • [cyan]qwen/qwen-2.5-coder-32b-instruct[/cyan] (платная, копеечная цена)")
        else:
            console.print(f"[red]❌ Модель вернула ошибку {chat_resp.status_code}:[/red] {chat_resp.text}")


def print_banner(rag: RAGPipeline):
    banner = f"""[bold cyan]Local SRE / Ops AI Agent (v0.1.0)[/bold cyan]
[dim]• Провайдер LLM:[/dim] [yellow]{settings.llm_provider}[/yellow] ({settings.ollama_model if settings.llm_provider=='ollama' else settings.openai_model})
[dim]• Режим безопасности:[/dim] [green]{'ВКЛЮЧЕН (AST/Regex Guardrails)' if settings.security_enabled else 'ОТКЛЮЧЕН'}[/green]
[dim]• Индексировано ранбуков:[/dim] [bold]{len(rag.store.chunks)} секций[/bold] из [dim]{settings.docs_dir}[/dim]
[dim]• Команды: 'exit' для выхода, '--check' для проверки связи с API, или введите инцидент[/dim]
"""
    console.print(Panel(banner, border_style="cyan"))


async def main_async():
    if "--check" in sys.argv or "-c" in sys.argv:
        await run_check()
        return

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
            if query.lower() in ("--check", "check"):
                await run_check()
                continue
            await run_query(agent, query)
        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]Сессия завершена.[/dim]")
            break


def main():
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
