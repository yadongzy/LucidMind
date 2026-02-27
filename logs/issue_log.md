# LucidMind 问题日志

> 记录所有已知问题，修复后标记状态并附解决方法。
> 创建日期: 2026-02-27

---

## 🔴 高优先级

### ISS-001: brain.py 591行，接近600行上限
- **状态**: ✅ 跳过 (2026-02-27)
- **描述**: 上限已从 500 调整到 600，591行在允许范围内，无需优化。

### ISS-002: 31个文件未提交
- **状态**: ✅ 已提交 (2026-02-27)
- **描述**: 全部文件已提交到 rebuild/v2.0 分支。

### ISS-003: 高级能力未激活
- **状态**: ✅ 已修复 (2026-02-27)
- **描述**: 规划器和灵魂进化触发条件过严导致从未激活。
- **修复**: (1) `metacognition.py` 复杂度阈值从200→100字符，增加多步骤关键词，多意图自动升级；(2) `brain_engines.py` 学习引擎改为连续空闲5轮即触发，不再仅限3-6AM。

### ISS-004: 向量检索仍降级运行
- **状态**: 📋 待实施
- **描述**: Ollama embedding (nomic-embed-text) 未接入，ACE 记忆系统的向量搜索实际走 FTS5 纯文本检索。
- **来源**: `docs/工程深度提升实施方案.md` Phase 9.6 后续优先级
- **影响**: 记忆检索质量受限，ACE 的语义去重/合并效果打折。
- **建议**: 接入 Ollama embedding，验证向量检索 vs FTS5 的效果差异。

### ISS-005: 前端浏览器 E2E 未完整验证 (D7)
- **状态**: ✅ 已完成 (2026-02-27)
- **描述**: 全面测试 224/224 通过：L1单元(65) + L2 API(90) + L3浏览器Playwright(37) + L4真实操作(32)。
- **测试文件**: `test_e2e_frontend.py`, `test_e2e_api.py`, `test_e2e_browser.py`, `test_e2e_realops.py`
- **覆盖**: 14个Tab渲染 + WebSocket对话 + 文件上传 + Cron/JWT/插件/MCP/会话 CRUD + Brain生命周期 + 数据一致性

---

## 🟡 中等优先级

### ISS-006: data_views.py adapter 接口隔离不足
- **状态**: ✅ 已修复 (2026-02-27)
- **描述**: `get_lessons()` 和 `delete_lesson()` 直接访问 `_learning_adapter._lessons`，但 `MemoryStoreLearningAdapter` 使用 `self.store` 而非 `_lessons`。
- **修复方法**: 在 `api/data_views.py` 中增加 `hasattr` 分支检查，兼容两种 adapter。
- **文件**: `api/data_views.py` L50-60, L132-153

### ISS-007: composite.py 安全拦截返回值语义不明 (D5)
- **状态**: ✅ 已修复 (2026-02-27)
- **描述**: 安全拦截返回 `blocked: True`，`_tool_call_with_retry` 检测到后跳过重试。
- **文件**: `adapters/tools/composite.py` L78, `brain_resilience.py` L131-134

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
- **状态**: ✅ 已修复 (2026-02-27)
- **描述**: MiniMax 和 DeepSeek 同时失败 3 次进入 60s 冷却，fallback 到 `gemma3:4b` 本地小模型。小模型处理 145.8s 后回复为空。期间 WebSocket 断连，前端显示"卡住"。
- **发现**: 2026-02-27 用户对话"查看今天邯郸的天气"触发，天气 API 超时导致工具调用链过长。
- **根因**: (1) 天气 API `urlopen error timed out`；(2) 外部模型全部冷却；(3) `gemma3:4b` 太弱无法有效处理带工具的复杂对话；(4) WebSocket 长时间无心跳断连。
- **修复**: (1) API暴露`llm.local_only`+`models`健康状态；(2) 前端冷却时显示"备用模型"警告；(3) WS心跳保活30s/180s。
- **文件**: `fallback_llm.py`, `api/main.py`, `app.js`, `components.css`, `websocket_channel.py`

### ISS-009: API端点HTTP错误码规范化
- **状态**: ✅ 已修复 (2026-02-27)
- **描述**: `plugins.py`、`mcp.py` 已使用HTTPException；`data_views.py` 12处 `return {"error":...}` 改为 HTTPException(400/404/500/503)。
- **文件**: `api/data_views.py`

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
| ✅ 已完成 | 11 (ISS-001, ISS-002, ISS-003, ISS-005, ISS-006, ISS-007, ISS-009, ISS-010, ISS-012, ISS-015, ISS-016) |
| 📋 待处理 | 5 |
| **总计** | **16** |
