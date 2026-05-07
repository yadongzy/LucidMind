# LucidMind 能力矩阵

> 自动更新: 2026-05-07
> 用途: 让用户和开发者清楚知道每项能力的成熟度

## 状态定义

| 状态 | 含义 |
|------|------|
| 🟢 **stable** | 生产可用，有测试覆盖 |
| 🟡 **beta** | 功能完整，可能有边缘问题 |
| 🟠 **experimental** | 可用但不稳定，API 可能变更 |
| ⚪ **planned** | 已设计，尚未实现 |
| 🔴 **degraded** | 功能存在但当前有已知问题 |

---

## 核心能力

| 能力 | 状态 | 模块 | 说明 |
|------|------|------|------|
| Brain 对话 | 🟢 stable | `brain.py` | 多模型 fallback, 工具调用, 流式输出 |
| OODA Daemon 循环 | 🟢 stable | `brain_daemon.py` | 后台观察→决策→执行→学习 |
| 工具调用 | 🟢 stable | `adapters/tools/` | CompositeToolAdapter, 30+ 内置工具 |
| 工具安全审批 | 🟢 stable | `adapters/tools/tool_safety.py` | dangerous/sensitive/safe 三级 + 审批落盘 |
| 任务队列 | 🟢 stable | `task_dispatcher.py` | 优先级队列, 自动过期, 多来源入队 |
| 命令队列 | 🟢 stable | `command_queue.py` | Chat/Daemon/Cron 三车道并发 |

## 记忆系统

| 能力 | 状态 | 模块 | 说明 |
|------|------|------|------|
| 长期记忆 (SQLite+FTS5) | 🟢 stable | `memory/store.py` | 混合搜索, 9 阶段 pipeline |
| Letta Blocks | 🟢 stable | `memory/letta_blocks.py` | 核心上下文块管理 |
| Token 预算 | 🟡 beta | `memory/token_budget.py` | ≤2000 token/轮, 自动裁剪 |
| 语义压缩 | 🟡 beta | `memory/compressor.py` | 对话压缩为精简记忆 |
| 主动遗忘 | 🟡 beta | `memory/forgetting.py` | 过期/冲突/有害记忆清理 |
| 意图感知检索 | 🟡 beta | `memory/noise_filter.py` | 意图分类 + 检索范围调节 |
| 记忆版本过滤 | 🟡 beta | `memory/store.py` Stage 9 | 过滤被取代/休眠的记忆 |
| Markdown 记忆同步 | 🟡 beta | `memory/sync.py` | 双向同步 Markdown ↔ SQLite |

## 进化引擎

| 能力 | 状态 | 模块 | 说明 |
|------|------|------|------|
| 项目体检 (7项) | 🟢 stable | `checkup/runner.py` | 测试/lint/类型/依赖/冻结文件/文档/性能 |
| 诊断分级 L0-L4 | 🟡 beta | `checkup/diagnosis.py` | 12 类问题码自动分级 |
| 自动修复 L0-L1 | 🟡 beta | `checkup/auto_repair.py` | ruff --fix + 验证闭环 |
| Codex 修复 L2-L3 | 🟠 experimental | `checkup/codex_repair.py` | Codex CLI patch + 用户确认 |
| 进化日志 | 🟢 stable | `checkup/evolution_log.py` | Bead 模式审计链 |
| 用户行为感知 | 🟡 beta | `checkup/user_behavior.py` | 模式检测 + 建议生成 |
| Brain-Codex 协商 | 🟠 experimental | `checkup/negotiation.py` | 多方案评估 + 决策记录 |
| REFLECTION.md 生成 | 🟡 beta | `checkup/reflection_gen.py` | 自动反思报告 |
| 定时自动体检 | 🟡 beta | `brain_daemon.py` | Daemon 每 50 轮触发 |

## 项目管理

| 能力 | 状态 | 模块 | 说明 |
|------|------|------|------|
| 项目状态索引 | 🟢 stable | `project_state/` | 语言/框架/入口/测试命令检测 |
| 任务报告 | 🟡 beta | `reports/task_reporter.py` | Markdown 任务报告生成 |
| 任务生命周期 | 🟡 beta | `execution/lifecycle.py` | 状态流转 + 证据收集 |
| 诊断事件收集 | 🟢 stable | `diagnostics.py` | 结构化事件 + JSONL 持久化 |
| 修复引擎 | 🟡 beta | `repair_engine.py` | 分级修复 + 回检验证 |

## 治理与安全

| 能力 | 状态 | 模块 | 说明 |
|------|------|------|------|
| 治理策略 | 🟢 stable | `governance/policy.py` | 冻结文件保护, 规则加载 |
| 决策日志 | 🟢 stable | `governance/decision_log.py` | 治理决策审计 |
| 身份系统 | 🟢 stable | `identity/` | SOUL.md + USER.md + 灵魂引擎 |
| 自省/反思 | 🟡 beta | `adapters/reflection/` | 重复检测 + 行为分析 |
| 审批记录落盘 | 🟢 stable | `tool_safety.py` | `data/audit/tool_approvals.jsonl` |

## 通道与接口

| 能力 | 状态 | 模块 | 说明 |
|------|------|------|------|
| WebSocket 通道 | 🟢 stable | `adapters/channel/websocket_channel.py` | 双向实时通信 |
| REST API | 🟢 stable | `api/` | FastAPI, 20+ 端点 |
| CLI | 🟡 beta | `cli.py` | 命令行对话 + 体检 |
| 微信/企微通道 | 🟠 experimental | `adapters/channel/` | 基础消息收发 |

## 技能与插件

| 能力 | 状态 | 模块 | 说明 |
|------|------|------|------|
| 技能发现 + 加载 | 🟢 stable | `skills/discovery.py` | manifest.json 自动发现 |
| Codex CLI 技能 | 🟡 beta | `skills/codex_cli/` | explain/review/patch/fix_tests |
| MCP 客户端 | 🟡 beta | `adapters/tools/mcp_client.py` | 外部工具服务器连接 |
| 技能自动创建 | 🟠 experimental | `skills/skill_creator.py` | LLM 生成技能代码 |
| 浏览器工具 | 🟡 beta | `adapters/tools/browser_tool.py` | 网页浏览 + 截图 |

## 前端

| 能力 | 状态 | 模块 | 说明 |
|------|------|------|------|
| Web 控制台 (Lit) | 🟡 beta | `frontend-v2/` | 对话 + 记忆 + 诊断 |
| 体检/进化 UI | ⚪ planned | — | 待实现 |

---

## 降级说明

当某项能力不可用时，系统行为:

| 场景 | 降级策略 |
|------|---------|
| 向量模型不可用 | FTS5 全文搜索回退 |
| WebSocket 断开 | Daemon 后台模式继续工作 |
| Codex CLI 不可用 | 跳过 L2+ 修复，仅执行 L0-L1 |
| LLM 主模型不可用 | FallbackLLM 自动切换备用模型 |
| MCP server 断开 | 标记工具不可用，不影响内置工具 |
