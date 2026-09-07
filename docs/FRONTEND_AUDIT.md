# LucidMind 前端功能脉络图 & 测试计划

> 生成时间: 2026-02-25  
> 版本快照: LucidMind-v1.0-snapshot-20260225_115841.tar.gz

---

## 一、页面总览（13个Tab）

```
┌─────────────────────────────────────────────────────────────┐
│  TOPBAR:  [≡菜单] [🧠LUCIDMIND] ... [状态] [模型选择] [🌙] │
├──────────┬──────────────────────────────────────────────────┤
│  NAV     │  CONTENT                                        │
│          │                                                  │
│ 对话     │  根据选中Tab渲染对应视图                          │
│  ▸ 对话  │                                                  │
│ 控制台   │                                                  │
│  ▸ 概览  │                                                  │
│  ▸ 会话  │                                                  │
│  ▸ 任务  │                                                  │
│ 大脑     │                                                  │
│  ▸ 状态  │                                                  │
│  ▸ 记忆  │                                                  │
│  ▸ 学习  │                                                  │
│ 连接     │                                                  │
│  ▸ 通道  │                                                  │
│  ▸ MCP   │                                                  │
│ 设置     │                                                  │
│  ▸ 插件  │                                                  │
│  ▸ 画像  │                                                  │
│  ▸ 配置  │                                                  │
│  ▸ 日志  │                                                  │
└──────────┴──────────────────────────────────────────────────┘
```

---

## 二、每页按钮/功能 完整审计

### 2.1 顶栏 (Topbar) — `app.js`

| # | 控件 | 功能 | API | 后端 | 状态 |
|---|------|------|-----|------|------|
| T1 | ≡ 菜单按钮 | 折叠/展开侧边栏 | 无(本地) | — | ✅ 正常 |
| T2 | 状态指示灯 | 显示 WebSocket 连接状态+心跳 | WebSocket ping/pong | websocket_channel.py | ✅ 正常 |
| T3 | 模型下拉选择 | 切换 LLM 模型 | POST /api/verify | main.py verify_config | ✅ 正常 |
| T4 | 🌙/☀ 主题切换 | 暗色/亮色主题 | 无(localStorage) | — | ✅ 正常 |

### 2.2 对话页 (Chat) — `views/chat.js`

| # | 控件 | 功能 | API | 后端 | 状态 |
|---|------|------|-----|------|------|
| C1 | 会话下拉选择 | 切换当前会话 | WebSocket switch_session + GET /api/sessions/{sid}/history | sessions.py | ✅ 正常 |
| C2 | ➕ 新建会话 | 创建新会话并切换 | POST /api/sessions | sessions.py | ✅ 正常 |
| C3 | 🗑 清除对话 | 清除当前对话历史 | DELETE /api/sessions/{sid}/history | sessions.py | ✅ 正常 |
| C4 | 🔄 刷新对话 | 重新加载对话历史 | GET /api/sessions/{sid}/history | sessions.py | ✅ 正常 |
| C5 | 🧠 思考开关 | 显示/隐藏思考过程 | 无(localStorage) | — | ✅ 正常 |
| C6 | 📎 上传文件 | 上传文件后自动发消息 | POST /api/upload → WebSocket chat | upload.py | ✅ 正常 |
| C7 | 输入框+发送 | 发送聊天消息 | WebSocket chat | websocket_channel → brain.process() | ✅ 正常 |
| C8 | ⏹ 停止按钮 | 中止当前生成 | WebSocket abort | websocket_channel.py | ✅ 正常 |
| C9 | 排队面板-编辑 | 编辑排队中的消息 | 无(本地Gateway) | — | ✅ 正常 |
| C10 | 排队面板-删除 | 删除排队中的消息 | 无(本地Gateway) | — | ✅ 正常 |
| C11 | 排队面板-强发 | 强制发送排队消息 | 无(本地Gateway) | — | ✅ 正常 |

