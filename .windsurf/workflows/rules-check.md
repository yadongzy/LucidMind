---
description: 每次收到任务时强制读取全部项目规则（LucidMind规则检查）
---

## 强制规则检查流程

每次收到用户任务时，必须按以下步骤执行，不可跳过。

### Step 1: 读取全部规则文件

// turbo
1. 读取 `.rules/README.md` 确认规则清单

// turbo
2. 读取全部规则文件（00 到 17），逐个读取：
   - `.rules/00-existence.md`
   - `.rules/01-architecture.md`
   - `.rules/02-walking-skeleton.md`
   - `.rules/03-code-limits.md`
   - `.rules/04-testing.md`
   - `.rules/05-locking.md`
   - `.rules/06-extension.md`
   - `.rules/07-logging.md`
   - `.rules/08-honesty.md`
   - `.rules/09-benchmark.md`
   - `.rules/10-code-guard.md`
   - `.rules/11-testing-iron.md`
   - `.rules/12-optimal-first.md`
   - `.rules/13-code-quality.md`
   - `.rules/14-teaching.md`
   - `.rules/15-file-protection.md`
   - `.rules/16-change-declaration.md`
   - `.rules/17-ai-discipline.md`

### Step 2: 检查敏感操作

3. 判断本次任务是否涉及以下敏感操作：
   - [ ] 修改 brain.py / brain_daemon.py / brain_meta.py
   - [ ] 修改 api/main.py
   - [ ] 修改 task_dispatcher.py
   - [ ] 修改 ports/ 下的接口文件
   - [ ] 修改 frontend/ 或 frontend-v2/ 下的文件
   - [ ] 删除任何文件
   - [ ] 修改路由指向或静态文件挂载
   - [ ] 修改 .rules/ 下的规则文件

   如果涉及任何一项 → **必须先声明原因并等待用户确认**

### Step 3: 声明计划

4. 向用户简要汇报：
   ```
   规则已检查（18条），本次任务涉及规则：[列出编号]
   计划修改文件：[列出文件名]
   是否涉及核心文件：是/否
   [如涉及核心文件] 修改原因：[说明]
   ```

### Step 4: 执行任务

5. 获得确认后（或不涉及核心文件时直接）执行任务

### Step 5: 执行后验证

// turbo
6. 运行 pytest：`python -m pytest tests/test_brain.py -v`

7. **必须更新 CHANGELOG.md** — 记录本次改动（新增/修复/变更/删除）
8. 将结果记录到 logs/

### Step 6: 诚实自查

8. 汇报前自查：
   - 说"已完成"的功能是否真的完成？
   - 说"测试通过"是否真的运行了？
   - 有没有降级运行却说"已完成"？
   - 有没有用API测试冒充浏览器测试？
