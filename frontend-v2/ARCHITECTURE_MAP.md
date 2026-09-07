# LucidMind 前端-后端 关联脉络图

**日期**: 2026-02-23  
**用途**: 逐一审查每个前端按钮/交互与后端模块的联动关系

---

## 一、系统总架构

```
┌─────────────────────────────────────────────────────────────────────┐
│                        前端 (Vite + Lit)                            │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐           │
│  │ chat.js  │  │overview.js│  │sessions.js│  │ config.js│  ...      │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘           │
│       │              │              │              │                │
│  ┌────┴──────────────┴──────────────┴──────────────┴─────┐         │
│  │                    app.js (主组件)                      │         │
│  │  状态: messages, sessions, status, brainStatus, theme  │         │
│  └────┬──────────────────────────────────┬───────────────┘         │
│       │                                  │                         │
│  ┌────┴────┐                        ┌────┴────┐                    │
│  │gateway.js│ WebSocket              │ api.js  │ REST               │
│  │ 心跳30s  │ 重连3s                 │ fetch() │                    │
│  └────┬────┘                        └────┬────┘                    │
└───────┼──────────────────────────────────┼─────────────────────────┘
        │ ws://host/ws                     │ http://host/api/*
        │                                  │
┌───────┼──────────────────────────────────┼─────────────────────────┐
│       │          后端 (FastAPI)           │                         │
│  ┌────┴────────────────┐           ┌─────┴──────────────────┐      │
│  │ websocket_channel.py│           │     api/main.py        │      │
│  │  ├─ ping → pong     │           │  ├─ /api/status        │      │
│  │  ├─ chat → brain    │           │  ├─ /api/verify        │      │
│  │  └─ switch_session  │           │  ├─ /api/sessions/*    │      │
│  └────┬────────────────┘           │  ├─ /api/brain/*       │      │
│       │                            │  ├─ /api/upload        │      │
│       ▼                            │  ├─ /api/teacher/*     │      │
│  ┌─────────┐                       │  ├─ /api/memory/*      │      │
│  │ Brain   │ ◄─────────────────────│  ├─ /api/lessons       │      │
│  │ 单例    │                       │  ├─ /api/tasks         │      │
│  └────┬────┘                       │  └─ /api/cron          │      │
│       │                            └────────────────────────┘      │
│       ▼                                                            │
│  ┌──────────────── 六边形架构 Ports ────────────────────┐           │
│  │                                                      │           │
│  │  ┌─────────┐  ┌──────────┐  ┌──────────┐            │           │
│  │  │ LLM Port│  │Tool Port │  │Memory Port│            │           │
│  │  │FallbackLLM│ │Composite │  │JSONMemory │            │           │
│  │  │ ├deepseek│  │ 33个工具  │  └──────────┘            │           │
│  │  │ ├minimax │  └──────────┘                           │           │
│  │  │ └local   │  ┌──────────┐  ┌──────────┐            │           │
│  │  └─────────┘  │Learn Port│  │Stream Port│            │           │
│  │               │JSONLessons│  │WS Stream  │            │           │
│  │               └──────────┘  └──────────┘            │           │
│  │  ┌──────────┐  ┌──────────┐                          │           │
│  │  │Channel   │  │Reflection│                          │           │
│  │  │Port (WS) │  │Port      │                          │           │
│  │  └──────────┘  └──────────┘                          │           │
│  └──────────────────────────────────────────────────────┘           │
│                                                                     │
│  ┌──────────────── 大脑子系统 ──────────────────────────┐           │
│  │  ┌─────────────┐  ┌──────────────┐  ┌────────────┐  │           │
│  │  │BrainDaemon  │  │ SoulEngine   │  │ GoalSystem │  │           │
│  │  │ OODA循环    │  │ 灵魂进化      │  │ 目标管理    │  │           │
│  │  │ 动态间隔    │  └──────────────┘  └────────────┘  │           │
│  │  └──────┬──────┘                                     │           │
│  │         │                                            │           │
│  │  ┌──────┴──────┐  ┌──────────────┐  ┌────────────┐  │           │
│  │  │TaskDispatcher│  │ BrainEngines │  │IssueTracker│  │           │
│  │  │ 任务队列     │  │ ├SelfCheck   │  │ 问题追踪    │  │           │
│  │  │ P0-P3/L0-L3 │  │ ├Repair     │  └────────────┘  │           │
│  │  └─────────────┘  │ ├DailyRoutine│                   │           │
│  │                    │ └Learning    │                   │           │
│  │  ┌─────────────┐  └──────────────┘                   │           │
│  │  │TeacherChannel│  ┌──────────────┐                  │           │
│  │  │ 老师通信     │  │RepairEngine  │                   │           │
│  │  │ inbox/outbox │  │ 分级修复      │                   │           │
│  │  └─────────────┘  └──────────────┘                   │           │
│  └──────────────────────────────────────────────────────┘           │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 二、前端页面 ↔ 后端模块 对应关系

### 2.1 Topbar（全局顶栏）

```
┌─────────────────────────────────────────────────────────────────┐
│ 🧠 LUCIDMIND 控制面板 │ [状态pill] │ [模型选择器▼] │ [🌙/☀️]    │
└─────────────────────────────────────────────────────────────────┘
```

| 元素 | 交互 | 前端方法 | 后端 API | 后端模块 |
|------|------|---------|---------|---------|
| 🧠 品牌 | 纯展示 | — | — | — |
| 状态 pill | 展示连接状态 | `this.connected` | WebSocket 连接状态 | `gateway.js` → `websocket_channel.py` |
| 状态圆点 | 绿=连接/红=断开 | `this.connected` | WS open/close 事件 | `gateway.js` |
| 模型选择器 | 下拉切换模型 | `_switchModel(model)` | `POST /api/verify` | `api/main.py` → `FallbackLLMAdapter` |
| 模型状态圆点 | 绿=可用/红=离线 | `this.status?.llm?.available` | `GET /api/status` | `api/main.py` → `llm_adapter.is_available()` |
| 🌙/☀️ 切换 | 切换主题 | `_toggleTheme()` | — (localStorage) | 纯前端 |

### 2.2 对话页 (chat.js)

```
┌─────────────────────────────────────────────────────────────────┐
│ Chat Controls: [会话选择器▼] [🔄刷新] │ [🧠思考开关]              │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Chat Thread (消息区)                                            │
│  ┌─ chat-group (user) ─────────────────────────────────────┐   │
│  │ [U] │ 用户消息气泡                                       │   │
│  │     │ 你 · 20:15                                         │   │
│  └─────────────────────────────────────────────────────────┘   │
│  ┌─ chat-group (assistant) ────────────────────────────────┐   │
│  │ [L] │ [⚡思考过程] (可折叠)                               │   │
│  │     │ [⚙工具调用: xxx]                                    │   │
│  │     │ [✓返回结果] (可折叠)                                │   │
│  │     │ 助手回复气泡 (Markdown渲染)                          │   │
│  │     │ LucidMind · 20:16                                   │   │
│  └─────────────────────────────────────────────────────────┘   │
│  ┌─ 阅读指示器 ────────────────────────────────────────────┐   │
│  │ [L] │ ● ● ● (三圆点跳动)                                │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
├─────────────────────────────────────────────────────────────────┤
│ Confirm Bar: 🧠 大脑计划等待确认  [▶执行] [⏭跳过]              │
├─────────────────────────────────────────────────────────────────┤
│ Queue: 📋 N 条消息排队中...                                     │
├─────────────────────────────────────────────────────────────────┤
│ Compose: [📎上传] [消息输入框...] [停止/新对话] [发送/排队 ↵]    │
└─────────────────────────────────────────────────────────────────┘
```

| 按钮/交互 | 前端方法 | 后端 API | 后端模块 | 数据流 |
|-----------|---------|---------|---------|--------|
| **会话选择器** | `_switchSession(sid)` | `WS: switch_session` + `GET /api/sessions/:id/history` | `websocket_channel.py` → `brain.switch_session()` + `api/sessions.py` | 切换会话 → 清空消息 → 加载历史 |
| **🔄 刷新** | `_loadHistory()` | `GET /api/sessions/:id/history` | `api/sessions.py` → `data/sessions/:id.json` | 重新加载当前会话历史 |
| **🧠 思考开关** | `showThinking = !showThinking` | — (localStorage) | 纯前端过滤 | 控制 thinking/tool_call/tool_result 消息是否显示 |
| **发送消息** | `_sendChat()` | `WS: chat` | `websocket_channel.py` → `brain.process(sid, text)` | 用户输入 → WS → Brain → LLM → 流式回复 |
| **Enter 快捷键** | `_sendChat()` | 同上 | 同上 | Shift+Enter=换行, Enter=发送, IME兼容 |
| **停止** (忙时) | `_abortChat()` | `WS: close` | `gateway.js` 关闭连接 → 自动重连 | 中断当前处理 |
| **新对话** (闲时) | `_newSession()` | `POST /api/sessions` | `api/sessions.py` → 生成UUID → 保存meta | 创建新会话 → 自动切换 |
| **排队** (忙时) | `_sendChat()` | `WS: chat` (入队) | `gateway.js` 消息队列 → 等待 `complete` 后发送 | 消息入队等待 |
| **📎 上传** | `_uploadFile(file)` | `POST /api/upload` + `WS: chat` | `api/upload.py` → 保存文件 → Brain 分析 | 上传 → 自动发送分析请求 |
| **图片粘贴** | `_uploadFile(file)` | 同上 | 同上 | 粘贴板图片 → 同上传流程 |
| **▶ 执行** (确认栏) | `_confirmPlan()` | `POST /api/brain/confirm` | `api/brain_init.py` → `daemon.confirm_plan()` | 确认大脑计划 → daemon 执行 |
| **⏭ 跳过** (确认栏) | `_skipPlan()` | `POST /api/brain/skip` | `api/brain_init.py` → `daemon._pending_plan = None` | 跳过当前计划 |
| **思考过程卡片** | `toggle collapsed` | — | 纯前端 | 点击折叠/展开 |
| **NSFW 过滤** | `containsNSFW()` | — | 纯前端 | 29个正则模式，≥2个命中 → 过滤 |
| **长消息折叠** | `renderCollapsibleBubble()` | — | 纯前端 | >500字符 → 预览+展开 |
| **查看原始内容** | `<details>` | — | 纯前端 | 被过滤内容的可选查看 |

### 2.3 系统概览页 (overview.js)

| 元素 | 数据来源 | 后端 API | 后端模块 |
|------|---------|---------|---------|
| 连接状态 | `app.connected` | WebSocket 状态 | `gateway.js` |
| 语言模型状态 | `status.llm.available` | `GET /api/status` | `api/main.py` → `llm_adapter.is_available()` |
| 模型名称 | `status.llm.model` | `GET /api/status` | `api/main.py` → `llm_adapter.model` |
| 提供商 | `status.llm.provider` | `GET /api/status` | `api/main.py` → `llm_adapter.provider_name` |
| 端口状态 (6个) | `status.ports.*` | `GET /api/status` | `api/main.py` 硬编码 |
| 大脑状态 | `brainStatus.awake` | `GET /api/brain/status` | `api/brain_init.py` → `brain._awake` |
| 暂停状态 | `brainStatus.daemon.paused` | `GET /api/brain/status` | `api/brain_init.py` → `daemon._paused` |
| 思考次数 | `brainStatus.daemon.thought_count` | `GET /api/brain/status` | `brain_daemon.py` → `daemon.get_status()` |
| 行动次数 | `brainStatus.daemon.action_count` | `GET /api/brain/status` | 同上 |
| 任务队列 | `brainStatus.daemon.queue` | `GET /api/brain/status` | `task_dispatcher.py` → 队列统计 |
| 工具列表 | `status.tools[]` | `GET /api/status` | `api/main.py` → `tool_adapter.list_tools()` |

### 2.4 会话管理页 (sessions.js)

| 按钮/交互 | 前端方法 | 后端 API | 后端模块 |
|-----------|---------|---------|---------|
| 会话列表 | `_refreshSessions()` | `GET /api/sessions` | `api/sessions.py` → `sessions_meta.json` |
| 新建会话 | `_newSession()` | `POST /api/sessions` | `api/sessions.py` → UUID 生成 |
| 删除会话 | `_deleteSession(sid)` | `DELETE /api/sessions/:id` | `api/sessions.py` → 删除 meta + json |
| 切换会话 | `_switchSession(sid)` | `WS: switch_session` + `GET /api/sessions/:id/history` | 同对话页 |

### 2.5 系统配置页 (config.js)

| 按钮/交互 | 前端方法 | 后端 API | 后端模块 |
|-----------|---------|---------|---------|
| 提供商选择 | DOM select | — | 纯前端 |
| API 密钥输入 | DOM input | — | 纯前端 |
| 测试并应用 | `api.verifyConnection()` | `POST /api/verify` | `api/main.py` → 更新 `_deepseek`/`_local` 配置 |
| 自动学习开关 | `api.resumeBrain()/pauseBrain()` | `POST /api/brain/resume` 或 `/pause` | `api/brain_init.py` → `daemon._paused` |
| 思考间隔 | `api.setBrainInterval()` | `POST /api/brain/interval` | `api/brain_init.py` → `daemon._interval` |
| 自动求助老师 | `api.setAutoAsk()` | `POST /api/brain/auto-ask` | `api/brain_init.py` → `teacher._auto_ask_enabled` |
| 显示思考过程 | `app.showThinking` | — (localStorage) | 纯前端 |

### 2.6 大脑状态页 (app.js _renderBrain)

| 元素 | 数据来源 | 后端 API | 后端模块 |
|------|---------|---------|---------|
| 运行/休眠 | `brainStatus.awake` | `GET /api/brain/status` | `brain_init.py` |
| 守护进程状态 | `brainStatus.daemon.running` | 同上 | `brain_daemon.py` |
| 思考次数 | `brainStatus.daemon.thought_count` | 同上 | 同上 |
| 行动次数 | `brainStatus.daemon.action_count` | 同上 | 同上 |
| 任务队列 | `brainStatus.daemon.queue.total` | 同上 | `task_dispatcher.py` |

### 2.7 事件日志页 (logs.js)

| 元素 | 数据来源 | 后端 API |
|------|---------|---------|
| 日志列表 | `app.eventLog[]` | — (纯前端，`_log()` 方法记录) |
| 清空按钮 | `app.eventLog = []` | — |

---

## 三、WebSocket 消息流完整链路

```
用户输入 "你好"
    │
    ▼