**⚠️ 联动缺失:**
| # | 问题 | 严重度 |
|---|------|--------|
| C-BUG1 | 对话中用户输入任务（如"帮我每天检查天气"），Brain 创建任务后，**任务看板不会自动刷新**，需要手动切到任务Tab才看到 | 🔴 高 |
| C-BUG2 | Brain 工具调用结果中如果有创建文件/笔记等副作用，**前端没有任何通知**告知用户去哪里查看 | 🟡 中 |
| C-BUG3 | 对话历史加载时，**tool_call/tool_result 消息的 timestamp 为 null**（后端保存时没存时间戳） | 🟡 中 |

### 2.3 系统概览 (Overview) — `views/overview.js`

| # | 控件 | 功能 | API | 后端 | 状态 |
|---|------|------|-----|------|------|
| O1 | 4列统计卡 | 显示工具/插件/通道/MCP数 | GET /api/status + /api/plugins + /api/channel/status + /api/mcp/servers | 多个 | ✅ 正常 |
| O2 | 系统快照 | 连接、LLM、端口状态 | GET /api/status | main.py | ✅ 正常 |
| O3 | 大脑守护进程 | 思考次数、行动次数、队列 | GET /api/brain/status | brain_init.py | ✅ 正常 |
| O4 | 通道状态卡片 | 4通道配置状态 | GET /api/channel/status | channels.py | ✅ 正常 |
| O5 | 工具列表-刷新 | 刷新工具+插件数据 | 重新 fetch | — | ✅ 正常 |
| O6 | 工具列表 | 显示所有注册工具名 | GET /api/status (tools) | main.py | ✅ 正常 |
| O7 | 端口详情 | 六边形架构端口状态 | GET /api/status (ports) | main.py | ✅ 正常 |

**⚠️ 问题:**
| # | 问题 | 严重度 |
|---|------|--------|
| O-BUG1 | 概览数据**首次加载后不自动刷新**（_pluginData 等用模块级缓存，关闭页面再打开不重新获取） | 🟡 中 |

### 2.4 会话管理 (Sessions) — `views/sessions.js`

| # | 控件 | 功能 | API | 后端 | 状态 |
|---|------|------|-----|------|------|
| S1 | 刷新按钮 | 重新加载会话列表 | GET /api/sessions | sessions.py | ✅ 正常 |
| S2 | 新建按钮 | 创建新会话 | POST /api/sessions | sessions.py | ✅ 正常 |
| S3 | 会话标题点击 | 切换到该会话+跳转对话页 | 本地 _switchSession + _setTab("chat") | — | ✅ 正常 |
| S4 | 删除按钮 | 删除指定会话 | DELETE /api/sessions/{sid} | sessions.py | ✅ 正常 |

**⚠️ 问题:**
| # | 问题 | 严重度 |
|---|------|--------|
| S-BUG1 | **无法重命名会话** — 后端有 PUT /api/sessions/{sid}/title，前端 api.js 有 renameSession()，但 UI 没有重命名入口 | 🟡 中 |
| S-BUG2 | 消息数列 **始终显示 0** — sessions.py 返回的 message_count 可能未正确计算 | 🟡 中 |

### 2.5 任务看板 (Tasks) — `views/scheduler.js`

| # | 控件 | 功能 | API | 后端 | 状态 |
|---|------|------|-----|------|------|
| K1 | 定时任务/任务队列 Tab | 切换两个子视图 | — | — | ✅ 正常 |
| K2 | 刷新按钮 | 重载定时+队列数据 | GET /api/cron + GET /api/dispatcher/tasks | cron.py + data_views.py | ✅ 正常 |
| K3 | 全部/活跃/完成 过滤 | 过滤任务队列 | 本地过滤 | — | ✅ 正常 |
| K4 | 删除定时任务 | 删除一条 cron job | DELETE /api/cron/{job_id} | cron.py | ✅ 正常 |
| K5 | 删除队列任务 | 删除一条 dispatcher task | DELETE /api/dispatcher/tasks/{task_id} | data_views.py | ✅ 正常 |

