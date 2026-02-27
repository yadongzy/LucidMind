# LucidMind 问题日志

> 记录所有已知问题，修复后标记状态并附解决方法。
> 创建日期: 2026-02-27

---

## 🔴 高优先级

### ISS-001: brain.py 591行，接近600行上限
- **状态**: 📋 待优化
- **描述**: brain.py 从 v1.7 的 663 行拆分到 500 行后，因 D9/D10/D16 等修复又膨胀到 591 行。上限已从 500 调整到 600，但仍接近边界。
- **影响**: 后续新增功能可能超限，违反 R3 规则。
- **建议**: 审查 brain.py 是否有可进一步拆出的逻辑（如工具进度推送、超时处理）。

### ISS-002: 31个文件未提交
- **状态**: 📋 待处理
- **描述**: D8-D16 修复、前端审计修复、data_views.py 兼容性修复等均在 working tree 中未 commit。
- **影响**: 代码丢失风险；无法回溯具体变更。
- **建议**: 尽快 `git add . && git commit` 打 tag。

### ISS-003: 高级能力未激活
- **状态**: 📋 待分析
- **描述**: 审计报告中 L8 规划器(0%触发)、L9 灵魂进化(0次进化) 至今未改善。
- **来源**: `docs/LucidMind大脑能力诚实审计报告.md`
- **影响**: 系统 Daemon 跑着但高级自主能力从未生效，属于死功能。
- **建议**: 评估是否需要这些功能；如需要则添加触发条件和测试。

### ISS-004: 向量检索仍降级运行
- **状态**: 📋 待实施
- **描述**: Ollama embedding (nomic-embed-text) 未接入，ACE 记忆系统的向量搜索实际走 FTS5 纯文本检索。
- **来源**: `docs/工程深度提升实施方案.md` Phase 9.6 后续优先级
- **影响**: 记忆检索质量受限，ACE 的语义去重/合并效果打折。
- **建议**: 接入 Ollama embedding，验证向量检索 vs FTS5 的效果差异。

### ISS-005: 前端浏览器 E2E 未完整验证 (D7)
- **状态**: 🔧 进行中
- **描述**: 237 个 pytest mock 测试全通过，29 个 API E2E 测试通过，但前端真实浏览器交互未自动化验证。
- **来源**: `logs/rebuild_v2.0_log.md` D7
- **影响**: UI 交互 Bug（如按钮无响应、数据未渲染）无法自动发现。
- **建议**: 分两阶段：A) 补全 API 回归测试；B) Playwright 浏览器 E2E。

---

## 🟡 中等优先级

### ISS-006: data_views.py adapter 接口隔离不足
- **状态**: ✅ 已修复 (2026-02-27)
- **描述**: `get_lessons()` 和 `delete_lesson()` 直接访问 `_learning_adapter._lessons`，但 `MemoryStoreLearningAdapter` 使用 `self.store` 而非 `_lessons`。
- **修复方法**: 在 `api/data_views.py` 中增加 `hasattr` 分支检查，兼容两种 adapter。
- **文件**: `api/data_views.py` L50-60, L132-153

### ISS-007: composite.py 安全拦截返回值语义不明 (D5)
- **状态**: 📋 记录待优化
- **描述**: 被 ToolSafetyGuard 拦截时返回 `{"success": False}`，Brain 当作工具执行失败处理并重试。
- **影响**: 安全拦截被当失败重试 2 次，浪费资源。
- **建议**: 返回值增加 `blocked: True`，`_tool_call_with_retry` 检测后跳过重试。

### ISS-008: brain_tool_guard.py 职责混合 (D4)
- **状态**: 📋 记录待优化
- **描述**: 文件包含三个不同功能：空承诺三层防护、预执行意图检测、防伪造守卫。270 行未超限但命名不准。
- **建议**: 后续可拆为 `brain_intent.py`（预执行）+ `brain_tool_guard.py`（防护+防伪造）。

