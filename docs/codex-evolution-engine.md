# LucidMind × Codex 自我进化引擎设计文档

> 版本: 0.1.0 | 日期: 2026-05-07
> 定位: LucidMind 的核心差异化能力 — 不只是对话 AI，而是自我进化的项目智能体

---

## 1. 核心理念

### 1.1 一句话定义

**LucidMind 是项目的长期大脑和进化编排器；Codex 是它的高精度执行双手。**

两者的关系不是"调用工具"，而是"大脑指挥双手"：

```
用户意图 → LucidMind（理解 + 决策 + 记忆） → Codex（执行 + 验证）→ 结果回流 → 记忆沉淀
```

### 1.2 为什么不只是"体检"

体检只是感知层。真正的价值链是完整的进化闭环：

| 阶段 | 能力 | 产物 |
|------|------|------|
| **感知** | 发现问题、感知用户习惯、监控代码健康 | 体检报告、用户行为模式 |
| **诊断** | 分析根因、评估影响、对比历史 | 诊断报告、置信度标注 |
| **决策** | 制定方案、治理审查、用户确认 | 执行计划、检查点 |
| **执行** | Codex patch、测试、验证 | 代码变更、测试结果 |
| **学习** | 记录什么有效/无效、更新策略 | 项目记忆、进化日志 |

### 1.3 行业对标与差异

| 产品/概念 | 做什么 | LucidMind 差异 |
|-----------|--------|---------------|
| **BugStack** (自愈代码库) | 5阶段: 错误捕获→上下文构建→修复生成→验证→部署 | LucidMind 不限于修 bug，还主动优化、升级、进化 |
| **Ralph Loop** (Addy Osmani) | 原子任务循环: 选任务→实现→验证→提交→重置上下文 | LucidMind 有长期记忆，不需要每轮重置 |
| **HyperAgents** (2026 论文) | 元级自修改 Agent，自动发明改进策略 | LucidMind 保持人在回路，安全第一 |
| **Devin / Codex Web** | 独立编程 Agent | LucidMind 是编排层，Codex 是执行层之一 |
| **AGENTS.md 模式** | 跨会话积累学习 | LucidMind 已有结构化项目记忆（更强） |

**关键差异**: 上述方案要么只修 bug（BugStack），要么无长期记忆（Ralph），要么缺乏安全边界（HyperAgents）。LucidMind 独特的是：**长期记忆 + 治理门控 + 用户习惯感知 + 多执行器编排**。

---

## 2. 架构设计

### 2.1 分层架构

```
┌─────────────────────────────────────────────────────────┐
│                    用户交互层                              │
│   对话 / 驾驶舱 / CLI / 定时触发 / Git Hook               │
└──────────────────────┬──────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────┐
│                 Brain (编排层)                             │
│   需求理解 → 意图翻译 → 任务分解 → 执行调度 → 结果汇总    │
│   ┌──────────┐  ┌──────────┐  ┌──────────┐              │
│   │ 记忆检索  │  │ 治理审查  │  │ 安全分级  │              │
│   └──────────┘  └──────────┘  └──────────┘              │
└──────────────────────┬──────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────┐
│                执行器层 (Executor Pool)                    │
│   ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐   │
│   │ Codex   │  │ Claude  │  │ Local   │  │ Shell   │   │
│   │ CLI     │  │ Code    │  │ LLM     │  │ Tools   │   │
│   └─────────┘  └─────────┘  └─────────┘  └─────────┘   │
└──────────────────────┬──────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────┐
│                验证层 (Quality Gates)                      │
│   测试套件 / Lint / 类型检查 / Benchmark / 回归检测        │
└──────────────────────┬──────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────┐
│                记忆层 (Memory & Learning)                  │
│   项目记忆 / 用户偏好 / 进化日志 / 失败教训                │
└─────────────────────────────────────────────────────────┘
```

### 2.2 Codex 能力画像 (Capability Profile)

LucidMind 维护一份 Codex 能力模型，决定什么任务交给谁：

```json
{
  "codex": {
    "strengths": ["code_generation", "refactoring", "test_writing", "bug_fixing", "code_review"],
    "weaknesses": ["architectural_decisions", "business_logic_understanding", "user_intent"],
    "limits": {
      "max_file_size": "~5000 lines",
      "context_window": "large but finite",
      "write_safety": "requires approval for destructive ops"
    },
    "best_for": [
      "精准的代码修改和补丁",
      "跨文件重构（重命名、抽提、解耦）",
      "写测试、修测试",
      "代码风格统一化",
      "安全漏洞修复"
    ],
    "not_for": [
      "架构决策（需要项目全局视角）",
      "需求理解（需要用户上下文）",
      "长期规划（需要项目记忆）"
    ]
  }
}
```