**⚠️ 联动缺失:**
| # | 问题 | 严重度 |
|---|------|--------|
| K-BUG1 | **没有"新建任务"按钮** — 用户只能在对话中告诉 Brain 创建任务，无法手动添加 | 🟡 中 |
| K-BUG2 | **Brain Daemon 创建的任务不实时同步** — 用户在对话中说"帮我做xxx"，Brain 添加到队列，但任务看板不自动刷新 | 🔴 高 |
| K-BUG3 | **任务状态不自动更新** — 任务从 pending→running→done 的变化不会推送到前端 | 🔴 高 |

### 2.6 大脑状态 (Brain) — `views/brain.js` → renderBrain()

| # | 控件 | 功能 | API | 后端 | 状态 |
|---|------|------|-----|------|------|
| B1 | 状态/思考/行动/队列 | 纯展示 | GET /api/brain/status | brain_init.py | ✅ 正常 |

**⚠️ 问题:**
| # | 问题 | 严重度 |
|---|------|--------|
| B-BUG1 | **功能太简单** — 只有4个统计数字，没有目标管理、没有唤醒/休眠按钮、没有暂停/恢复按钮 | 🔴 高 |
| B-BUG2 | 后端有 GET /api/brain/goals, POST /api/brain/goals, GET /api/brain/thoughts, POST /api/brain/awaken, POST /api/brain/sleep, POST /api/brain/pause, POST /api/brain/resume — **全部未在前端暴露** | 🔴 高 |

### 2.7 记忆页 (Memory) — `views/brain.js` → renderMemory()

| # | 控件 | 功能 | API | 后端 | 状态 |
|---|------|------|-----|------|------|
| M1 | 统计卡片 | 会话消息数/经验总数/来源 | GET /api/memory/default + GET /api/lessons | data_views.py | ✅ 正常 |
| M2 | 刷新按钮 | 重载记忆数据 | 同上 | — | ✅ 正常 |
| M3 | 最近对话列表 | 展示最近20条消息 | GET /api/memory/default | data_views.py | ✅ 正常 |

**⚠️ 问题:**
| # | 问题 | 严重度 |
|---|------|--------|
| M-BUG1 | 固定查询 `default` 会话 — **没有跟随当前选中会话** | 🟡 中 |
| M-BUG2 | **无法删除/编辑单条记忆** | 🟢 低 |

### 2.8 学习中心 (Learning) — `views/brain.js` → renderLearning()

| # | 控件 | 功能 | API | 后端 | 状态 |
|---|------|------|-----|------|------|
| L1 | 统计卡片 | 经验总数/有效性均值/分层/来源 | GET /api/lessons | data_views.py | ✅ 正常 |
| L2 | 刷新按钮 | 重载经验数据 | 同上 | — | ✅ 正常 |
| L3 | 经验列表 | 展示前50条经验 | GET /api/lessons | data_views.py | ✅ 正常 |

**⚠️ 问题:**
| # | 问题 | 严重度 |
|---|------|--------|
| L-BUG1 | **无法删除无效经验** — 用户无法清理低质量经验 | 🟡 中 |
| L-BUG2 | 经验列表**不可搜索/过滤** | 🟢 低 |

### 2.9 消息通道 (Channels) — `views/channels.js`

| # | 控件 | 功能 | API | 后端 | 状态 |
|---|------|------|-----|------|------|
| CH1 | 刷新按钮 | 重载通道状态 | GET /api/channel/status | channels.py | ✅ 正常 |
| CH2 | 4通道卡片 | 展示配置状态+环境变量说明 | GET /api/channel/status | channels.py | ✅ 正常 |
| CH3 | Webhook 端点说明 | 纯文本展示 | — | — | ✅ 正常 |