[前端 gateway.js]
    │ send({ type: "chat", message: "你好", session_id: "default" })
    │
    ▼
[后端 websocket_channel.py]
    │ handle_connection() → msg_type == "chat"
    │ asyncio.create_task(_safe_process(brain, stream, sid, text))
    │
    ▼
[Brain.process(sid, "你好")]
    │
    ├─ 1. memory_adapter.get_context(sid)     → 获取历史上下文
    ├─ 2. metacognition.analyze()             → 元认知分析
    ├─ 3. llm_adapter.chat(messages, tools)   → 调用 LLM
    │      │
    │      ├─ 尝试 DeepSeek (主模型)
    │      ├─ 失败 → MiniMax (备用)
    │      └─ 失败 → Local qwen2.5:7b (保底)
    │
    ├─ 4. stream.emit("thinking", data)       → 前端收到思考过程
    ├─ 5. stream.emit("tool_call", data)      → 前端收到工具调用
    │      │
    │      └─ tool_adapter.execute(name, args) → 执行工具
    │         └─ stream.emit("tool_result", data) → 前端收到结果
    │
    ├─ 6. stream.emit("response_start")       → 流式开始
    ├─ 7. stream.emit("response_delta", chunk) → 流式增量 (多次)
    ├─ 8. stream.emit("response_end")         → 流式结束
    │
    └─ 9. stream.emit("complete")             → 处理完成
         │
         ▼
    [前端 gateway.js]
         isProcessing = false → 处理队列中下一条消息
