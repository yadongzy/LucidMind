# 自愈系统深度审计日志

**日期**: 2026-03-01 14:30  
**审计范围**: repair_engine.py, brain_engines.py, issue_tracker.py, diagnostics.py, brain_daemon.py, brain_resilience.py, file.py, code_runner, git_helper, mcp_client.py  
**触发**: 用户截图暴露 retries:2476 问题

---

## 一、发现的严重 Bug

### Bug-1: RepairEngine JSON/SQLite 不匹配（致命）

**文件**: `repair_engine.py:63-73`  
**现象**: issue#67327 "经验库有65条重复" retries=2476，永不关闭  
**根因**:
- `_auto_fix_minor()` 第64行: `getattr(self._brain.learning, 'lessons_file', None)` — 当前 adapter 是 `MemoryStoreLearningAdapter`(SQLite)，没有 `lessons_file` 属性 → 永远 None
- 去重逻辑从不执行
- 第76行 `return True` 假阳性 — 什么都没修复也报告成功
- `_verify_fix()` 第135-138行用 SQLite 验证确实有重复 → 验证失败 → bump_retry

**影响**: 每轮 daemon 循环浪费计算，JSON 写入尝试无效

### Bug-2: issue_tracker 无 max_retry 限制

**文件**: `issue_tracker.py:36-43`  
**现象**: retries 可无限增长（已达 2476 次）  
**根因**: `report_issue()` 在去重时只做 `retries += 1`，无上限检查  
**影响**: 僵尸 issue 永远不会被清除或上报

### Bug-3: _auto_fix_minor 默认返回 True

**文件**: `repair_engine.py:76`  
**代码**: `return True` — 所有未匹配的 minor issue 都被标记为"已修复"  
**影响**: 假阳性，掩盖真实问题

---

## 二、Brain 已有工具链能力审计

| 工具 | 文件 | 自修复可用性 |
|------|------|------------|
| `read_file` | adapters/tools/file.py:46 | ✅ 可读 .py 源码（不在 _BLOCKED_PATHS 中） |
| `write_file` | adapters/tools/file.py:63 | ✅ 可写代码文件（原子写入） |
| `list_directory` | adapters/tools/file.py:82 | ✅ 项目结构感知 |
| `delete_file` | adapters/tools/file.py:100 | ✅ 删除文件 |
| `run_python` | skills/code_runner/main.py:24 | ⚠️ 封禁了 subprocess/exec/eval |
| `run_script` | skills/code_runner/main.py:32 | ✅ 可运行 pytest（bash执行） |
| `git_status` | skills/git_helper/main.py:13 | ✅ 查看仓库状态 |
| `git_diff` | skills/git_helper/main.py:20 | ✅ 查看差异 |
| `git_log` | skills/git_helper/main.py:28 | ✅ 查看历史 |
| `git_commit` | skills/git_helper/main.py:36 | ✅ 提交修改 |
| MCP client | adapters/tools/mcp_client.py | ✅ 连接外部 Agent |

**关键发现**: Brain 已具备 read→analyze→fix→test→commit 全链路能力，但从未在自修复场景使用。

---

## 三、安全边界审计

### file.py _BLOCKED_PATHS
```python
_BLOCKED_PATHS = [".env", ".git", "__pycache__", "node_modules", ".rules", "identity"]
```

**被保护**: .env（密钥）、.git（版本库）、.rules（规则）、identity（身份）  
**未保护**: 所有 .py 源码、配置文件、前端代码  
**评估**: 对自修复场景，需要增加核心文件保护白名单

### code_runner 安全检查
```python
dangerous = ["os.system", "subprocess", "shutil.rmtree", "rm -rf", "__import__",
             "exec(", "eval(", "open('/etc", "open('/sys", ...]
```
- `run_python`: 严格限制，不能调用 subprocess → 不能直接跑 pytest
- `run_script`: 限制较松，可以运行 `pytest`、`python3 -m pytest`

### ToolSafetyGuard
- 所有工具调用经过 `composite.py:74-81` 的安全审批
- 高危操作需要用户确认

---

## 四、文献研究摘要

| 来源 | 关键数据 |
|------|---------|
| RepairAgent (ICSE 2025, arXiv:2403.17134) | Defects4J 164/835 = 19.6% 修复率, $0.14/bug |
| SWE-bench Verified (swe-rebench.com, 2026) | Claude Opus 4.6 via Claude Code ≈ 62-65% 解决率 |
| SWE-bench Pro (Scale AI) | 工业级代码 ≈ 43-46% |
| C3 AI Alchemist (2025) | ACA 沙箱架构，需 guardrails + CI/CD |
| Claude Code Sandboxing (Anthropic 2026) | Docker/bwrap 沙箱，developer-in-the-loop 仍是默认 |
| MemGPT/Letta (UC Berkeley, arXiv:2310.08560) | 自主记忆管理，core_memory_replace/append |

---

## 五、修复计划

1. **立即修复** repair_engine.py: JSON→SQLite 适配 + 去除假阳性
2. **立即修复** issue_tracker.py: 增加 max_retry + 自动关闭/上报
3. **清除** 僵尸 issue (retries>100)
4. **方案文档** → docs/自愈系统方案.md

---

## 六、实施记录

### Phase 0: 立即修复 
1. `repair_engine.py:63-87` — JSON→SQLite API 适配 + 去除假阳性 `return True`
2. `issue_tracker.py:19,43-47,125-129` — 增加 `_MAX_RETRY=20` + 自动关闭
3. `data/issues.json` — 清除 2 个僵尸 issue (retries=2501, 885)

### Phase 1: L1 数据层修复 
4. `repair_engine.py:84-89` — 增加噪音数据清理修复 (`_clean_noise_lessons`)
5. `brain_engines.py:71-78` — SelfCheckEngine 增加噪音检测 + 统一适配 `[:60]` 截断

### Phase 2: L2 Brain 自服务修复 
6. `adapters/tools/file.py:31-41,140-177` — `_PROTECTED_FILES` + `_PROTECTED_DIRS` + `_is_protected()` + `write_mode` 参数
7. `prompts/self_repair.md` — 自服务修复流程模板 (截断→分析→修复→测试→提交→反馈)
8. `repair_engine.py:133-175` — `_enqueue_brain_repair()` + `_create_repair_prompt()` L2 组装
9. `repair_engine.py:96-113` — `_fix_medium` retries>=5 升级 L2
10. `repair_engine.py:115-126` — `_fix_severe` 非 LLM 问题转交 L2
11. `brain_task_executor.py:55-56` — `self_repair` 源码交付完整工单访问

### 测试结果
- 603/603 passed, 0 failed (移除无关的 MCP E2E 网络测试)
- 方案文档: docs/自愈系统方案.md