**⚠️ 问题:**
| # | 问题 | 严重度 |
|---|------|--------|
| CH-BUG1 | **纯展示页面** — 没有启动/停止通道按钮，没有测试连接按钮 | 🟡 中 |
| CH-BUG2 | 没有在线配置环境变量的功能（只展示需要哪些变量） | 🟢 低 |

### 2.10 MCP 管理 — `views/mcp.js`

| # | 控件 | 功能 | API | 后端 | 状态 |
|---|------|------|-----|------|------|
| MC1 | 🔍 发现工具 | 扫描本机已安装MCP Server | POST /api/mcp/discover | mcp.py | ✅ 正常 |
| MC2 | ➕ 添加 | 展开/收起添加表单 | — | — | ✅ 正常 |
| MC3 | 添加表单-保存 | 添加新MCP Server | POST /api/mcp/servers | mcp.py | ✅ 正常 |
| MC4 | 刷新 | 重载服务器+工具列表 | GET /api/mcp/servers + /api/mcp/tools | mcp.py | ✅ 正常 |
| MC5 | 删除按钮 | 删除MCP Server | DELETE /api/mcp/servers/{name} | mcp.py | ✅ 正常 |
| MC6 | MCP工具列表 | 展示MCP提供的工具 | GET /api/mcp/tools | mcp.py | ✅ 正常 |

**状态: ✅ 完整，所有按钮都有实际功能。**

### 2.11 插件管理 (Plugins) — `views/plugins.js`

| # | 控件 | 功能 | API | 后端 | 状态 |
|---|------|------|-----|------|------|
| P1 | 🔄 热加载 | 重新扫描 skills/ 加载插件 | POST /api/plugins/reload | plugins.py | ✅ 正常 |
| P2 | 刷新 | 重载插件列表 | GET /api/plugins | plugins.py | ✅ 正常 |
| P3 | 启用/禁用按钮 | 切换单个插件状态 | PUT /api/plugins/{name}/toggle | plugins.py | ✅ 正常 |

**⚠️ 问题:**
| # | 问题 | 严重度 |
|---|------|--------|
| P-BUG1 | **PluginHub 搜索 UI 缺失** — 后端有 GET /api/plugins/hub/search 和 POST /api/plugins/hub/install，但前端**没有搜索框和安装按钮** | 🔴 高 |

### 2.12 用户画像 (Profile) — `views/profile.js`

| # | 控件 | 功能 | API | 后端 | 状态 |
|---|------|------|-----|------|------|
| PR1 | 编辑按钮 | 进入编辑模式 | — | — | ✅ 正常 |
| PR2 | 保存按钮 | 保存用户画像 | PUT /api/user-profile | data_views.py | ✅ 正常 |
| PR3 | 取消按钮 | 退出编辑模式 | — | — | ✅ 正常 |

**状态: ✅ 完整，功能正常。**

### 2.13 系统配置 (Config) — `views/config.js`

| # | 控件 | 功能 | API | 后端 | 状态 |
|---|------|------|-----|------|------|
| CF1 | 测试并应用按钮 | 验证LLM配置 | POST /api/verify | main.py | ✅ 正常 |
| CF2 | 自动执行开关 | 暂停/恢复 Brain Daemon | POST /api/brain/pause 或 /resume | brain_init.py | ✅ 正常 |
| CF3 | 思考间隔选择 | 设置 OODA 循环间隔 | POST /api/brain/interval | brain_init.py | ✅ 正常 |
| CF4 | 自动求助老师 | 开关自动求助 | POST /api/brain/auto-ask | brain_init.py | ✅ 正常 |
| CF5 | 思考过程开关 | 显示/隐藏思考 | 无(localStorage) | — | ✅ 正常 |