### ISS-015: /api/memory/stats 和 /api/memory/list 被 data_views 路由遮蔽
- **状态**: ✅ 已修复 (2026-02-27)
- **描述**: `data_views.py` 的 `/api/memory/{session_id}` 路由匹配了 `stats` 和 `list` 作为 session_id，导致 `memory.py` 的 `/api/memory/stats` 和 `/api/memory/list` 端点无法访问。
- **发现**: E2E 测试中发现，`GET /api/memory/stats` 返回 `{"messages": [], "session_id": "stats"}` 而非记忆统计。
- **修复方法**: 在 `api/main.py` 中将 `memory_router` 注册顺序移到 `data_views.router` 之前，添加注释标记。
- **文件**: `api/main.py` L36-40

### ISS-016: 所有外部LLM冷却时大脑卡住 + WebSocket断连
- **状态**: 📋 待优化
- **描述**: MiniMax 和 DeepSeek 同时失败 3 次进入 60s 冷却，fallback 到 `gemma3:4b` 本地小模型。小模型处理 145.8s 后回复为空。期间 WebSocket 断连，前端显示"卡住"。
- **发现**: 2026-02-27 用户对话"查看今天邯郸的天气"触发，天气 API 超时导致工具调用链过长。
- **根因**: (1) 天气 API `urlopen error timed out`；(2) 外部模型全部冷却；(3) `gemma3:4b` 太弱无法有效处理带工具的复杂对话；(4) WebSocket 长时间无心跳断连。
- **建议**: 
  - 冷却期内前端应提示"当前使用备用模型，响应可能较慢"
  - 工具超时应更快返回错误（当前 urlopen 默认超时太长）
  - WebSocket 增加超时重连机制

### ISS-009: Phase 0.3 剩余端点 HTTP 规范化未完成
- **状态**: 📋 待处理
- **描述**: 仅修改了 `hub/install` 1 个端点，`api/plugins.py` 其余 5 个 + `api/mcp.py` 6 个端点未规范化为标准 HTTP 错误码。
- **来源**: `docs/工程深度提升实施方案.md` Phase 0.3

### ISS-010: E2E test 断言对 daemon 字段名的错误假设
- **状态**: ✅ 已修复 (2026-02-27)
- **描述**: `test_brain_status_has_daemon_fields` 断言 `interval` 和 `auto_ask`，但 daemon `get_status()` 实际返回 `running` 和 `paused`。
- **修复方法**: 修改测试断言为 `running` 和 `paused`。
- **文件**: `tests/test_e2e_frontend.py` L206-214

---

## 🟢 低优先级

### ISS-011: mcp_transport.py 类名变更破坏封装 (D6)
- **状态**: 📋 可接受
- **描述**: 拆分时 `_StdioTransport`（私有）改为 `StdioTransport`（公开）。当前无外部依赖，实际影响为零。

### ISS-012: 42 个测试文件中大量历史遗留
- **状态**: 📋 待清理
- **描述**: `test_s20_s23_browser.py`、`test_s30_s33_browser.py` 等旧浏览器测试可能已过时，部分可能无法运行。
- **建议**: 审查后删除不再需要的测试文件，或标记 skip。

### ISS-013: Phase 3.2 冻结文件诊断埋点未完成
- **状态**: 📋 待处理
- **描述**: brain.py process()、brain_resilience.py、API 中间件等冻结文件中的诊断埋点未注入。
- **影响**: 诊断系统覆盖面不完整。

### ISS-014: Phase 4.1 真实 MCP E2E 测试仅 mock
- **状态**: 📋 待处理
- **描述**: MCP 测试使用 mock，未用真实 MCP Server 验证。
- **影响**: MCP 集成可能存在未发现的问题。

---

## 📊 统计

| 状态 | 数量 |
|------|------|
| ✅ 已修复 | 3 (ISS-006, ISS-010, ISS-015) |
| 🔧 进行中 | 1 (ISS-005) |
| 📋 待处理 | 11 |
| **总计** | **15** |
