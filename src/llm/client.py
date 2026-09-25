import json
import time
from typing import Any, Dict, List, Optional
import httpx
from .provider import BaseLLMClient, ChatMessage, LLMResponse, ToolCall
from ..config import Settings


class OpenAICompatibleClient(BaseLLMClient):
    """Client for vLLM, OpenAI, Groq, OpenRouter using /v1/chat/completions."""

    def __init__(
        self,
        base_url: str,
        api_key: Optional[str] = None,
        model: str = "gpt-4o-mini",
        timeout: float = 60.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key or "sk-dummy-key-for-local-vllm"
        self.model = model
        self.timeout = timeout

    async def chat(
        self,
        messages: List[ChatMessage],
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 0.1,
    ) -> LLMResponse:
        start = time.perf_counter()
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        # Format payload
        payload_messages = []
        for m in messages:
            msg_dict: Dict[str, Any] = {"role": m.role, "content": m.content}
            if m.tool_calls:
                msg_dict["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": json.dumps(tc.arguments),
                        },
                    }
                    for tc in m.tool_calls
                ]
            if m.name:
                msg_dict["name"] = m.name
            payload_messages.append(msg_dict)

        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": payload_messages,
            "temperature": temperature,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        endpoint = f"{self.base_url}/chat/completions"

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(endpoint, json=payload, headers=headers)
            elapsed_ms = round((time.perf_counter() - start) * 1000, 2)

            if resp.status_code != 200:
                raise RuntimeError(
                    f"LLM API Error ({resp.status_code}) from {endpoint}: {resp.text}"
                )

            data = resp.json()
            choice = data["choices"][0]
            msg = choice["message"]

            tool_calls: List[ToolCall] = []
            if "tool_calls" in msg and msg["tool_calls"]:
                for tc in msg["tool_calls"]:
                    fn = tc.get("function", {})
                    fn_name = fn.get("name", "")
                    fn_args_raw = fn.get("arguments", "{}")
                    try:
                        fn_args = json.loads(fn_args_raw) if isinstance(fn_args_raw, str) else fn_args_raw
                    except json.JSONDecodeError:
                        fn_args = {"raw": fn_args_raw}

                    tool_calls.append(
                        ToolCall(
                            id=tc.get("id", f"call_{int(time.time()*1000)}"),
                            name=fn_name,
                            arguments=fn_args,
                        )
                    )

            usage = data.get("usage", {})

            return LLMResponse(
                content=msg.get("content") or "",
                tool_calls=tool_calls,
                model=data.get("model", self.model),
                duration_ms=elapsed_ms,
                prompt_tokens=usage.get("prompt_tokens", 0),
                completion_tokens=usage.get("completion_tokens", 0),
                raw=data,
            )


class OllamaClient(BaseLLMClient):
    """Client for local Ollama server supporting tool calling."""

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "qwen2.5-coder:1.5b",
        timeout: float = 60.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    async def chat(
        self,
        messages: List[ChatMessage],
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 0.1,
    ) -> LLMResponse:
        start = time.perf_counter()

        payload_messages = []
        for m in messages:
            item: Dict[str, Any] = {"role": m.role, "content": m.content}
            if m.tool_calls:
                item["tool_calls"] = [
                    {
                        "function": {
                            "name": tc.name,
                            "arguments": tc.arguments,
                        }
                    }
                    for tc in m.tool_calls
                ]
            payload_messages.append(item)

        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": payload_messages,
            "stream": False,
            "options": {"temperature": temperature},
        }

        if tools:
            # Transform to Ollama tools structure
            ollama_tools = []
            for t in tools:
                if t.get("type") == "function":
                    ollama_tools.append(t)
            if ollama_tools:
                payload["tools"] = ollama_tools

        endpoint = f"{self.base_url}/api/chat"

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(endpoint, json=payload)
            elapsed_ms = round((time.perf_counter() - start) * 1000, 2)

            if resp.status_code != 200:
                raise RuntimeError(
                    f"Ollama API Error ({resp.status_code}) from {endpoint}: {resp.text}"
                )

            data = resp.json()
            msg = data.get("message", {})
            content = msg.get("content") or ""

            tool_calls: List[ToolCall] = []
            if "tool_calls" in msg and msg["tool_calls"]:
                for idx, tc in enumerate(msg["tool_calls"]):
                    fn = tc.get("function", {})
                    fn_name = fn.get("name", "")
                    fn_args = fn.get("arguments", {})
                    tool_calls.append(
                        ToolCall(
                            id=f"ollama_tc_{idx}_{int(time.time())}",
                            name=fn_name,
                            arguments=fn_args if isinstance(fn_args, dict) else {},
                        )
                    )

            return LLMResponse(
                content=content,
                tool_calls=tool_calls,
                model=data.get("model", self.model),
                duration_ms=elapsed_ms,
                prompt_tokens=data.get("prompt_eval_count", 0),
                completion_tokens=data.get("eval_count", 0),
                raw=data,
            )


