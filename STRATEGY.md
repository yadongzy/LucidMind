# LucidMind 战略方案

> **Python 开发者的轻量 AI Agent — 透明、可靠、10 分钟部署**
>
> 版本: v2.0 | 日期: 2025-02-25

---

## 一、定位

### 不是 OpenClaw 复制品，是 Python 生态的 AI Agent

| | OpenClaw | LucidMind |
|---|---------|-----------|
| 语言 | Node.js / TypeScript | **Python** |
| 技能 | Markdown 描述（LLM 解读执行，不确定性高） | **Python 代码（确定性执行）** |
| 部署 | Docker + Node.js + 多平台 SDK | **pip install + 一行启动** |
| UI | 无（纯命令行 + 消息平台） | **Web 管理界面** |
| 透明度 | 黑箱 | **思维过程实时可见** |
| 通道 | 7+ 平台 | Web + Telegram（够用优先） |
| 插件获取 | ClawHub 社区市场 | **MCP 兼容 + PluginHub + 自动搜索安装** |

### 一句话
**LucidMind = pip install 即用的 AI Agent，Python 插件确定性执行，MCP 兼容数百工具。**

### 差异化核心（OpenClaw 做不到的）
1. **透明思维** — 用户看到 Agent 完整推理过程，出错能定位原因
2. **Python 插件** — 确定性执行 vs Markdown 的 LLM 解读猜测
3. **一行部署** — `pip install lucidmind && lucidmind start`
4. **MCP 兼容** — 瞬间接入 Claude/Cursor/VS Code 生态的数百工具

### OpenClaw 的真实弱点（我们的机会）
1. **技能=Markdown** — 同一技能每次执行结果可能不同（LLM 解读有随机性）
2. **无管理界面** — 非技术用户无法使用
3. **安全事故** — 6000 封邮件被删，证明其工具审批流是事后补救
4. **重型部署** — Docker + Node.js + 多平台 SDK 配置复杂

---

## 二、现状评估

### 核心架构（✅ 不需要重建）
- **六边形架构**：Brain 只认 Port 接口，等效 OpenClaw 的 Gateway 架构
- **Agent Loop**：Brain.process() + 多轮工具调用 + Ralph 重试容错
- **Daemon 心跳**：等效 OpenClaw 的 HEARTBEAT.md 定时唤醒
- **记忆系统**：JSON 持久化 + 语义搜索（比 OpenClaw 的纯文件更强）
- **多模型**：DeepSeek + MiniMax + 本地 Ollama 自动降级

### 需要清理的问题
- 根目录 33 个废弃 .py 脚本
- 42 个 .md 文件堆积（PROGRESS.md 一个 4500 行）
- scripts/ 里 28 个一次性教学脚本
- brain.py 内部 import 风格不一致
- introspect.py 过大（15K）应拆分

---

## 三、执行计划（聚焦，不分散）

### Phase 1: 核心能力（唯一聚焦，2-4周）

#### 1A. 代码清理（2天）✅ 已完成

| # | 任务 | 说明 | 状态 |
|---|------|------|------|
| A1 | 根目录废弃 .py → archive/ | 33 个文件 | ✅ |
| A2 | scripts/teach_round*.py → archive/ | 28 个文件 | ✅ |
| A3 | 过时 .md 合并/删除 | 只留 README/SOUL/STRATEGY/RULES/ARCHITECTURE | ✅ |
| A4 | brain.py 内部 import 规范化 | 移到文件顶部 | ✅ |
| A5 | .gitignore 更新 | 排除 archive/ | ✅ |

#### 1B. MCP 协议完整兼容（1周）✅ 已完成

**为什么提前**：接入 MCP = 瞬间获得数百个现成工具，比自己写 100 个插件效率高 100 倍。

| # | 任务 | 说明 | 状态 |
|---|------|------|------|
| B1 | MCP Client 完善 | stdio + http 传输，配置文件 | ✅ |
| B2 | MCP Server 发现 | 自动发现 + API 管理 | ✅ |
| B3 | MCP 工具注入 Brain | MCP 工具与原生工具统一调度 | ✅ |
| B4 | 前端 MCP 配置 | UI 中添加/删除/发现 MCP Server | ✅ |

#### 1C. 15+ 内置插件（1周）✅ 已完成（15 个插件 / 35 个工具）

见下方「内置插件清单」。

#### 1D. 插件自动搜索安装（3天）✅ 已完成

见下方「PluginHub 自动安装」。

#### 1E. 插件热加载 + CLI 工具（2天）✅ 已完成

| # | 任务 | 说明 | 状态 |
|---|------|------|------|
| E1 | 运行时热加载 | POST /api/plugins/reload | ✅ |
| E2 | `lucidmind create-plugin <name>` | CLI 模板生成器 | 🔲 |
| E3 | 插件开发文档 | docs/plugin-guide.md | ✅ |

