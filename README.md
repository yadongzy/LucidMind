# LucidMind — 可扩展的 AI Agent 平台

> **执行任务、调用工具、无限扩展。**
> 标准化插件协议，透明思维过程，自主决策。

## 架构

六边形架构（Ports & Adapters）— Brain 只认识接口，不认识实现。

```
         ┌───────────────────────────────────────────┐
         │          Brain 单例 (跨连接持续存活)        │
         │  process() + _sessions + set_stream()  │
         │  🧠 Daemon(后台思考) + 🎯 Goals(目标驱动)  │
         └─┬──┬──┬──┬──┬──┬──┬────────────────────┘
           │  │  │  │  │  │  │
     ┌────┴┐┌┴──┐┌┴──┐┌┴──┐┌┴──┐┌┴──┐┌┴────────┐
     │ LLM ││Tool││Mem ││Strm││Lrn ││Ref ││Channel │
     │ Port││Port││Port││Port││Port││Port││Port    │
     └──┬──┘└┬───┘└┬───┘└┬───┘└┬───┘└┬───┘└┬────────┘
        │    │    │    │    │    │    │
     DeepSk 18Tool JSON  WS  JSON JSON  WS Channel
     +Local +Plugin      HTTP       Refl  Adapter
```

## 功能清单 (S0-S57)

| 类别 | 功能 |
|------|------|
| **核心** | 六边形架构, Brain 单例推理循环, Ralph 永不放弃 |
| **意识** | 🧠 后台思考+自主行动, 🧬 动态灵魂进化, 🎯 目标驱动, 真实元认知(LLM), 自我评估 |
| **LLM** | DeepSeek + qwen3:8b 保底, SpecialKB 缓存, Provider 健康追踪+冷却 |
| **工具 (19个)** | Shell, File, WebSearch, SearchFiles, Document, Browser, Image, FileAnalyze, Vision, TTS, STT, SubAgent, Plugins |
| **记忆** | JSON 持久化, 多会话管理, LLM摘要压缩, 向量语义检索, 用户画像 |
| **透明度** | 实时思维流, LLM深度元认知, 任务规划器, 经验学习, 自省 |
| **前端** | WebSocket 流式, 代码高亮+复制, typing指示, 主题切换, 🧠大脑状态面板, 消息搜索+导出, 移动端适配 |
| **通道** | WebSocket(ChannelPort) + HTTP API + CLI |
| **安全** | JWT全链路认证(注册→登录→WS传token→session隔离→登出), 命令黑名单, 敏感路径保护 |
| **个性化** | 用户画像(user_profile.md), 纠正学习, 高频纠正自动写入永久规则 |
| **主动服务** | Daemon健康监控, 磁盘/日志/数据异常告警, 事件驱动唤醒 |
| **扩展** | 技能插件(skills/), 子代理并行, 错误恢复, Docker部署, MCP协议 |

## 快速开始

### 一键安装+启动（推荐）

**Linux / macOS:**
```bash
chmod +x install.sh start.sh
./install.sh          # 一键安装（创建虚拟环境+安装依赖+构建前端）
# 编辑 .env 填入 API Key
./start.sh            # 一键启动（自动打开浏览器）
```

**Windows:**
```
双击 install.bat      # 一键安装
# 编辑 .env 填入 API Key
双击 start.bat        # 一键启动（自动打开浏览器）
```

### 手动安装

```bash
# 1. 创建虚拟环境
python3 -m venv venv && source venv/bin/activate  # Linux/macOS
python -m venv venv && venv\Scripts\activate       # Windows

# 2. 安装依赖
pip install -r requirements.txt

# 3. 配置环境变量
cp .env.example .env  # 或手动创建 .env
# 编辑 .env 填入 DEEPSEEK_API_KEY

# 4. 启动服务器
python -m uvicorn api.main:app --host 0.0.0.0 --port 8765

# 5. 打开浏览器 http://localhost:8765
```

## 项目结构

