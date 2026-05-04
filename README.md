<p align="center">
  <h1 align="center">LucidMind</h1>
  <p align="center"><strong>The self-evolving AI agent with deep memory and transparent thinking.</strong></p>
  <p align="center">
    <a href="#quick-start">Quick Start</a> &middot;
    <a href="#features">Features</a> &middot;
    <a href="#architecture">Architecture</a> &middot;
    <a href="docs/">Documentation</a> &middot;
    <a href="CHANGELOG.md">Changelog</a>
  </p>
</p>

---

LucidMind is an autonomous AI agent platform built on hexagonal architecture (Ports & Adapters). Unlike chatbot wrappers, it features a **closed-loop memory engine** with SQLite + FTS5 + vector retrieval, a **three-tier self-repair system**, **four-lane concurrent task scheduling**, and a **soul evolution engine** that makes the agent genuinely improve over time.

Use any LLM you want — DeepSeek, MiniMax, OpenAI, Anthropic, Google Gemini, Groq, Moonshot, Volcengine (Doubao), Zhipu GLM, xAI Grok, Mistral, or your own local models via Ollama. Switch providers at runtime — no code changes needed.

## Quick Start

### One-line Install (Linux / macOS)

```bash
git clone https://github.com/yadongzy/LucidMind.git
cd LucidMind
chmod +x install.sh start.sh
./install.sh        # creates venv, installs deps, builds frontend
cp .env.example .env
# edit .env — add at least DEEPSEEK_API_KEY
./start.sh          # starts server and opens browser
```

### Manual Install

```bash
python3 -m venv venv && source venv/bin/activate
pip install -e ".[all,dev]"
cp .env.example .env   # edit and fill in your API keys
python -m uvicorn api.main:app --host 0.0.0.0 --port 8765
# open http://localhost:8765
```

### Windows

```
install.bat         # double-click to install
# edit .env
start.bat           # double-click to start
```

### CLI

```bash
lucidmind           # interactive CLI (after pip install -e .)
```

## Features

| Category | What LucidMind Does |
|---|---|
| **Core** | Hexagonal architecture — Brain depends only on Ports, never on Adapters |
| **Memory** | SQLite + FTS5 full-text search + vector retrieval, ACE Bullet feedback loop, auto decay/merge/prune, Markdown memory export, query expansion (jieba + synonyms) |
| **Self-Repair** | Three-tier: L1 data cleanup → L2 Brain self-service → L3 external agent delegation |
| **Task Scheduling** | Four-lane command queue (CHAT / DAEMON / CRON / SUBAGENT), auto task decomposition, parent-child aggregation |
| **Soul Evolution** | CORE.md + SOUL.md + per-user USER.md, soul_engine auto-evolves personality, user preference extraction |
| **LLM Providers** | 11 cloud providers + local Ollama, FallbackLLMAdapter with health tracking & cooldown, runtime model switching |
| **Three-Layer Protection** | Layer 1: text-to-tool extraction, Layer 2: tool_choice="required" retry, Layer 3: stronger model fallback + soft-failure detection |
| **Tools** | 35 built-in tools + 15 skill plugins, hot-reload, ToolSafetyGuard approval system (dangerous/sensitive/safe classification) |
| **Multi-Channel** | WebSocket, Telegram, Feishu, WeCom, WeChat (GeweChat iPad protocol) |
| **MCP** | Full MCP protocol (stdio + HTTP transport), config file discovery, management API |
| **Frontend** | Vite + Lit web UI, real-time thought stream, task scheduler, plugin manager, model config, diagnostics |
| **Security** | JWT auth, tool safety approval, protected files list, command blacklist |
| **Cron** | Built-in scheduled tasks with OODA-loop engines (self-check, noise filter, soul evolution) |

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│                    Entry Points                          │
│  WebSocket    Telegram    Feishu    WeCom    WeChat  CLI │
└──────┬──────────┬──────────┬─────────┬────────┬─────┬───┘
       │          │          │         │        │     │
       ▼          ▼          ▼         ▼        ▼     ▼
┌──────────────────────────────────────────────────────────┐
│                  Brain  (brain.py)                        │
│  process() → three-layer retry → tool loop → stream      │
│                                                          │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌───────────────┐  │
│  │ LLMPort │ │ToolPort │ │MemPort  │ │ LearningPort  │  │
│  └────┬────┘ └────┬────┘ └────┬────┘ └──────┬────────┘  │
└───────┼───────────┼───────────┼──────────────┼───────────┘
        │           │           │              │
   ┌────▼────┐ ┌────▼─────┐ ┌──▼───────┐ ┌────▼──────────┐
   │Fallback │ │Composite │ │SQLite    │ │ACE Bullet     │
   │LLM      │ │Tool +    │ │+FTS5     │ │Memory Curator │
   │Adapter  │ │Plugins   │ │+Vector   │ │+Reflect       │
   └─────────┘ └──────────┘ └──────────┘ └───────────────┘