### 2.3 需求翻译层 (Intent Translator)

用户说的话往往是模糊的。LucidMind 的核心价值之一是**把模糊意图翻译成 Codex 能精准执行的指令**。

```
用户: "让首页加载快一点"

LucidMind 内部处理:
1. [记忆检索] 首页 = frontend-v2/src/ui/app.js, bundle 297KB
2. [项目分析] 所有 view 都是同步 import，无代码分割
3. [方案生成] 路由懒加载 + 减少首屏组件
4. [翻译为 Codex prompt]:
   "Refactor frontend-v2/src/ui/app.js:
    1. Convert static imports of view modules to dynamic import()
    2. Add route-based code splitting for each view
    3. Keep all existing functionality unchanged
    4. Follow existing code style (lit-html, ES modules)"
5. [安全分级] L2 常规变更 → 需用户确认
6. [执行] codex_patch
7. [验证] npm run build → 检查 bundle 大小变化
8. [记忆] "路由懒加载减少首屏加载 35%" → 写入项目记忆
```

---

## 3. 五大核心能力

### 3.1 能力一：项目体检 (Health Check)

**目的**: 全面了解项目当前状态，发现潜在问题。

**触发方式**:
- 对话: "给项目做个全面体检"
- 驾驶舱: "开始体检" 按钮
- 定时: 每周自动执行
- Git Hook: 每次 PR 自动触发

**检查项**:

| 检查 | 工具 | 输出 |
|------|------|------|
| 项目结构分析 | ProjectStateIndexer | 语言/框架/入口/依赖关系图 |
| 代码质量审查 | codex_review × 核心文件 | 逐模块评分 + 问题列表 |
| 架构评估 | codex_explain × 核心目录 | 分层合理性、循环依赖 |
| 测试健康度 | pytest + 覆盖率分析 | 通过率、覆盖率、薄弱区域 |
| 安全扫描 | GovernancePolicy + codex_review | 敏感文件、权限、漏洞 |
| 依赖健康 | pip audit + npm audit | 过期依赖、已知漏洞 |
| 性能基准 | benchmark scripts | 响应时间、内存占用 |

**输出**: 体检报告（Markdown），每条结论带置信度：
- 🟢 **已验证** — 有测试/数据支持
- 🟡 **推断** — AI 分析结论，需人工确认
- 🔴 **高风险** — 强烈建议立即处理

### 3.2 能力二：智能诊断 (Diagnosis)

**目的**: 深入分析某个具体问题的根因。

**触发方式**: "为什么 brain.py 的 process() 这么慢？"

**流程**:
1. Brain 检索相关记忆和上下文
2. codex_explain 分析目标代码
3. 对比历史变更（git log）
4. 生成诊断报告：根因、影响范围、修复建议

### 3.3 能力三：安全进化 (Safe Evolution)

**目的**: 不只发现问题，还安全地修复它们。

**安全分级协议**:

| 级别 | 改动范围 | 权限策略 | 回滚机制 |
|------|---------|---------|---------|
| **L0 静默** | 文档、注释、日志格式 | 自动执行，事后通知 | git revert |
| **L1 轻量** | 新增文件、新增测试 | 自动执行，需通知 | 删除新文件 |
| **L2 常规** | 修改非核心模块 | 需用户确认 | git branch + revert |
| **L3 重大** | 修改核心模块 (brain.py, api/) | 完整方案 + 影响分析 + 用户确认 | 快照备份 + branch |
| **L4 架构** | 重构依赖关系、改 schema | 分步方案 + checkpoint + 灰度 | 完整回滚计划 |

**L3/L4 流程**:
```
1. Brain 生成完整方案 → 展示给用户
2. 用户确认 → 创建 feature branch
3. Codex 在 branch 上执行
4. 自动跑全量测试
5. 测试通过 → 通知用户 review
6. 用户确认 merge → 合入主分支
7. 失败 → 自动回滚 → 记录失败原因
```

### 3.4 能力四：用户感知与主动进化

**目的**: 感知用户使用模式，主动提出改进建议。

**感知来源**:
- 对话频率和主题分布
- 用户频繁执行的手动操作
- 功能使用率（哪些页面/按钮从未使用）
- 错误和异常日志
- 用户反馈（显式 + 隐式）

**进化循环**:
```
感知 → 提议 → 协商 → 确认 → 执行 → 验证 → 记忆
```

