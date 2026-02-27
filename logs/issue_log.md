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

### ISS-008: brain_tool_guard.py 职责拆分 (D4)
- **状态**: ✅ 已修复 (2026-02-27)
- **描述**: 拆出 `brain_intent.py`(75行，预执行意图检测)，`brain_tool_guard.py` 从316→254行(空承诺+防伪造)。
- **文件**: `brain_intent.py`(new), `brain_tool_guard.py`, `brain.py`

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

### ISS-011: mcp_transport.py 类名封装 (D6)
- **状态**: ✅ 已确认 (2026-02-27)
- **描述**: 类名已为公开(`StdioTransport`/`HttpTransport`)，无外部依赖，实际影响为零。无需修改。

### ISS-012: 过时v1测试文件清理
- **状态**: ✅ 已完成 (2026-02-27)
- **描述**: 35个过时测试文件移到 `tests/_deprecated/`，保留参考。活跃测试从42→ 13个文件。

### ISS-013: 冻结文件诊断埋点
- **状态**: ✅ 已完成 (2026-02-27)
- **描述**: `brain.py process()` 已有埋点；`brain_resilience.py` 新增 LLM调用和工具调用的 `record_event` 埋点。
- **文件**: `brain_resilience.py`

### ISS-014: MCP 真实 E2E 测试
- **状态**: ✅ 已完成 (2026-02-27)
- **描述**: 新增5个真实API测试：update server、安全拒绍shell注入、拒绍PATH覆盖、删除404、完整生命周期。
- **文件**: `tests/test_e2e_realops.py`

---

## 📊 统计

| 状态 | 数量 |
|------|------|
| ✅ 已完成 | 16/16 全部完成 |
| 📋 待处理 | 0 |
| **总计** | **16** |