#### 1F. 前端完善（2天）✅ 已完成

| # | 任务 | 说明 | 状态 |
|---|------|------|------|
| F1 | 仪表盘 | 插件/通道/MCP/工具 统计卡片 | ✅ |
| F2 | 插件安装 UI | 搜索 PluginHub + 一键安装 | ✅ |
| F3 | MCP 管理 UI | 添加/删除/发现 MCP Server | ✅ |
| F4 | 通道管理 UI | 4通道状态 + Webhook配置 | ✅ |
| F5 | 工具安全审批弹窗 | 危险工具执行前用户确认 | ✅ |

### Phase 2: 多通道 + 安全（✅ 已完成）

| 功能 | 状态 | 说明 |
|------|------|------|
| Telegram 通道 | ✅ 已完成 | polling 模式，python-telegram-bot |
| 飞书通道 | ✅ 已完成 | SDK 长连接 + 语音消息(Whisper STT) |
| 企业微信通道 | ✅ 已完成 | XML Webhook + 自建应用消息 API |
| 微信个人号通道 | ✅ 已完成 | GeweChat iPad协议（研究确认最优方案） |
| 工具安全审批流 | ✅ 已完成 | 危险工具执行前 WebSocket 用户确认 |
| E2E 自动化测试 | ✅ 已完成 | pytest 25 个用例全部通过 |

### Phase 3: 大脑变聪明（当前聚焦）

> **核心方向：上下文记忆与检索（对标 OpenClaw src/memory/）+ 正确使用工具与 MCP**
> 教学方向已验证无效（200条垃圾经验），不再投入。大脑变聪明靠的是：
> 1. 高质量记忆检索 — 记对的东西，找得到
> 2. 正确使用工具 — 用工具做事，不是背答案
> 3. MCP 生态接入 — 借助外部工具扩展能力

#### 3A. 记忆系统加固（对标 OpenClaw）

| # | 任务 | 说明 | 当前状态 |
|---|------|------|---------|
| A1 | 向量语义检索 | Ollama nomic-embed-text + BM25融合(0.6:0.4) | ✅ 已可用 |
| A2 | 经验分层(tier) | strategy永不衰减/fact=60天/temp=7天 | ✅ 已实现 |
| A3 | 选择性添加门控 | 拒绝空洞/短/重复经验 | ✅ 已实现 |
| A4 | 组合删除(curate) | 周期性+历史性删除，200条→48条 | ✅ 已运行 |
| A5 | effectiveness虚高修正 | 简单问候不应标记effective，只有工具调用才算 | 🔲 待修 |
| A6 | daemon任务标记有效性 | 90%任务走daemon不触发_mark_lessons_effective | 🔲 待修 |
| A7 | 深度元认知超时修正 | 5s→15s，让规划器能被触发 | 🔲 待修 |
| A8 | 灵魂进化激活 | evolve()无调用方，需接入学习引擎 | 🔲 待修 |

**依据**: arXiv:2505.16067 — 组合删除准确率+4%，内存-75%。Harvard D3 — "Simply storing every experience leads to worse outcomes."

#### 3B. 工具能力提升

| # | 任务 | 说明 | 状态 |
|---|------|------|------|
| B1 | 清理死代码工具 | 移除8个无用工具注册(GUI/豆包/TTS等) | 🔲 |
| B2 | 工具使用准确性 | 大脑正确选择和调用工具的能力 | 🔲 |
| B3 | MCP 生态实际接入 | 配置并验证外部MCP Server可用 | 🔲 |

#### 3C. 工程质量

| # | 任务 | 说明 | 状态 |
|---|------|------|------|
| C1 | 回归测试框架 | 通道/记忆/Brain核心的冒烟测试 | 🔲 |
| C2 | 变更日志制度 | CHANGELOG.md，每次改动必须记录 | 🔲 |
| C3 | 根目录散落文件清理 | 6个.md + 7个.py 不属于核心 | 🔲 |
| C4 | brain_daemon.py超限 | 405行→≤300行 | 🔲 |
| C5 | task_dispatcher.py超限 | 484行→≤300行（已拆分utils） | ⚠️ 需验证 |

### Phase 4+: 按需扩展

| 功能 | 状态 | 说明 |
|------|------|------|
| Discord 通道 | 🔲 | 社区贡献即可 |
| 权限分级 | 🔲 | 多用户场景才需要 |
| 社区生态 | 🔲 | 需要用户基础支撑 |
| pip 打包发布 | 🔲 | Phase 3 稳定后 |

---

## 四、内置插件清单（15+）

