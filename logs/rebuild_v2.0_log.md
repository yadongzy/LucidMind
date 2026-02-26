# rebuild/v2.0 执行日志

> 基于《工程深度提升实施方案 v1.0》逐阶段实施
> 起始分支: rebuild/v2.0 (from v1.7)
> 日期: 2026-02-26

---

## 已完成: brain.py 拆分 (Phase R1)

| 文件 | 行数 | 状态 |
|------|------|------|
| brain.py | 500 | ✅ ≤500 |
| brain_tool_guard.py | 269 | ✅ ≤300 |
| brain_perf.py | 76 | ✅ ≤200 |

改动: process() 重写返回 dict, 动态工具轮数, 90s 超时, tool_choice 支持, 冗余 import 清除

## 已完成: brain_resilience.py 升级 (Phase R2 部分)

- `_llm_call_with_retry` 新增 `tool_choice` + `llm_override` 参数
- `LLMPort.chat()` 添加 `**kwargs`
- DeepSeek + FallbackLLM 适配器透传 tool_choice
- 顶层 import re, 删除延迟导入
- brain_learning.py 添加 `_ace_reflect_and_merge` stub
- 单元测试 72/72 通过

---

## Phase 0: 安全修复 — ✅ 19/19

从 v1.8 提取: composite.py(safety_guard集成), skills/__init__.py(_validate_plugin_name), api/plugins.py+api/mcp.py(HTTP规范化)

## Phase 1: 插件三层加载 — ✅ 9/9

从 v1.8 提取: skills/loader.py, SKILL.md x3

## Phase 2: 安全体系化 — ✅ 25/25

从 v1.8 提取: skills/discovery_safety.py, skill_scanner.py增强, mcp_client.py安全验证

## Phase 3: 诊断系统 — ✅ 11/11

从 v1.8 提取: diagnostics.py, api/diagnostics.py, composite.py埋点

## Phase 4: MCP E2E — ✅ 12/12

从 v1.8 提取: mcp_client.py(超时修复+连接复用)

## Phase 5: 自动安装闭环 — ✅ EXT-4/5 10/10

registry.json 15插件, _on_tool_not_found完整链路

## Phase 6: 代码质量 — ✅ 已在v1.8文件中

cli.py模板安全, soul_engine.py去重, mcp_client.py连接复用

## Phase 7: 记忆架构 — ✅ 29/29

从 v1.8 提取: memory/(store+chunking+sync+config+types+migrate+__init__), api/memory.py

## Phase 8: ACE 集成 — ✅ 50/50

从 v1.8 提取: memory_store_adapter.py, store.py(ACE方法), sync.py(Reflector)

## Phase 9: 性能优化 — ✅ 237/237 全部通过

| 项目 | 状态 |
|------|------|
| 工具摘要化 | ✅ R1: _build_self_awareness 紧凑化 |
| Compaction 收紧 | ✅ 阈值: 2.5K/10条→3.5K截断→4K/20条摘要→保留6条 |
| 远程历史限制 | ✅ R1: _build_messages 最多20条 |
| tool_choice 透传 | ✅ R2: LLMPort+DeepSeek+Fallback **kwargs |

---

## 测试汇总

| 测试文件 | 通过 |
|----------|------|
| test_phase0_safety.py | 19/19 |
| test_phase1_loader.py | 9/9 |
| test_phase2_security.py | 25/25 |
| test_phase3_diagnostics.py | 11/11 |
| test_phase4_mcp_e2e.py | 12/12 |
| test_phase7_memory.py | 29/29 |
| test_ext4_ext5.py | 10/10 |
| test_phase8_ace.py | 50/50 |
| test_brain.py | 通过 |
| test_advanced.py | 通过 |
| test_s3_tools.py | 通过 |
| test_tools.py | 通过 (1 skip: 网络) |
| test_s9_acceptance.py | 通过 |
| test_cron_heartbeat.py | 通过 |
| **总计** | **237 passed, 0 failed** |
