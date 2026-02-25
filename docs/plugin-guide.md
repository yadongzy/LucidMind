# LucidMind 插件开发指南

> 10 分钟写一个插件，热加载立即可用。

---

## 快速开始

### 1. 创建插件目录

```bash
mkdir -p skills/my_plugin
```

### 2. 创建 manifest.json

```json
{
  "name": "my_plugin",
  "version": "1.0.0",
  "description": "我的第一个插件",
  "author": "你的名字",
  "entry": "main.py",
  "tools": ["my_tool"],
  "platform": [],
  "dependencies": [],
  "enabled": true
}
```

**字段说明：**

| 字段 | 必填 | 说明 |
|------|------|------|
| `name` | ✅ | 插件唯一标识 |
| `version` | ✅ | 语义版本号 |
| `description` | ✅ | 一句话描述（显示在 UI 中） |
| `author` | | 作者 |
| `entry` | | 入口文件名（默认 `main.py`） |
| `tools` | ✅ | 工具名列表（供 LLM 调用） |
| `platform` | | 平台限制，如 `["darwin"]`。空数组 = 全平台 |
| `dependencies` | | Python 依赖包 |
| `enabled` | | 是否启用（默认 `true`） |

### 3. 创建 main.py

```python
"""我的插件 — 一句话描述。"""

from typing import Any
from ports.tool_port import ToolPort


class MyPluginAdapter(ToolPort):
    """类名必须以 Adapter 结尾。"""

    def list_tools(self) -> list[dict[str, Any]]:
        """声明工具定义（OpenAI function calling 格式）。"""
        return [
            {
                "type": "function",
                "function": {
                    "name": "my_tool",
                    "description": "这个工具做什么（LLM 根据此描述决定是否调用）",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "input": {
                                "type": "string",
                                "description": "参数说明",
                            },
                        },
                        "required": ["input"],
                    },
                },
            },
        ]

    async def execute(self, tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
        """执行工具调用。"""
        if tool_name == "my_tool":
            value = params.get("input", "")
            # 你的逻辑
            return {"success": True, "result": f"处理完成: {value}"}
        return {"success": False, "error": f"未知工具: {tool_name}"}
```

### 4. 热加载

在前端插件管理页面点击「🔄 热加载」按钮，或调用 API：

```bash
curl -X POST http://localhost:8765/api/plugins/reload
```

**无需重启服务器**，插件立即可用。

---

## 返回格式

`execute()` 方法必须返回 dict，包含以下字段：

```python
# 成功
{"success": True, "result": "工具输出文本"}

# 失败
{"success": False, "error": "错误原因"}
```

`result` 的值会被 LLM 读取并用于生成回复。保持简洁、有结构，方便 LLM 理解。

---

## 最佳实践

### 工具描述要清晰

LLM 根据 `description` 决定是否调用你的工具。写清楚：
- 工具做什么
- 什么时候应该用
- 参数含义

```python
# ❌ 模糊
"description": "处理数据"

# ✅ 清晰
"description": "查询指定城市的当前天气和未来3天预报"
```

### 参数类型要准确

```python
"properties": {
    "city": {"type": "string", "description": "城市名"},
    "days": {"type": "integer", "description": "预报天数（1-7）"},
    "detailed": {"type": "boolean", "description": "是否包含详细信息"},
}
```

### 错误处理要完善

```python
async def execute(self, tool_name, params):
    try:
        # 业务逻辑
        result = do_something(params)
        return {"success": True, "result": result}
    except ValueError as e:
        return {"success": False, "error": f"参数错误: {e}"}
    except Exception as e:
        return {"success": False, "error": f"执行失败: {e}"}
```

### 数据持久化

使用 `data/` 目录存储插件数据：

```python
import pathlib
_DATA_DIR = pathlib.Path(__file__).parent.parent.parent / "data"

# 存储
(_DATA_DIR / "my_data.json").write_text(json.dumps(data), encoding="utf-8")
```

### 安全注意事项

- **不要执行用户提供的任意代码**（除非是 code_runner 这样的沙盒插件）
- **不要硬编码 API Key**，使用环境变量 `os.getenv("MY_API_KEY")`
- **限制外部请求的超时时间**
- **对文件操作限制路径范围**

---

## 多工具插件

一个插件可以暴露多个工具：

```python
def list_tools(self):
    return [
        {"type": "function", "function": {"name": "tool_a", ...}},
        {"type": "function", "function": {"name": "tool_b", ...}},
    ]

async def execute(self, tool_name, params):
    if tool_name == "tool_a":
        return self._do_a(params)
    elif tool_name == "tool_b":
        return self._do_b(params)
    return {"success": False, "error": f"未知工具: {tool_name}"}
```

---

## 使用 WebSocket 推送

如果插件需要主动推送消息到前端（如提醒、监控告警）：

```python
_ws_channel = None

def set_ws_channel(channel):
    global _ws_channel
    _ws_channel = channel

class MyAdapter(ToolPort):
    async def _notify(self, message: str):
        if _ws_channel:
            import json
            await _ws_channel.broadcast(json.dumps({
                "type": "notification",
                "data": message,
            }))
```

在 `api/main.py` 中注入 WebSocket：

```python
try:
    from skills.my_plugin.main import set_ws_channel
    set_ws_channel(_ws_channel)
except ImportError:
    pass
```

---

## 目录结构参考

```
skills/
├── my_plugin/
│   ├── manifest.json      # 插件元数据
│   ├── main.py            # 入口（导出 XxxAdapter 类）
│   ├── utils.py           # 辅助模块（可选）
│   └── README.md          # 插件文档（可选）
├── weather/
│   ├── manifest.json
│   └── main.py
└── ...
```

---

## API 参考

### 插件管理

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/plugins` | 列出所有插件 |
| GET | `/api/plugins/{name}` | 插件详情 |
| PUT | `/api/plugins/{name}/toggle` | 启用/禁用 |
| POST | `/api/plugins/reload` | 热加载 |

### PluginHub

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/plugins/hub/search?q=xxx` | 搜索远程插件 |
| POST | `/api/plugins/hub/install` | 安装远程插件 |

### MCP

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/mcp/servers` | MCP Server 列表 |
| POST | `/api/mcp/servers` | 添加 MCP Server |
| DELETE | `/api/mcp/servers/{name}` | 移除 MCP Server |
| POST | `/api/mcp/discover` | 重新发现 MCP 工具 |
| GET | `/api/mcp/tools` | MCP 工具列表 |

---

## 内置插件列表

| 插件 | 工具 | 说明 |
|------|------|------|
| `clipboard` | clipboard_read, clipboard_write | 系统剪贴板 |
| `project_context` | scan_project | 项目结构扫描 |
| `reminder` | set_reminder, list_reminders | 定时提醒 |
| `notes` | create_note, search_notes, list_notes | Markdown 笔记 |
| `bookmarks` | add_bookmark, search_bookmarks, list_bookmarks | 网址收藏 |
| `knowledge_base` | kb_add, kb_search, kb_list | 个人知识库 |
| `daily_digest` | generate_digest | 每日摘要 |
| `github_ops` | gh_issues, gh_create_issue, gh_prs, gh_repo_info | GitHub |
| `docker_ops` | docker_ps, docker_logs, docker_restart | Docker |
| `git_helper` | git_status, git_diff, git_log, git_commit | Git |
| `code_runner` | run_python, run_script | 代码执行 |
| `weather` | get_weather | 天气查询 |
| `calculator` | calc, unit_convert | 计算/换算 |
| `web_monitor` | monitor_add, monitor_check, monitor_list | 网页监控 |
| `email_sender` | send_email | 邮件发送 |