```

**Key design principles:**
- Brain only imports from `ports/` — never directly from `adapters/`
- All adapters are injected at startup (`api/startup.py`)
- Tools self-register via plugin manifest — no manual import list
- Memory, learning, and reflection are separate concerns with independent adapters

## Project Structure

```
LucidMind/
├── brain.py                # Core reasoning engine (451 lines)
├── brain_daemon.py         # Background OODA loop
├── brain_task_executor.py  # Task execution with retry & decomposition
├── brain_resilience.py     # LLM retry, memory flush, error recovery
├── command_queue.py        # Four-lane async command queue
├── task_dispatcher.py      # Task lifecycle management
├── goal_tracker.py         # Lightweight goal state tracker
├── ports/                  # 7 Port interfaces (hexagonal boundaries)
├── adapters/
│   ├── llm/                # DeepSeek, Anthropic, Fallback adapters + model catalog
│   ├── tools/              # 18 tool adapters (file, shell, browser, vision, etc.)
│   ├── memory/             # Vector store, JSON memory, user profile
│   ├── channel/            # WebSocket, Telegram, Feishu, WeCom, WeChat
│   ├── stream/             # WebSocket stream, broadcast, collector
│   └── learning/           # ACE Bullet memory curator
├── memory/
│   ├── store.py            # Core memory store (SQLite + FTS5)
│   ├── sync.py             # Session reflection & extraction
│   ├── query_expansion.py  # jieba + synonym query expansion
│   └── markdown_store.py   # Markdown memory file export
├── identity/               # Soul system (CORE.md, SOUL.md, soul_engine)
├── skills/                 # Plugin system (loader, MCP wrapper, hub)
├── api/                    # FastAPI routes (20+ routers)
├── frontend-v2/            # Vite + Lit web UI
├── tests/                  # 470+ unit tests
├── prompts/                # System prompt templates
└── docs/                   # Documentation
```

## Configuration

Copy `.env.example` to `.env` and fill in your API keys:

```bash
cp .env.example .env
```

At minimum, set one LLM provider key:
```
DEEPSEEK_API_KEY=your-key-here
```

See `.env.example` for all available configuration options (LLM providers, embedding, channels, MCP, security, etc.).

## Plugin System

Each plugin is a directory under `skills/` with a `manifest.json`:

```json
{
  "name": "my_plugin",
  "version": "1.0.0",
  "description": "My custom plugin",
  "entry": "main.py",
  "tools": ["my_tool"]
}
```

15 built-in plugins (35 tools) included. Plugins are hot-reloaded — no restart needed.

Manage via the web UI plugin page or API (`GET /api/plugins`, `POST /api/plugins/{name}/toggle`).

## MCP Integration

LucidMind supports the [Model Context Protocol](https://modelcontextprotocol.io/) for connecting to external tool servers:

```bash
# Configure MCP servers in .env
MCP_SERVERS=filesystem:/path/to/mcp-server-filesystem,memory:/path/to/mcp-server-memory
```

Manage via API: `GET /api/mcp/servers`, `POST /api/mcp/servers/{name}/restart`.

## Multi-Channel

Connect LucidMind to messaging platforms:

| Channel | Protocol | Config |
|---|---|---|
| WebSocket | Built-in | Default |
| Telegram | Bot API (polling) | `TELEGRAM_BOT_TOKEN` |
| Feishu | Webhook | `FEISHU_APP_ID`, `FEISHU_APP_SECRET` |
| WeCom | XML callback | `WECOM_CORP_ID`, `WECOM_AGENT_ID`, `WECOM_SECRET` |
| WeChat | GeweChat iPad | `GEWECHAT_BASE_URL`, `GEWECHAT_TOKEN` |

## Testing

```bash
# Unit tests (470+ tests)
python -m pytest tests/ --ignore=tests/_deprecated -v

# Quick smoke test
python -m pytest tests/test_command_queue.py tests/test_phase0_safety.py -v
```

## Comparison with Hermes Agent

| Dimension | LucidMind | Hermes Agent |
|---|---|---|
| Memory | SQLite+FTS5+Vector+ACE Bullet feedback | MEMORY.md plain text |
| Self-Repair | Three-tier (L1→L2→L3) | None |
| Task Scheduling | Four-lane command queue | Cron only |
| Soul Evolution | Auto-evolving SOUL.md + UserProfile | Static SOUL.md |
| Channels | 5 platforms | 15+ platforms |
| Tools | 35 tools + safety guard | 61 tools |

## License

MIT — see [LICENSE](LICENSE).

## Contributing

Contributions welcome! Please read the existing code style and run tests before submitting PRs.

```bash
pip install -e ".[dev]"
python -m pytest tests/ --ignore=tests/_deprecated -v
```