```

---

## 四、心跳链路

```
[前端 gateway.js]
    │ setInterval(30000) → send({ type: "ping" })
    │ setTimeout(60000) → 超时关闭连接
    │
    ▼
[后端 websocket_channel.py]
    │ msg_type == "ping"
    │ → send_json({ type: "pong", ts, brain: awake, queue: len })
    │
    ▼
[前端 gateway.js]
    │ 收到 pong → clearTimeout(heartbeatTimeout)
    │ 连接保活成功
```

---

## 五、大脑守护进程 (Daemon) 循环

```
BrainDaemon._think_loop() — 每 interval 秒执行一次
    │
    ├─ Observe (观察)
    │   ├─ 释放卡住任务
    │   ├─ 自动淘汰过期任务
    │   └─ 老师消息入队
    │
    ├─ Decide (决策)
    │   └─ dequeue 最高优先级任务 (P0>P1>P2>P3>L0>L1>L2>L3)
    │
    ├─ Act (行动)
    │   └─ brain.process(sid, task) → 执行1件任务
    │
    └─ 动态间隔调整
        ├─ P0 = 10s
        ├─ P1/P2 = 30s
        ├─ P3 = 60s
        ├─ 学习 = 120s
        ├─ 空 = 300s
        └─ 连续3轮空 = 600s