**示例**:
```
[感知] 用户过去7天每天都手动搜索对话3次以上
[提议] "观察到您频繁搜索对话内容。建议增加搜索历史记录和模糊匹配功能，预计可减少50%搜索时间。"
[协商] 用户: "好主意，但我更想要按日期筛选"
[确认] Brain 调整方案，用户同意
[执行] Codex patch 实现日期筛选
[验证] 自动测试 + 用户试用
[记忆] "用户偏好按日期筛选对话" + "日期筛选实现方案"
```

### 3.5 能力五：Brain-Codex 双向协商

**目的**: 不是单向发指令，而是让 Brain 和 Codex 协商出最优方案。

**流程**:
```
Brain → Codex: "brain.py process() 452行太长，建议重构方案？"
Codex → Brain: "方案A: 抽提3个Mixin  方案B: 内部_handle_*方法拆分"
Brain: [查记忆] 上次 Mixin 重构引入了循环依赖
Brain → Codex: "采用方案B，但保留现有Mixin结构"
Codex: 执行方案B
Brain: 测试通过 → 记忆 "方案B更安全"
```

**关键**: Brain 有项目历史记忆，能避免重蹈覆辙。Codex 有代码分析能力，能给出技术方案。两者互补。

---

## 4. 新增扩展能力（基于行业调研）

### 4.1 自愈代码库 (Self-Healing Codebase)

参考 BugStack 的 5 阶段模型，LucidMind 可以实现：

```
错误捕获 → 上下文构建 → 修复生成 → 验证 → 部署
```

**LucidMind 增强版**:
- **错误捕获**: 监控 LucidMind 自身运行日志 + 用户反馈
- **上下文构建**: 利用项目记忆，不只看代码还看历史决策
- **修复生成**: Codex patch，最小化修改原则
- **验证**: 全量测试 + 回归检测
- **部署**: L0/L1 自动部署，L2+ 需确认
- **学习**: 记录修复模式，下次更快

### 4.2 REFLECTION.md 模式

参考 Addy Osmani 的 Ralph Loop：每次 Codex 执行后，Brain 生成反思记录：

```markdown
## 反思 2026-05-07 #042
- **任务**: 优化首页加载速度
- **执行**: 路由懒加载
- **结果**: bundle 减少 35%, 首屏时间从 1.2s → 0.8s
- **意外发现**: lit-html 的 unsafeHTML 指令不能在 lazy import 中使用
- **新规则**: → 写入 AGENTS.md / 项目记忆
- **Prompt 改进**: 下次 Codex 调用时提醒 "注意 lit-html 指令兼容性"
```

### 4.3 Bead 模式 — 不可变决策记录

参考 Gastown 的 "beads" 模式：每个 LucidMind 决策生成一个不可变记录：

```json
{
  "bead_id": "evolve-042",
  "timestamp": "2026-05-07T08:30:00Z",
  "type": "evolution",
  "trigger": "user_pattern:frequent_search",
  "proposal": "Add search history",
  "decision": "approved_with_modification",
  "modification": "User prefers date filter over history",
  "executor": "codex_patch",
  "outcome": "success",
  "test_result": "33/33 pass",
  "memory_update": ["user_prefers_date_filter", "date_filter_implementation"]
}
```

→ 可查询、可审计、可回溯。

### 4.4 多执行器智能路由

不只用 Codex，根据任务特点选择最优执行器：

| 任务类型 | 最优执行器 | 原因 |
|---------|-----------|------|
| 精准代码修改 | Codex | 代码理解最强 |
| 长文档生成 | Claude | 长上下文处理 |
| 本地快速测试 | Local LLM | 零延迟、隐私 |
| Shell 操作 | 内置工具 | 直接执行 |
| 网络搜索 | 搜索工具 | 实时信息 |

Brain 根据能力画像 + 历史成功率动态选择。

### 4.5 进化看板 (Evolution Dashboard)

驾驶舱新增"进化"面板：

```
📊 本周进化报告
├── 🐛 自动修复了 3 个 bug (L0: 2, L1: 1)
├── 🚀 性能提升 12% (bundle 297KB → 261KB)  
├── 📝 新增 8 条项目记忆
├── ✅ 代码覆盖率 78% → 85%
├── 🔒 2 次 L3 变更被用户否决 (已记住原因)
└── 💡 3 个待确认的改进建议
```

### 4.6 Token 预算与成本控制

参考 Ralph Loop 的 Token Budgeting：

- 每次进化任务设 token 上限
- 达到 85% 预算时暂停并通知
- 卡住 3 轮以上自动终止
- 记录每次 Codex 调用的 token 消耗和效果
- 长期优化 prompt 以减少浪费

---

## 5. 安全与边界

### 5.1 核心安全原则