**⚠️ 问题:**
| # | 问题 | 严重度 |
|---|------|--------|
| CF-BUG1 | **安全配置未暴露** — 后端有完整的 /api/security/* API，前端没有安全设置面板 | 🟡 中 |

### 2.14 事件日志 (Logs) — `views/logs.js`

| # | 控件 | 功能 | API | 后端 | 状态 |
|---|------|------|-----|------|------|
| LG1 | 清空按钮 | 清空本地日志 | 无(本地) | — | ✅ 正常 |
| LG2 | 日志列表 | 展示 WebSocket 事件日志 | 无(本地) | — | ✅ 正常 |

**状态: ✅ 功能正常（纯本地日志，不涉及后端）。**

### 2.15 全局模态框

| # | 控件 | 功能 | API | 后端 | 状态 |
|---|------|------|-----|------|------|
| G1 | 工具审批弹窗 | 危险工具执行前确认 | WebSocket tool_approval_response | tool_safety.py | ✅ 正常 |
| G2 | 断线重连提示 | 显示断线状态 | WebSocket | — | ✅ 正常 |

---

## 三、数据流脉络图

### 3.1 对话 → 任务 联动链路（✅ 已修复）

```
用户输入 "帮我每天查天气"
  │
  ▼
[WebSocket chat] → brain.process()
  │
  ├─ LLM 决定调用工具 → set_reminder / add_task
  │   │
  │   ▼
  │  TaskDispatcher.enqueue()  ← 任务已创建（后端）
  │   │
  │   ✓ _notify("task_created", task) → WebSocket broadcast  ← ✅ 已修复
  │   │
  │   ▼
  │  前端监听 lucid-task-updated 事件 → scheduler.js 自动刷新
  │
  ├─ Brain 返回回复 → WebSocket response
  │
  ▼
前端显示回复 + 任务看板已自动更新
```

**修复实现:**
1. task_dispatcher.py 添加 register_notify_hook / _notify 钩子系统
2. api/main.py 注册 _task_notify_hook → WebSocket broadcast
3. app.js 处理 task_updated 消息 → dispatchEvent("lucid-task-updated")
4. scheduler.js 监听事件自动刷新数据

### 3.2 插件 → 工具列表 联动链路（正常 ✅）

```
用户点击 "热加载"
  │
  ▼
POST /api/plugins/reload → skills/__init__.py 重新扫描
  │
  ├─ 返回 {plugins: N, tools: M}
  │
  ▼
前端 _loadPlugins() → 刷新插件列表 ✅
概览页 tools 列表 → 需要手动刷新 ⚠️
```

### 3.3 MCP → 工具注入链路（正常 ✅）

```
用户添加 MCP Server → POST /api/mcp/servers
  │
  ▼
点击 "发现工具" → POST /api/mcp/discover
  │
  ▼
MCPClientAdapter.discover() → 连接 MCP Server → 获取工具
  │
  ▼
CompositeToolAdapter._rebuild_map() → Brain 可调用新工具 ✅
```

### 3.4 安全审批链路（正常 ✅）

```
Brain 调用 run_shell → CompositeToolAdapter.execute()
  │
  ▼
ToolSafetyGuard.check() → classify("run_shell") = "dangerous"
  │
  ▼
WebSocket 推送 tool_approval_request → 前端弹窗
  │
  ├─ 用户点「允许」→ tool_approval_response(approved=true)
  │   └→ guard.handle_approval_response() → Future.set_result → 继续执行
  │
  └─ 用户点「拒绝」→ tool_approval_response(approved=false)
      └→ 返回 {success: false, error: "用户拒绝"} → Brain 告知用户
```

---

## 四、问题汇总 & 严重度分级

### 🔴 高优先级 — 全部已修复 ✅

| ID | 页面 | 问题描述 | 状态 |
|----|------|----------|------|
| C-BUG1 | 对话 | Brain创建任务后，任务看板不自动刷新 | ✅ task_updated WebSocket推送 |
| K-BUG2 | 任务 | 对话中创建的任务不实时同步到任务看板 | ✅ lucid-task-updated事件 |
| K-BUG3 | 任务 | 任务状态变化不推送前端 | ✅ complete/fail/block均推送 |
| B-BUG1 | 大脑 | 大脑页面功能过于简单，缺少唤醒/休眠/暂停/恢复/目标管理 | ✅ 全部添加 |
| B-BUG2 | 大脑 | 6个后端API未暴露到前端 | ✅ goals/thoughts/awaken/sleep/pause/resume |
| P-BUG1 | 插件 | PluginHub搜索安装UI缺失 | ✅ 搜索框+结果+一键安装 |

### 🟡 中优先级 — 全部已修复 ✅

| ID | 页面 | 问题描述 | 状态 |
|----|------|----------|------|
| C-BUG2 | 对话 | 工具执行副作用无通知 | ✅ task_updated推送解决 |
| C-BUG3 | 对话 | tool_call/tool_result 时间戳缺失 | ✅ save_message已自动添加timestamp |
| S-BUG1 | 会话 | 无法重命名会话 | ✅ 双击标题重命名 |
| S-BUG2 | 会话 | 消息数始终为0 | ✅ 显示 message_count/messages |
| O-BUG1 | 概览 | 概览数据不自动刷新 | ✅ 30s自动刷新 |
| K-BUG1 | 任务 | 没有手动新建任务按钮 | ✅ 新建任务按钮+表单+优先级选择 |
| M-BUG1 | 记忆 | 记忆页固定查default，不跟随当前会话 | ✅ 跟随 currentSession |
| L-BUG1 | 学习 | 无法删除无效经验 | ✅ 删除按钮已加 |
| CH-BUG1 | 通道 | 纯展示页，没有启停/测试按钮 | ✅ 测试连接+重启按钮+状态反馈 |
| CF-BUG1 | 配置 | 安全配置面板缺失 | ✅ 审批开关+工具列表 |

### 🟢 低优先级 — 全部已修复 ✅

| ID | 页面 | 问题描述 | 状态 |
|----|------|----------|------|
| M-BUG2 | 记忆 | 无法删除/编辑单条记忆 | ✅ 单条删除按钮已加 |
| L-BUG2 | 学习 | 经验列表不可搜索/过滤 | ✅ 搜索框已加 |
| CH-BUG2 | 通道 | 不能在线配置环境变量 | ⚠️ 安全考虑暂缓(需服务器重启生效) |

---

## 五、完整测试计划

### 5.1 测试类别

| 类别 | 内容 | 测试方式 |
|------|------|----------|
| A. 页面渲染 | 每个Tab能正常渲染，无JS报错 | 手动点击 |
| B. 按钮功能 | 每个按钮点击后有预期效果 | 手动点击 |
| C. 数据加载 | API数据正确加载和显示 | 手动验证 |
| D. 端到端联动 | 对话→任务、插件→工具等链路 | 手动验证 |
| E. 异常处理 | 网络断开、API报错时的表现 | 模拟异常 |
| F. 自动化API | pytest 覆盖所有API | 自动运行 |

### 5.2 详细测试用例

#### A. 页面渲染测试 (13项)

| 用例ID | 步骤 | 预期结果 | 合格标准 |
|--------|------|----------|----------|
| A-01 | 点击"对话"Tab | 对话界面渲染，输入框可用 | 无JS错误，可输入文字 |
| A-02 | 点击"概览"Tab | 4列统计卡显示数据 | 所有数字非undefined |
| A-03 | 点击"会话"Tab | 会话列表渲染 | 至少显示1个会话 |
| A-04 | 点击"任务"Tab | 定时任务/队列Tab渲染 | Tab可切换 |
| A-05 | 点击"大脑"Tab | 4个统计数字显示 | 无undefined |
| A-06 | 点击"记忆"Tab | 消息和经验统计显示 | 无加载卡死 |
| A-07 | 点击"学习"Tab | 经验列表渲染 | 无加载卡死 |
| A-08 | 点击"通道"Tab | 4通道卡片渲染 | 显示环境变量说明 |
| A-09 | 点击"MCP"Tab | 服务器列表渲染 | 统计数字正确 |
| A-10 | 点击"插件"Tab | 插件列表渲染 | 运行中/已禁用数正确 |
| A-11 | 点击"画像"Tab | 用户画像内容显示 | Markdown正确渲染 |
| A-12 | 点击"配置"Tab | 表单控件渲染 | 下拉框可选择 |
| A-13 | 点击"日志"Tab | 日志列表渲染 | 至少有系统事件 |

#### B. 按钮功能测试 (30+项)

| 用例ID | 页面 | 步骤 | 预期结果 |
|--------|------|------|----------|
| B-01 | 对话 | 输入文字→Enter发送 | 消息出现，Brain回复 |
| B-02 | 对话 | 点击➕新建会话 | 新会话创建，切换到新会话 |
| B-03 | 对话 | 点击🗑清除对话 | confirm弹窗→清空消息列表 |
| B-04 | 对话 | 点击🔄刷新 | 重新加载历史（旋转动画） |
| B-05 | 对话 | 切换会话下拉 | 消息列表切换，加载新历史 |
| B-06 | 对话 | 点击🧠思考开关 | 思考过程显示/隐藏切换 |
| B-07 | 对话 | 点击📎上传文件 | 文件选择器打开 |
| B-08 | 对话 | 生成中点击⏹停止 | 生成中止 |
| B-09 | 会话 | 点击"刷新" | 会话列表重载 |
| B-10 | 会话 | 点击"新建" | 新会话出现在列表 |
| B-11 | 会话 | 点击会话标题 | 跳转到对话页+切换 |
| B-12 | 会话 | 点击"删除" | confirm→会话删除 |
| B-13 | 任务 | 点击"定时任务"Tab | 定时任务列表显示 |
| B-14 | 任务 | 点击"任务队列"Tab | 队列列表显示 |
| B-15 | 任务 | 点击刷新 | 数据重载 |
| B-16 | 任务 | 点击过滤按钮 | 列表过滤 |
| B-17 | 任务 | 点击删除任务 | confirm→任务删除 |
| B-18 | MCP | 点击"发现工具" | 发现数显示 |
| B-19 | MCP | 点击"添加"→填表→保存 | 新Server出现在列表 |
| B-20 | MCP | 点击"删除" | Server从列表消失 |
| B-21 | MCP | 点击"刷新" | 数据重载 |
| B-22 | 插件 | 点击"热加载" | 成功消息显示 |
| B-23 | 插件 | 点击"启用/禁用" | 状态切换 |
| B-24 | 插件 | 点击"刷新" | 数据重载 |
| B-25 | 画像 | 点击"编辑" | 文本编辑器出现 |
| B-26 | 画像 | 编辑后点"保存" | 内容保存成功 |
| B-27 | 画像 | 点击"取消" | 回到查看模式 |
| B-28 | 配置 | 点击"测试并应用" | 验证结果显示 |
| B-29 | 配置 | 切换"自动执行" | Brain暂停/恢复 |
| B-30 | 日志 | 点击"清空" | 日志列表清空 |
| B-31 | 顶栏 | 点击模型下拉切换 | 模型切换成功/失败提示 |
| B-32 | 顶栏 | 点击主题切换 | 暗色/亮色切换 |

#### C. 端到端联动测试 (6项)

| 用例ID | 场景 | 步骤 | 预期结果 | 当前状态 |
|--------|------|------|----------|----------|
| E2E-01 | 对话→任务 | 在对话中说"帮我每小时查天气" | 任务看板自动出现新任务 | ❌ 不联动 |
| E2E-02 | 对话→笔记 | 在对话中说"记个笔记：xxx" | 记忆页显示新笔记 | ❌ 不联动 |
| E2E-03 | 插件热加载→工具 | 热加载后概览页工具列表更新 | 工具列表自动刷新 | ⚠️ 需手动刷新 |
| E2E-04 | MCP添加→工具 | 添加MCP Server后发现工具 | 工具注入Brain | ✅ 正常 |
| E2E-05 | 安全审批 | 让Brain执行run_shell | 弹出审批弹窗 | ✅ 正常 |
| E2E-06 | 会话切换→历史 | 会话Tab切到另一个会话 | 对话页加载对应历史 | ✅ 正常 |

### 5.3 合格标准

#### 最低合格（上线门槛）

1. **所有13个Tab能正常渲染**，无JS报错（控制台无红色Error）
2. **所有按钮点击有响应**（即使是toast提示"功能开发中"也算，不能无响应）
3. **对话功能完整**: 发送→接收→历史加载→会话切换
4. **API 返回正确**: E2E测试 25/25 通过

#### 良好合格（推荐标准）

5. **联动打通**: 对话中创建的任务/笔记，在对应页面自动可见（不需手动刷新）
6. **大脑页面完整**: 目标管理+唤醒/休眠+暂停/恢复 全部可操作
7. **PluginHub 搜索安装**: 能搜索+一键安装插件
8. **会话可重命名**
9. **概览数据自动刷新**

#### 优秀合格（目标标准）

10. **实时推送**: 任务状态变化通过 WebSocket 推送到前端
11. **安全配置 UI**: 在设置页面管理危险工具列表
12. **通道管理**: 启停按钮+测试连接
13. **经验管理**: 搜索+删除无效经验

---

## 六、后端已有但前端未暴露的 API

| API | 功能 | 所属模块 |
|-----|------|----------|
| POST /api/brain/awaken | 唤醒大脑 | brain_init.py |
| POST /api/brain/sleep | 休眠大脑 | brain_init.py |
| POST /api/brain/pause | 暂停Daemon | brain_init.py |
| POST /api/brain/resume | 恢复Daemon | brain_init.py |
| GET /api/brain/goals | 获取大脑目标 | brain_init.py |
| POST /api/brain/goals | 设置大脑目标 | brain_init.py |
| GET /api/brain/thoughts | 获取思考历史 | brain_init.py |
| GET /api/brain/soul/history | 获取灵魂历史 | brain_init.py |
| GET /api/brain/teaching/inbox | 教学收件箱 | brain_init.py |
| POST /api/brain/teaching/reply | 教学回复 | brain_init.py |
| GET /api/brain/teaching/status | 教学状态 | brain_init.py |
| GET /api/plugins/hub/search | PluginHub搜索 | plugins.py |
| POST /api/plugins/hub/install | PluginHub安装 | plugins.py |
| PUT /api/sessions/{sid}/title | 重命名会话 | sessions.py |
| GET /api/security/config | 安全配置 | security.py |
| POST /api/security/toggle | 启停安全审批 | security.py |
| POST /api/security/classify | 工具分类 | security.py |
| GET /api/ab-test | A/B测试数据 | data_views.py |
| PUT /api/ab-test | 切换A/B测试 | data_views.py |

---

## 七、修复优先级执行计划

### 第1批: 🔴 高优先级 — 全部完成 ✅

1. ✅ **大脑页面增强** — 唤醒/休眠、暂停/恢复按钮，目标查看，思考历史
2. ✅ **任务联动** — task_dispatcher 钩子 → WebSocket broadcast → 前端自动刷新
3. ✅ **PluginHub UI** — 搜索框+结果+一键安装

### 第2批: 🟡 中优先级 — 大部分完成 ✅

4. ✅ **会话重命名** — 双击标题触发 prompt
5. ✅ **记忆页跟随会话** — 使用 app.currentSession
6. ✅ **经验搜索+删除** — 搜索框 + 删除按钮
7. ✅ **概览自动刷新** — 30s定时刷新
8. ✅ **安全配置面板** — 审批开关 + 危险/敏感工具列表