BrainEngines._run_engines()
    ├─ SelfCheckEngine: 每日轻量自检 + 每月全量
    ├─ RepairEngine: 分级修复 + 回检验证
    ├─ DailyRoutineEngine: 5项每日必做
    └─ LearningEngine: 3:00-6:00 定时学习
```

---

## 六、确认栏链路

```
[后端 BrainDaemon]
    │ daemon._pending_plan = plan
    │ ws_channel.broadcast({ type: "plan_confirm" })
    │
    ▼
[前端 app.js]
    │ case "plan_confirm": this.pendingConfirm = true
    │ → 显示确认栏
    │
    ├─ 用户点击 "执行"
    │   │ _confirmPlan() → POST /api/brain/confirm
    │   │ → daemon.confirm_plan() → 执行计划
    │   └─ pendingConfirm = false → 隐藏确认栏
    │
    └─ 用户点击 "跳过"
        │ _skipPlan() → POST /api/brain/skip
        │ → daemon._pending_plan = None
        └─ pendingConfirm = false → 隐藏确认栏
```

---

## 七、模型切换链路

```
[前端 Topbar 模型选择器]
    │ @change → _switchModel("qwen2.5:7b")
    │
    ▼
[前端 app.js]
    │ providerMap: deepseek-chat→deepseek, minimax→minimax, qwen2.5:7b→local
    │ api.verifyConnection(provider, "", model)
    │
    ▼
