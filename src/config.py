from pathlib import Path
from typing import Literal, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration for SRE AI Agent."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # 1. LLM Provider configuration
    llm_provider: Literal["ollama", "vllm", "openai", "groq", "openrouter", "mock"] = "mock"

    # Ollama settings
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5-coder:1.5b"

    # vLLM settings
    vllm_base_url: str = "http://localhost:8000/v1"
    vllm_model: str = "Qwen/Qwen2.5-Coder-7B-Instruct"

    # OpenAI / Groq / OpenRouter settings
    openai_api_key: Optional[str] = None
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o-mini"
    openrouter_site_url: str = "https://github.com/chopalex/sre-ai-agent"
    openrouter_app_name: str = "SRE AI Agent"

    # 2. Security & Guardrails
    security_enabled: bool = True
    command_timeout_seconds: int = 15
    max_command_output_bytes: int = 1048576  # 1MB
    allow_network_tools: bool = True

    # 3. RAG Settings
    docs_dir: Path = Path("docs")
    rag_top_k: int = 3
    rag_similarity_threshold: float = 0.10

    # 4. Agent & Observability
    agent_max_steps: int = 6
    agent_verbose: bool = True
    audit_log_file: Path = Path("logs/audit.jsonl")

    # 5. API Server
    api_host: str = "0.0.0.0"
    api_port: int = 8000


settings = Settings()
