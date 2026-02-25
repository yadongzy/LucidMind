# LucidMind Architecture

> 清明心智 — 简洁、透明、可扩展的 AI 认知系统

---

## 核心理念

```
做两件事：
1. 想尽一切方法完成任务（Ralph 模式 — 永不放弃）
2. 想尽一切办法让自己更聪明（持续进化）

用户能看到全部思考过程。
```

---

## 六边形架构（Ports & Adapters）

```
                    ┌─── Channel Port ←── Web Console Adapter
                    │                 ←── (将来: CLI, Telegram, 飞书...)
                    │
                    ┌─── Stream Port  ←── WebSocket Adapter
                    │                 ←── (将来: Console Print...)
                    │
┌──────────────┐    │
│              │────┤─── LLM Port    ←── DeepSeek Adapter
│    Brain     │    │                ←── (将来: Ollama, OpenAI...)
│   (核心)     │    │
│              │────┤
└──────────────┘    │─── Tool Port   ←── Shell Adapter
                    │                ←── File Adapter
                    │                ←── WebSearch Adapter
                    │                ←── (将来: MCP, Browser...)
                    │
                    ├─── Memory Port  ←── JSON File Adapter
                    │                 ←── (将来: SQLite, Vector, 多层记忆)
                    │
                    └─── Learning Port ←── JSON Lessons Adapter
                                       ←── (将来: PatternDetector, 经验系统)
```

**核心规则**：Brain 只认识 Port，不认识 Adapter。

---

## 目录结构

```
LucidMind/
├── brain.py              # 核心大脑 ≤ 500 行
├── ports/                # 端口定义（纯接口）
│   ├── __init__.py
│   ├── llm_port.py       # LLM 对话接口
│   ├── tool_port.py      # 工具执行接口
│   ├── memory_port.py    # 记忆存取接口
│   ├── stream_port.py    # 思维流输出接口
│   ├── channel_port.py   # 用户输入接口
│   └── learning_port.py  # 经验学习接口
├── adapters/             # 适配器实现
│   ├── llm/
│   │   ├── __init__.py
│   │   └── deepseek.py   # DeepSeek API
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── shell.py
│   │   ├── file_ops.py
│   │   └── web_search.py
│   ├── memory/
│   │   ├── __init__.py
│   │   └── json_memory.py
│   ├── stream/
│   │   ├── __init__.py
│   │   └── websocket_stream.py
│   ├── channel/
│   │   ├── __init__.py
│   │   └── web_console.py
│   └── learning/
│       ├── __init__.py
│       └── json_lessons.py
├── identity/
│   └── SOUL.md           # AI 身份与性格
├── api/
│   ├── __init__.py
│   └── main.py           # FastAPI 入口 ≤ 200 行
├── frontend/
│   ├── console.html
│   ├── console.js
│   └── console.css
├── tests/
│   ├── __init__.py
│   └── test_brain.py
├── data/                 # 运行时数据
├── RULES.md              # 项目规则
├── ARCHITECTURE.md       # 本文件
├── PROGRESS.md           # 进度追踪
├── requirements.txt
└── pyproject.toml
```

---

## 数据流

```
用户输入 (Browser)
    │
    ▼
Channel Port ── Web Console Adapter ── WebSocket
    │
    ▼
Brain.process(user_input)
    │
    ├──→ Stream Port: emit("正在分析你的问题...")
    │
    ├──→ LLM Port: chat(messages) → LLM 决定是否需要工具
    │
    ├──→ [如果需要工具] Tool Port: execute(tool, params) → 结果
    │    │
    │    └──→ LLM Port: chat(messages + tool_result) → 最终回复
    │
    ├──→ Stream Port: emit(思考过程 + 回复)
    │
    ├──→ Memory Port: save(对话记录)
    │
    └──→ Learning Port: learn(本次经验)

用户看到：思考过程（实时流） + 最终回复
```

---

## 扩展路径

| 当前（V1） | 将来（V2+） | 扩展方式 |
|-----------|------------|---------|
| 1 个 LLM (DeepSeek) | 多 LLM + 故障转移 | 新增 LLM Adapter |
| JSON 文件记忆 | 向量检索 + 多层记忆 | 新增 Memory Adapter |
| 3 个基础工具 | MCP + 浏览器 + 自定义 | 新增 Tool Adapter |
| Web Console | CLI + Telegram + 飞书 | 新增 Channel Adapter |
| JSON 经验 | 模式检测 + 规则内化 | 新增 Learning Adapter |
| 无认知循环 | 6 阶段认知循环 | Brain 内部升级（通过 mixin） |