参考 HyperAgents 论文和 NIST 2026 标准：

1. **基础模型权重冻结** — LucidMind 不修改 LLM 本身，只修改代码
2. **沙箱执行** — Codex 在隔离环境中运行
3. **评估标准人类设定** — 什么是"好的改进"由用户定义
4. **人在回路** — L2 以上变更必须用户确认
5. **完整审计** — 所有决策可追溯、可回滚

### 5.2 防失控机制

```
if 进化次数 > 每日上限:
    暂停，通知用户
if 连续失败 > 3 次:
    终止当前任务，分析原因
if 修改了冻结文件:
    需要 L3 审批
if 测试覆盖率下降:
    自动回滚
if 用户否决了某类改进 2 次:
    记住不再建议此类改进
```

### 5.3 记忆是瓶颈也是护城河

引用 2026 自我进化 Agent 报告：

> "Self-improvement requires memory. An agent that cannot remember what it tried, what worked, and what failed is doomed to repeat the same experiments indefinitely."

LucidMind 的**结构化项目记忆**正是核心竞争力。不同于 Ralph Loop 的 flat markdown 文件，LucidMind 有：
- 分层记忆（事实/经验/工作）
- 置信度标注
- 来源追踪
- 主动遗忘（过期/矛盾的记忆）

---

## 6. 实施路线

### Phase 1: 基础体检 (1-2 周)

- [ ] `ProjectCheckupRunner` — 编排 7 项检查
- [ ] 体检报告生成（Markdown + JSON）
- [ ] 驾驶舱"开始体检"按钮
- [ ] 基本 CLI 入口

### Phase 2: 诊断 + 修复闭环 (2-3 周)

- [ ] 诊断 API（深入分析单个问题）
- [ ] 安全分级引擎（L0-L4 自动分级）
- [ ] Codex patch + 自动测试 + 回滚
- [ ] 进化日志（Bead 模式）

### Phase 3: 用户感知 + 主动进化 (3-4 周)

- [ ] 用户行为感知模块
- [ ] 改进建议生成 + 用户确认流程
- [ ] Brain-Codex 协商协议
- [ ] REFLECTION.md 自动生成

### Phase 4: 多执行器路由 + 自愈 (4-6 周)

- [ ] 执行器能力画像 + 智能路由
- [ ] 自愈代码库基础版
- [ ] Git Hook 集成
- [ ] 进化看板 UI

### Phase 5: 自治能力 (6-8 周)

- [ ] 定时自动体检 + 自动修复
- [ ] Token 预算管理
- [ ] 进化效果度量
- [ ] 用户自定义进化策略

---

## 7. 衡量标准

| 指标 | 目标 |
|------|------|
| 体检覆盖率 | ≥80% 核心文件被扫描 |
| 自动修复成功率 | ≥70% 的 L0/L1 问题自动修复 |
| 测试通过率 | 进化后测试通过率 ≥ 进化前 |
| 用户确认率 | ≥60% 的建议被用户接受 |
| 平均修复时间 | L0: <2min, L1: <5min, L2: <30min |
| 记忆利用率 | ≥50% 的 Codex 调用使用了项目记忆 |
| 进化频率 | 每周 ≥3 次有意义的改进 |

---

---

## 8. 记忆系统优化 — 落地可执行方案

> "记忆是瓶颈。一个不能记住自己尝试过什么、什么有效、什么失败的 Agent，注定反复做同样的实验。"
> — Self-Improving AI Agents: The 2026 Guide

### 8.1 现状诊断

LucidMind 当前 4 层记忆架构：

| 层 | 实现 | 存什么 | 上限 | 问题 |
|---|---|---|---|---|
| ① 会话历史 | `JSONMemoryAdapter` | 每条消息 | 100条/会话 | token 膨胀 |
| ② 长期记忆 | `JSONMemoryAdapter` | 知识/教训 | 200条 | 无语义压缩 |
| ③ Letta Blocks | `BlockManager` | 核心上下文 | 2000字符/块 | OK |
| ④ SQLite Store | `MemoryStore` | 结构化记忆 | 无限 | 无遗忘机制 |

**核心问题**：
- 无 token 预算控制 → 每轮消耗 4000-5000 token 的记忆上下文
- 无语义压缩 → 10 轮对话产生 20 条原始记忆
- 无主动遗忘 → 过时/冲突记忆持续被检索
- 无冲突解决 → 矛盾信息共存导致 AI 回答不一致

### 8.2 最优架构：三级分层 + Token Budget

