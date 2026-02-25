# LucidMind 变更日志

> **规则：每次代码改动必须在此文件记录。不记录 = 违反规则。**

---

## v1.3 (2026-02-26)

### 验证确认（C5-C8 已在代码中实现）
- **C5**: `brain.py:246` — 只在 `_tool_calls_happened` 时标记经验有效（简单问候不算）
- **C6**: daemon 通过 `brain.process()` 调用，已包含 effectiveness 标记逻辑
- **C7**: `metacognition.py:107` — 深度元认知超时已改为 15s
- **C8**: `brain_engines.py:292` — `evolve()` 已接入学习引擎定时调用

### 工程质量（D1-D5）
- **D1**: `test_e2e_api.py` 25/25 测试全部通过
- **D3**: 9 个死代码文件移到 `adapters/tools/_deprecated/`
  - cascade_comm.py, clipboard.py, doubao_comm.py, gui_automation.py,
    notification.py, plugin_loader.py, stt.py, tts.py, vision.py
- **D4**: 15 个根目录散落文件移到 `_deprecated/`
  - 6 个分析 .md、probe_port.py、self_eval.py、integrated_lessons.json、
    user_preferences.json、user_profile.md、SOUL.md.deprecated、GPT.md、邯郸天气*.txt
- **D5**: `brain_daemon.py` 389行→162行（提取 `brain_daemon_observe.py` DaemonObserveMixin）

### 修改
- `brain_daemon.py`: 继承 `DaemonObserveMixin`，观察/健康/教学方法全部提取
- `STRATEGY.md`: C5-C8, D1-D5, E1 全部标记 ✅

---

## v1.2 (2026-02-26)

### 新增
- **Skill Scanner 安全扫描**（A4）：`skills/skill_scanner.py`
  - 13种危险模式检测：挖矿、数据外泄、反向Shell、eval/exec、subprocess、env读取等
  - 三级分类：CRITICAL（阻止安装）、WARNING（警告）、INFO（记录）
  - 集成到 `install_from_hub()`：下载后扫描，CRITICAL 直接删除拒绝安装
- **Skill Creator 自动创建**（A5）：`skills/skill_creator.py`
  - PluginHub 无匹配时自动生成 manifest.json + main.py
  - 生成后自动经过 skill_scanner 安全扫描
  - 集成到 `brain_resilience.py` `_auto_create_skill()` 方法
  - 完整闭环：_on_tool_not_found → 搜索PluginHub → 无结果 → 自动创建 → 扫描 → 热加载
- **MCP 连接健康监控+自动重连**（B5）：`mcp_client.py`
  - `health_check()` 方法：检查所有 MCP Server 连接状态
  - `_reconnect_server()` 方法：自动重连断开的服务器（最多3次）
  - `execute()` 中集成：服务器断开或无响应时自动重连再重试
  - `GET /api/mcp/health` API 端点
- **MCP 工具名冲突治理**（B6）：`mcp_client.py`
  - `discover()` 中检测工具名冲突，跳过重复工具并记录日志

### 修改
- `skills/__init__.py`：平台检查支持 `"all"` 字符串匹配所有平台
- `skills/__init__.py`：`install_from_hub()` 集成安全扫描（本地启用和远程下载两个路径）
- `brain_resilience.py`：`_on_tool_not_found` 搜索无结果时回退到 `_auto_create_skill`
- `api/mcp.py`：新增 `/api/mcp/health` 端点
- STRATEGY.md：A4/A5/B4/B5/B6 全部标记 ✅

### 测试验证
- skill_scanner：扫描全部16个 skills，正确识别 code_runner 的 CRITICAL（false positive in blacklist comment）
- skill_creator：创建 auto_test_tool（2个工具），安全扫描通过，热加载成功
- _on_tool_not_found 完整链路：magic_spell_cast → PluginHub无结果 → 自动创建 auto_magic_spell → 成功
- MCP auto-reconnect：Kill filesystem 进程 → execute 自动重连 → 执行成功
- MCP health_check：2个服务器均返回 healthy

---

## v0.3.3 (2026-02-25)

### 新增
- **PluginHub registry.json**（A1）：收录 16 个 skills，支持远程+本地回退
- **`_on_tool_not_found` 自动搜索安装**（A3）：`brain_resilience.py` 新增方法
  - 工具未注册 → 搜索 PluginHub → 精确匹配 tool 名 → 自动安装 → 热加载 → 立即重试
  - 集成到 `_tool_call_with_retry` 中，无需额外代码路径