### 已完成（15个）✅

| 插件 | 工具 | 说明 |
|------|------|------|
| `clipboard` | clipboard_read, clipboard_write | 系统剪贴板读写（macOS） |
| `project_context` | scan_project | 扫描项目目录结构和技术栈 |
| `reminder` | set_reminder, list_reminders | 定时提醒 + WebSocket 推送 |

### 信息管理类（4个）✅

| 插件 | 工具 | 功能说明 | 状态 |
|------|------|---------|------|
| `notes` | create_note, search_notes, list_notes | Markdown 笔记本 | ✅ |
| `bookmarks` | add_bookmark, search_bookmarks, list_bookmarks | 网址收藏夹 | ✅ |
| `knowledge_base` | kb_add, kb_search, kb_list | 个人知识库 | ✅ |
| `daily_digest` | generate_digest | 每日摘要 | ✅ |

### 开发者工具类（4个）✅

| 插件 | 工具 | 功能说明 | 状态 |
|------|------|---------|------|
| `github_ops` | gh_issues, gh_create_issue, gh_prs, gh_repo_info | GitHub 操作 | ✅ |
| `docker_ops` | docker_ps, docker_logs, docker_restart | Docker 容器管理 | ✅ |
| `git_helper` | git_status, git_diff, git_log, git_commit | Git 操作 | ✅ |
| `code_runner` | run_python, run_script | 沙盒代码执行器（已加固） | ✅ |

### 生活助手类（4个）✅

| 插件 | 工具 | 功能说明 | 状态 |
|------|------|---------|------|
| `weather` | get_weather, weather_forecast | 天气查询 | ✅ |
| `calculator` | calc, unit_convert, currency_convert | 计算器 | ✅ |
| `web_monitor` | monitor_add, monitor_check, monitor_list | 网页监控 | ✅ |
| `email_sender` | send_email | 邮件发送 | ✅ |

### 汇总

| 类别 | 数量 | 状态 |
|------|------|------|
| 已完成 | **15** | ✅ |
| 工具总数 | **35** | ✅ |

> **设计原则**：每个插件都是独立目录，manifest.json + main.py，不依赖其他插件。
> 插件之间通过 Brain 协调（LLM 决定用哪个工具），不直接互相调用。

---

## 五、插件自动搜索安装（PluginHub）

### 核心机制：Agent 自己知道需要什么工具

```
用户："帮我查一下北京的天气"
   │
   ▼
Brain: 我需要 weather 工具 → 发现没有安装
   │
   ▼
自动搜索 PluginHub → 找到 weather 插件
   │
   ▼
提示用户："我找到了天气插件，需要安装吗？" / 自动安装
   │
   ▼
热加载 → 执行查询 → 返回结果
```

### 技术实现

#### 1. PluginHub 仓库结构（GitHub 仓库）

```
lucidmind-plugins/          ← GitHub public repo
├── registry.json           ← 所有插件索引
├── weather/
│   ├── manifest.json
│   └── main.py
├── github_ops/
│   ├── manifest.json
│   └── main.py
└── ...
```

**registry.json:**
```json
{
  "plugins": [
    {
      "name": "weather",
      "version": "1.0.0",
      "description": "天气查询：当前天气+预报",
      "tools": ["get_weather", "weather_forecast"],
      "keywords": ["天气", "weather", "forecast", "温度"],
      "download_url": "https://raw.githubusercontent.com/.../weather/"
    }
  ]
}
```

#### 2. 自动搜索流程

```python
# Brain 工具调用失败时触发
async def _on_tool_not_found(self, tool_name: str) -> str | None:
    """工具不存在 → 搜索 PluginHub → 提示/自动安装。"""
    # 1. 搜索本地 registry 缓存
    match = search_plugin_registry(tool_name)
    if not match:
        # 2. 拉取远程 registry.json 刷新
        await refresh_registry()
        match = search_plugin_registry(tool_name)
    if match:
        # 3. 自动安装（下载到 skills/ 目录）
        await install_plugin(match["name"])
        # 4. 热加载
        await reload_skills()
        return f"已自动安装插件 {match['name']}，正在重新执行..."
    return None
```

#### 3. 智能匹配

不只按 tool_name 精确匹配，还支持：
- **关键词匹配**：用户说"天气"→ 匹配 weather 插件的 keywords
- **语义匹配**：用 LLM 判断"帮我监控这个网页有没有更新"需要 web_monitor 插件
- **MCP 降级**：PluginHub 没有 → 搜索已连接的 MCP Server 是否提供

#### 4. 安装方式