```
┌─────────────────────────────────────────────┐
│  Level 0: Working Memory (工作记忆)          │
│  • 当前会话摘要 ≤ 800 token                  │
│  • 每轮动态生成，不持久化                     │
└──────────────────┬──────────────────────────┘
                   │
┌──────────────────▼──────────────────────────┐
│  Level 1: Core Memory (核心记忆)             │
│  • Letta Blocks ≤ 600 token                 │
│  • 直注 system prompt                       │
└──────────────────┬──────────────────────────┘
                   │ 按需检索
┌──────────────────▼──────────────────────────┐
│  Level 2: Archival Memory (归档记忆)         │
│  • SQLite + FTS5 + Vec                      │
│  • 检索上限 3-4 条 ≤ 600 token              │
│  • 主动遗忘 + 冲突解决 + 版本化             │
└─────────────────────────────────────────────┘
```

**Token Budget 硬预算**: 每轮记忆注入总计 ≤ 2000 token。

### 8.3 执行方案

#### 方案 A: Token Budget 机制

**文件**: `memory/token_budget.py` (新建)

功能：
- 定义每轮记忆 token 预算常量
- 实现 `trim_to_budget()` — 截断检索结果使其不超预算
- 实现 `estimate_tokens()` — 快速 token 计数（中文×2 + 英文÷4）
- Brain 调用检索后统一通过 budget 过滤

#### 方案 B: 语义压缩

**文件**: `memory/compressor.py` (新建)

功能：
- 会话结束时将 N 条对话压缩为 1 条精炼记忆
- 格式: `"{日期}: {主题} — 问题: {问题}。方案: {方案}。结果: {结果}。"`
- 压缩比: 10:1 (10条消息 → 1条记忆，≤150字符)
- 无需 LLM 调用（规则提取 + 模板填充）

#### 方案 C: 主动遗忘 + 冲突解决

**文件**: `memory/forgetting.py` (新建)

功能：
- `forget_stale()` — 90天未被检索的标记 dormant，180天永久删除
- `forget_harmful()` — harmful_count ≥ 3 立即删除（已有，增强）
- `resolve_conflict()` — 检测同主题冲突，标记旧版本 superseded
- `merge_similar()` — 同主题保留最多 3 条，合并其余
- 定时任务: 每日运行一次清理

#### 方案 D: 意图感知检索

**文件**: `memory/noise_filter.py` (增强现有)

功能：
- 多级意图分类: greeting / recall / coding / preference / general
- 按意图调整检索数量和集合范围
- coding_task → 只检索 facts + lessons (limit=3)
- recall_explicit → 检索全部 (limit=6, boost_exact=True)
- greeting → 不检索

#### 方案 E: 记忆版本化

**文件**: `memory/store_feedback.py` (增强现有)

功能：
- 新记忆存入时检测同主题旧记忆
- 旧记忆添加 `superseded_by` + `superseded_at` 元数据
- 检索时过滤掉被 superseded 的记忆
- 保留历史链（可追溯决策变化）

### 8.4 衡量标准

| 指标 | 当前值 | 目标值 |
|------|--------|--------|
| 每轮记忆 token | ~4000-5000 | ≤ 2000 |
| 记忆条数增长率 | 每会话 +5-10 条 | 每会话 +1-2 条（压缩后） |
| 检索精度 | 未量化 | ≥ 80% 相关性 |
| 过时记忆比例 | 未清理 | < 5% |
| 冲突记忆数 | 未检测 | 0（自动解决） |

### 8.5 实施顺序

1. **Token Budget** (最紧急) → 立即控制成本和速度
2. **语义压缩** → 减少记忆膨胀
3. **主动遗忘** → 防止污染
4. **意图感知** → 精准检索
5. **版本化** → 解决冲突

---

## 参考资料

1. **Self-Improving AI Agents: The 2026 Guide** (o-mega.ai) — HyperAgents, 记忆瓶颈, 安全边界
2. **The Code Agent Orchestra** (Addy Osmani) — Ralph Loop, Quality Gates, AGENTS.md, REFLECTION.md, Beads 模式
3. **What Is a Self-Healing Codebase?** (bugstack.ai) — 5 阶段自愈 pipeline, 最小化修复, 置信度打分
4. **NIST 2026 Agent Standards** — 自治 AI 系统安全框架
5. **LucidMind 项目目标与可落地执行方案** — §3.2 必须做什么
6. **Best AI Agent Memory Systems in 2026** (vectorize.io) — 8 框架对比, 分层存储, 多策略检索
7. **Mem0 Research** (mem0.ai) — Token-efficient memory, 91.6 LoCoMo
8. **SimpleMem** (GitHub) — 语义压缩, +47% F1, 30x token 减少