```
LucidMind/
├── brain.py              # 核心推理引擎 (单例, ~496行)
├── ports/                # 六个 Port 接口
│   ├── llm_port.py
│   ├── tool_port.py
│   ├── memory_port.py
│   ├── stream_port.py
│   ├── channel_port.py
│   ├── learning_port.py
│   └── reflection_port.py
├── adapters/             # 适配器实现
│   ├── llm/              # DeepSeek + Fallback
│   ├── tools/            # 18个工具适配器
│   ├── memory/           # JSON 记忆
│   ├── stream/           # WebSocket + Collect
│   ├── channel/          # WebSocket Channel (S34)
│   ├── learning/         # 经验学习 + SpecialKB
│   ├── reflection/       # 自省
│   └── recovery.py       # 错误恢复
├── brain_daemon.py       # 后台思考循环 (S31)
├── identity/             # 灵魂与目标
│   ├── SOUL.md           # 灵魂定义(可进化)
│   ├── soul_engine.py    # 灵魂进化引擎 (S32)
│   └── goals.py          # 目标系统 (S33)
├── api/                  # FastAPI 路由
│   ├── main.py           # 主入口 (178行)
│   ├── sessions.py       # 会话管理
│   ├── http_chat.py      # HTTP 对话通道
│   ├── data_views.py     # 记忆/经验可视化
│   ├── upload.py         # 文件上传
│   ├── tasks.py          # 异步任务
│   ├── cron.py           # 定时任务
│   └── brain_init.py     # 大脑生命周期 (S30-S33)
├── frontend/             # 前端
│   ├── console.html
│   ├── console.js        # 主逻辑
│   ├── ux_enhance.js     # UX增强 (S27)
│   └── console.css
├── skills/               # 技能插件（自动发现+加载）
├── user_profile.md       # 用户画像（可编辑，注入system prompt）
├── tests/                # 测试
├── .rules/               # 项目规则体系
└── data/                 # 数据存储
```

## 规则体系

13条规则（`.rules/00-12`），核心铁律：
- **第零条**: 项目存在的理由 — 思维透明
- **第一条**: 六边形架构 — Brain 不认识 Adapter
- **第八条**: 诚实铁律 — 不凑合、不编造、不蒙混
- **第十一条**: 测试铁律 — 所有功能必须真实浏览器验证

## 测试

```bash
# 单元测试
python -m pytest tests/test_brain.py -v

# 浏览器测试
python tests/test_s20_s23_browser.py
```

## 插件系统

标准化插件协议，每个插件是一个目录，包含 `manifest.json` 和入口文件：

```
skills/my_plugin/
  manifest.json    # 插件描述
  main.py          # 入口文件
```

**manifest.json:**
```json
{
  "name": "my_plugin",
  "version": "1.0.0",
  "description": "我的自定义插件",
  "entry": "main.py",
  "tools": ["my_tool"],
  "platform": [],
  "dependencies": [],
  "enabled": true
}
```

**main.py:**
```python
from ports.tool_port import ToolPort

class MyPluginAdapter(ToolPort):
    def list_tools(self):
        return [{"type": "function", "function": {
            "name": "my_tool",
            "description": "我的自定义工具",
            "parameters": {"type": "object", "properties": {}}
        }}]

    async def execute(self, tool_name, params):
        return {"success": True, "result": "Hello!"}
```

内置插件：`clipboard`（剪贴板）、`project_context`（项目扫描）、`reminder`（定时提醒）。
可通过前端插件管理页面或 API (`/api/plugins`) 查看和启用/禁用。

## 用户画像

编辑 `user_profile.md` 自定义大脑行为：

```markdown
# 用户画像
## 基本信息
- 称呼: 你的名字
- 语言偏好: 中文
## 安全规则
- 删除文件前必须先预览
```

大脑会自动读取并注入 system prompt。用户多次纠正同一个问题时，大脑会自动将其写入此文件作为永久规则。

## 许可

MIT