class MockLLMClient(BaseLLMClient):
    """Deterministic Mock LLM for offline testing, CI, and evaluation.

    Simulates an intelligent SRE agent that:
    1. First queries runbooks via search_runbooks
    2. Then executes a safe diagnostic tool based on the alert
    3. Finally synthesizes the conclusion with citations
    """

    def __init__(self, model: str = "mock-sre-agent:latest"):
        self.model = model
        self.step = 0

    async def chat(
        self,
        messages: List[ChatMessage],
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 0.1,
    ) -> LLMResponse:
        last_msg = messages[-1] if messages else ChatMessage(role="user", content="")

        # Check if we got tool observation
        if last_msg.role == "tool":
            # If observation was search_runbooks, call diagnostic
            if "runbook" in last_msg.name or "search" in last_msg.name:
                return LLMResponse(
                    content="Изучил регламент. Согласно [runbook_disk_alert.md#L8-L14], выполняю первичную диагностику дискового пространства.",
                    tool_calls=[
                        ToolCall(
                            id="mock_tc_diag",
                            name="system_diagnostic",
                            arguments={"target": "disk", "path": "/"},
                        )
                    ],
                    model=self.model,
                    duration_ms=5.0,
                    prompt_tokens=120,
                    completion_tokens=35,
                )
            else:
                # Diagnostics done, return final answer with citation
                return LLMResponse(
                    content=(
                        "### Отчёт по диагностике системы\n\n"
                        "1. **Регламент:** Использован регламент **[runbook_disk_alert.md#L8-L14]**.\n"
                        "2. **Результаты проверки:**\n"
                        f"{last_msg.content[:400]}\n\n"
                        "3. **Рекомендации:** Опасных утечек не обнаружено, свободное место в пределах нормы. "
                        "В случае превышения 85% выполнить ротацию согласно регламенту очистки `journalctl --vacuum-time=3d`."
                    ),
                    tool_calls=[],
                    model=self.model,
                    duration_ms=5.0,
                    prompt_tokens=250,
                    completion_tokens=90,
                )

        # Initial user request
        user_text = ""
        for m in reversed(messages):
            if m.role == "user":
                user_text = m.content.lower()
                break

        # Check user intent
        if "диск" in user_text or "disk" in user_text or "мест" in user_text:
            return LLMResponse(
                content="Обнаружен запрос по проблеме с диском. Обращаюсь к базе знаний ранбуков для получения утверждённых инструкций.",
                tool_calls=[
                    ToolCall(
                        id="mock_tc_rag",
                        name="search_runbooks",
                        arguments={"query": "диск свободное место alert iowait df"},
                    )
                ],
                model=self.model,
                duration_ms=5.0,
                prompt_tokens=100,
                completion_tokens=30,
            )
        elif "nginx" in user_text or "502" in user_text:
            return LLMResponse(
                content="Запрос по сбою веб-сервера. Проверяю регламент решения 502/504 ошибок.",
                tool_calls=[
                    ToolCall(
                        id="mock_tc_nginx",
                        name="search_runbooks",
                        arguments={"query": "nginx 502 bad gateway"},
                    )
                ],
                model=self.model,
                duration_ms=5.0,
                prompt_tokens=90,
                completion_tokens=25,
            )
        elif "сеть" in user_text or "loss" in user_text or "latency" in user_text:
            return LLMResponse(
                content="Диагностика сетевых задержек. Вызываю сетевую диагностику.",
                tool_calls=[
                    ToolCall(
                        id="mock_tc_net",
                        name="system_diagnostic",
                        arguments={"target": "network"},
                    )
                ],
                model=self.model,
                duration_ms=5.0,
                prompt_tokens=90,
                completion_tokens=25,
            )
        elif "rm -rf" in user_text or "удалить" in user_text:
            # Dangerous command request simulation
            return LLMResponse(
                content="Попытка выполнить системную команду.",
                tool_calls=[
                    ToolCall(
                        id="mock_tc_blocked",
                        name="execute_bash",
                        arguments={"command": "rm -rf /tmp/test"},
                    )
                ],
                model=self.model,
                duration_ms=5.0,
            )
        else:
            # Default direct diagnostic
            return LLMResponse(
                content="Выполняю проверку состояния системы.",
                tool_calls=[
                    ToolCall(
                        id="mock_tc_default",
                        name="system_diagnostic",
                        arguments={"target": "disk"},
                    )
                ],
                model=self.model,
                duration_ms=5.0,
                prompt_tokens=80,
                completion_tokens=20,
            )


def create_llm_client(cfg: Settings) -> BaseLLMClient:
    """Factory to instantiate the appropriate LLM client."""
    provider = cfg.llm_provider.lower()

    if provider == "ollama":
        return OllamaClient(
            base_url=cfg.ollama_base_url,
            model=cfg.ollama_model,
        )
    elif provider == "vllm":
        return OpenAICompatibleClient(
            base_url=cfg.vllm_base_url,
            api_key="vllm-local",
            model=cfg.vllm_model,
        )
    elif provider in ("openai", "groq"):
        return OpenAICompatibleClient(
            base_url=cfg.openai_base_url,
            api_key=cfg.openai_api_key or "sk-dummy",
            model=cfg.openai_model,
        )
    else:
        # Default mock mode
        return MockLLMClient()