- **MCP filesystem Server 接入**（B1+B2）：14 个文件操作工具，list/write/read 端到端验证通过
- **MCP memory Server 接入**（B1+B3）：9 个知识图谱工具，create_entities/search_nodes 端到端验证通过
- 总计：2 个 MCP Server，23 个外部工具注入 Brain

### 修改
- `skills/__init__.py`：`refresh_hub_registry()` 支持本地 registry.json 回退
- `skills/__init__.py`：`install_from_hub()` 本地已存在时直接启用+热加载，不重复下载
- `api/plugins.py`：移除 `install_from_hub` 中冗余的 `hot_reload()` 调用
- `data/mcp_servers.json`：配置 filesystem + memory 两个 MCP Server
- STRATEGY.md：A1/A2/A3/B1/B2/B3 标记 ✅

---

## v0.3.2 (2026-02-25)

### 变更
- STRATEGY.md 3B MCP 工作流深度扩展：基于 OpenClaw mcporter skill 代码深度研究
  - 新增 B5（连接健康监控）、B6（工具名冲突治理）两个任务项
  - 新增 mcporter 完整架构分析（list/call/auth/config/daemon/codegen）
  - 新增 4 个关键设计模式分析（CLI桥接器、统一调用面、工具注入、确定性分发）
  - 新增 LucidMind vs mcporter 10 维度对比表
  - 明确 LucidMind 的 3 个结构性优势（直接集成、Python原生、无shell中转）
  - 明确 5 个缺失项（连接保活、工具名冲突、OAuth认证、ad-hoc Server、端到端验证）

---

## v0.3.1 (2026-02-25)

### 变更
- STRATEGY.md Phase 3 全面重构：基于 OpenClaw 代码深度对标分析
  - 3A: Skill 生态（PluginHub仓库 + 前端安装 + 大脑自动搜索安装 + Skill Creator + 安装时安全扫描）
  - 3A 补齐：Skill Creator (A5) 从 Phase 4 提升到 Phase 3 P0，形成完整工具发现闭环
  - 3B: MCP 工作流（实际接入 MCP Server + 两个端到端工作流验证）
  - 3C: 记忆系统加固（effectiveness修正 + daemon有效性闭环）
  - 3D: 工程质量（回归测试 + 死代码清理）
  - 3E: 安全加固（安装时静态代码扫描，对标 OpenClaw skill-scanner.ts）
  - 明确 P0/P1/P2 执行顺序
  - Phase 4 加入 Skill Creator 和多角色配置

---

## v0.3.0-feishu-voice (2026-02-25)

### 新增
- 飞书语音消息支持：下载音频 → Whisper STT → Brain处理 → 文字回复
- 飞书 SDK 长连接模式（无需公网域名/ngrok）
- Whisper 模型缓存（避免每次语音消息重新加载）
- `.zshrc` 添加 `proxy_on` / `proxy_off` 快捷命令

### 修复
- 修复全通道 `Brain._stream` → `Brain.stream` 属性名错误（飞书/微信/企微/Telegram/Teacher API）
- 修复飞书回复消息静默失败（添加HTTP响应状态日志）
- 修复飞书 WebSocket 连接被 Little Snitch Network Extension 内核级拦截（关闭 Network Extension）
- 注释 `.zshrc` 中硬编码的 Clash 代理变量（Clash 未运行时导致所有外网超时）

### 变更
- 飞书适配器清除代理环境变量 + 禁用 IPv6（避免 SDK 连接失败）

---

## v0.2.0 (2026-02-25)

### Phase 1 + Phase 2 完成
- 代码大清理（33个废弃.py + 28个脚本 → archive/）
- 15个内置插件（35个工具）
- MCP 协议完整兼容（stdio + http）
- PluginHub 自动搜索安装
- 插件热加载
- 前端仪表盘 + 插件/MCP/通道 UI
- Telegram / 飞书 / 企业微信 / 微信 四通道
- 工具安全审批流
- E2E 自动化测试（25个用例）
- 经验管理器 memory_curator.py（选择性添加 + 组合删除）
- 经验分层（strategy/fact/temp）
- 向量语义检索（Ollama nomic-embed-text）

---

## 日志格式

```
## vX.Y.Z (YYYY-MM-DD)

### 新增
- 新功能描述

### 修复
- Bug修复描述

### 变更
- 行为变更描述

### 删除
- 移除的功能/文件
```
