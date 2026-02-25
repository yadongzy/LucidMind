# LucidMind 变更日志

> **规则：每次代码改动必须在此文件记录。不记录 = 违反规则。**

---

## v0.3.1 (2026-02-25)

### 变更
- STRATEGY.md Phase 3 全面重构：基于 OpenClaw 代码深度对标分析
  - 3A: Skill 生态（PluginHub仓库 + 前端安装 + 大脑自动搜索安装 + 安装时安全扫描）
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