| 方式 | 触发 | 说明 |
|------|------|------|
| **自动安装** | Brain 检测到缺少工具 | 静默下载 + 热加载 |
| **CLI 安装** | `lucidmind install weather` | 命令行 |
| **UI 安装** | 前端插件市场页面 | 浏览 + 一键安装 |
| **手动安装** | 复制目录到 skills/ | 重启或热加载 |

### 对比 OpenClaw 的 ClawHub

| | OpenClaw ClawHub | LucidMind PluginHub |
|---|---------|-----------|
| 技能格式 | Markdown (SKILL.md) | Python 代码 (main.py) |
| 安装方式 | 手动下载 .md 文件 | **自动检测 + 下载 + 热加载** |
| 触发 | 用户手动搜索安装 | **Agent 自动发现缺失并安装** |
| 可靠性 | LLM 每次解读可能不同 | 确定性 Python 执行 |
| 审核 | 社区自治 | registry.json 白名单 |

---

## 六、MCP 兼容策略

### 为什么 MCP 是第一优先

MCP (Model Context Protocol) 已成为行业标准：
- **Claude Desktop** 原生支持
- **Cursor / VS Code** 原生支持
- **数百个现成 MCP Server**：GitHub、Slack、Google、文件系统、数据库...

接入 MCP = 瞬间获得数百工具，不需要自己写插件。

### 实现方案

```
LucidMind
├── 原生插件 (skills/)        ← Python 代码，确定性执行
├── MCP 工具 (mcp_servers/)   ← 对接外部 MCP Server
└── PluginHub (远程)          ← 按需下载

Brain 统一调度：LLM 不区分工具来源，只看工具定义。
```

### 插件来源优先级

```
用户请求 → Brain 选择工具
  │
  ├─ 1. 原生插件（skills/）     ← 最快、最可靠
  ├─ 2. MCP Server 工具         ← 已连接的外部工具
  ├─ 3. PluginHub 自动安装       ← 按需下载
  └─ 4. 告知用户需要手动配置     ← 最后手段
```

---

## 七、技术决策

### 1. Python 插件 vs Markdown 技能

| 维度 | Markdown（OpenClaw） | Python（LucidMind） |
|------|---------------------|-------------------|
| 上手难度 | 低（写文档） | 中（写代码） |
| 表达能力 | 弱（依赖 LLM） | **强（任意逻辑）** |
| 可靠性 | 低（每次执行可能不同） | **高（确定性执行）** |
| 调试 | 难（黑箱） | **易（断点+日志）** |
| 性能 | 慢（LLM 翻译） | **快（直接执行）** |
| 生态 | 大（社区贡献门槛低） | 小（需要会 Python） |

**结论**：可靠性 > 门槛低。LLM 负责决策"用什么"，Python 负责"怎么用"。

### 2. 保留六边形架构

Brain 只认 Port 接口：
- 换 LLM → 只改 LLMAdapter
- 加通道 → 只加 ChannelAdapter
- 加工具 → 只加 ToolAdapter（插件 / MCP）
- 换存储 → 只改 MemoryAdapter

### 3. Web UI 是差异化武器

OpenClaw 完全没有管理界面。LucidMind 的 Web UI：
- 实时看 Agent 思维（透明思维）
- 插件市场（搜索/安装/管理）
- MCP 连接管理
- 任务监控 + 仪表盘
- 用户画像编辑

---

## 八、成功指标

| 指标 | 目标 | 时间 |
|------|------|------|
| 内置插件 | 15+ | Phase 1 |
| MCP 工具可用 | 50+ | Phase 1（通过 MCP 兼容） |
| 部署时间 | < 5 分钟 | Phase 1 |
| 新插件开发时间 | < 10 分钟 | Phase 1 |
| 代码行数（核心） | < 5,000 行 | 清理后 |
| 自动安装成功率 | > 90% | Phase 1 |

---

## 九、立即行动项

| # | 任务 | 优先级 | 状态 |
|---|------|--------|------|
| 1 | 代码大清理（~80 废弃文件） | P0 | ✅ |
| 2 | MCP 协议完整兼容 | P0 | ✅ |
| 3 | 15 个内置插件 (35 工具) | P0 | ✅ |
| 4 | PluginHub 自动搜索安装机制 | P1 | ✅ |
| 5 | 插件热加载 | P1 | ✅ |
| 6 | 前端仪表盘 + 插件/MCP/通道 UI | P1 | ✅ |
| 7 | 插件开发文档 | P2 | ✅ |
| 8 | 多通道 (Telegram/飞书/企微/微信) | P1 | ✅ |
| 9 | 工具安全审批流 | P1 | ✅ |
| 10 | E2E 自动化测试 (25 用例) | P1 | ✅ |
| 11 | Demo 视频录制 | P2 | 🔲 |
| 12 | pip 打包发布 | P1 | 🔲 |
