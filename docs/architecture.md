# Architecture

LucidMind follows **Hexagonal Architecture** (Ports & Adapters). The Brain core depends only on abstract Port interfaces — all external integrations are injected as Adapters.

## Layer Diagram

```
┌─────────────────────────────────────────────────┐
│                   API Layer                      │
│   FastAPI (main.py) · WebSocket · REST · CLI     │
└────────────────────┬────────────────────────────┘
                     │  injects adapters
┌────────────────────▼────────────────────────────┐
│                  Brain Core                      │
│   brain.py · brain_daemon.py · brain_compact.py  │
│   brain_task_executor.py · brain_learning.py     │
│                                                  │
│   Depends ONLY on Ports:                         │
│   LLMPort · ToolPort · MemoryPort · StreamPort   │
│   LearningPort · ReflectionPort · ChannelPort    │
└────────────────────┬────────────────────────────┘
                     │  implements ports
┌────────────────────▼────────────────────────────┐
│                  Adapters                        │
│   adapters/llm/     — DeepSeek, OpenAI, etc.    │
│   adapters/tools/   — Shell, File, Web, MCP     │
│   adapters/memory/  — SQLite+FTS5+Vec, JSON     │
│   adapters/stream/  — WebSocket, CLI, Broadcast │
│   adapters/channel/ — Telegram, Discord, Feishu │
│   adapters/learning/— MemoryStore, ACE          │
└────────────────────┬────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────┐
│                  Storage                         │
│   SQLite (memory.db) · JSON files · JSONL backup │
└─────────────────────────────────────────────────┘
```

## Port Interfaces

All ports live in `ports/`:

| Port | File | Purpose |
|---|---|---|
| `LLMPort` | `ports/llm_port.py` | Chat completion (streaming) |
| `ToolPort` | `ports/tool_port.py` | Tool listing & execution |
| `MemoryPort` | `ports/memory_port.py` | Memory CRUD & search |
| `StreamPort` | `ports/stream_port.py` | Real-time output streaming |
| `LearningPort` | `ports/learning_port.py` | Session learning & ACE |
| `ReflectionPort` | `ports/reflection_port.py` | Self-reflection & rules |
| `ChannelPort` | `ports/channel_port.py` | Multi-channel messaging |

## Brain Core

The Brain is the central orchestrator:

1. **`brain.py`** — Main entry point. Receives user messages, builds context (memory retrieval, user profile, rules), calls LLM, dispatches tool calls, streams output.

2. **`brain_daemon.py`** — Background task queue. Manages autonomous task execution with priority scheduling.

3. **`brain_task_executor.py`** — Task execution engine. Handles model routing, tool grouping, failure recovery, and streaming for background tasks.

4. **`brain_compact.py`** — Context window compaction. When conversation history exceeds limits, generates a summary to maintain continuity.

5. **`brain_learning.py`** — Post-session learning. Extracts lessons from conversations and merges them into long-term memory.

## Memory System

```
memory/
├── store.py            — Core SQLite + FTS5 + Vec backend (CRUD, search)
├── store_ranking.py    — Multi-stage retrieval ranking pipeline
├── store_feedback.py   — ACE feedback, delta merge, backup
├── types.py            — MemoryResult dataclass
├── noise_filter.py     — Noise detection & retrieval skip
├── query_expansion.py  — Chinese segmentation & synonym expansion
├── block_inject.py     — Letta-style block injection
├── letta_blocks.py     — Block manager (persona, human, system)
└── markdown_store.py   — Markdown file-based memory
```

### Retrieval Pipeline

The hybrid search pipeline (in `store_ranking.py`):

1. **Adaptive Skip** — Simple greetings/commands bypass retrieval
2. **Parallel Retrieval** — Vector search + FTS5 BM25
3. **RRF Fusion** — Reciprocal Rank Fusion with vector as base
4. **Recency Boost** — Exponential decay bonus for fresh memories
5. **Importance Weight** — ACE feedback (helpful/harmful) scoring
6. **Length Normalization** — Penalize keyword-dense long entries
7. **Time Decay** — Multiplicative age penalty (evergreen collections exempt)
8. **Hard Min Score** — Final quality threshold
9. **MMR Diversity** — Maximal Marginal Relevance deduplication

### ACE (Adaptive Context Engine)

The self-improving memory system:

- **Bullet Feedback** — Each memory tracks `helpful_count` / `harmful_count`
- **Delta Merge** — New lessons are deduplicated against existing memories
- **Prune** — Memories with net-negative feedback are removed
- **Collapse Detection** — Alerts if memory count drops > 50% after merge

## Plugin System

Plugins are ToolPort implementations in `skills/`:

```
skills/
├── my_plugin/
│   ├── manifest.json   — Metadata, tool names, dependencies
│   ├── main.py         — ToolPort class implementation
│   └── README.md       — Plugin documentation
```

Create a plugin:

```bash
lucidmind create-plugin my_tool --description "My custom tool" --tools "search,create"
```

Plugins are hot-reloadable via `POST /api/plugins/reload`.

## Self-Repair System

LucidMind includes a multi-layer self-repair system (`repair_engine.py`):

- **L0 Retry** — Automatic retry with exponential backoff
- **L1 Model Fallback** — Switch to backup LLM on failure
- **L2 Context Reduction** — Trim context on token overflow
- **L3 Tool Isolation** — Quarantine failing tools

## Token Tracking

Built-in token budget management (`token_tracker.py`):

- Per-session and global token counting
- Configurable daily/monthly budgets
- Auto-switch to cheaper model at threshold
- Pause at hard limit