[后端 POST /api/verify]
    │ _PROVIDERS[provider] → (base_url, default_model)
    │ DeepSeekAdapter(api_key, base_url, model).is_available()
    │
    ├─ 成功 → 更新 _deepseek 或 _local 的配置
    │   target.api_key = api_key
    │   target.base_url = base_url
    │   target.model = model
    │   llm_adapter.provider_name = provider
    │
    └─ 失败 → 返回 { status: "error" }
    │
    ▼
[前端 app.js]
    │ _refreshStatus() → GET /api/status → 更新 modelInfo
    │ → Topbar 显示新模型名称 + 状态圆点
```

---

## 八、文件上传链路

```
[前端 chat.js]
    │ 📎按钮 → input[type=file] → _uploadFile(file)
    │ 或 粘贴图片 → @paste → _uploadFile(file)
    │
    ▼
[前端 app.js]
    │ api.uploadFile(file) → POST /api/upload (FormData)
    │
    ▼
[后端 api/upload.py]
    │ 保存到 data/uploads/ → 返回 { filename, path, size }
    │
    ▼
[前端 app.js]
    │ 添加 "📎 已上传: xxx" 消息
    │ gateway.sendChat("我上传了文件 xxx，请分析", sid)
    │ → Brain 自动分析文件
```

---

## 九、定时轮询

| 轮询 | 间隔 | 前端方法 | 后端 API |
|------|------|---------|---------|
| 系统状态 | 30s | `_refreshStatus()` | `GET /api/status` |
| 大脑状态 | 15s | `_refreshBrain()` | `GET /api/brain/status` |
| 心跳 | 30s | `gateway._startHeartbeat()` | `WS: ping → pong` |

---

## 十、待实现页面 ↔ 后端 API 映射

| 前端页面 | 当前状态 | 后端 API | 后端模块 |
|---------|---------|---------|---------|
| 记忆与经验 | 占位符 | `GET /api/memory/:sid` + `GET /api/lessons` | `api/data_views.py` → `JSONMemoryAdapter` + `JSONLessonsAdapter` |
| 任务看板 | 占位符 | `GET /api/tasks` | `api/tasks.py` → `task_dispatcher.py` |
| 学习中心 | 占位符 | `GET /api/brain/thoughts` + 需新增 | `api/brain_init.py` → `daemon._thought_log` |
| 大脑目标 | 未实现 | `GET /api/brain/goals` | `api/brain_init.py` → `GoalSystem` |
| 灵魂历史 | 未实现 | `GET /api/brain/soul/history` | `api/brain_init.py` → `SoulEngine` |
| 教学通道 | 未实现 | `GET /api/brain/teaching/inbox` + `POST /api/brain/teaching/reply` | `api/brain_init.py` → `TeacherChannel` |
