"""Notification Tool Adapter — 系统通知。

发送 macOS/Linux 桌面通知。
"""

import asyncio
import platform
import subprocess
from typing import Any

from ports.tool_port import ToolPort
from logs import get_logger

logger = get_logger("tools")


class NotificationAdapter(ToolPort):
    """系统通知工具。发送桌面通知提醒用户。"""

    async def execute(self, tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
        if tool_name != "notify":
            return {"success": False, "result": None, "error": f"Unknown tool: {tool_name}"}
        title = params.get("title", "LucidMind")
        message = params.get("message", "")
        if not message:
            return {"success": False, "result": None, "error": "message is required"}
        try:
            if platform.system() == "Darwin":
                script = f'display notification "{message}" with title "{title}"'
                subprocess.run(["osascript", "-e", script], timeout=5, capture_output=True)
            else:
                subprocess.run(["notify-send", title, message], timeout=5, capture_output=True)
            return {"success": True, "result": f"通知已发送: {title} - {message[:50]}"}
        except Exception as e:
            return {"success": False, "result": None, "error": str(e)}

    def list_tools(self) -> list[dict[str, Any]]:
        return [{"type": "function", "function": {
            "name": "notify",
            "description": "发送桌面通知。提醒用户重要信息。",
            "parameters": {"type": "object", "properties": {
                "title": {"type": "string", "description": "通知标题，默认 LucidMind"},
                "message": {"type": "string", "description": "通知内容"}
            }, "required": ["message"]}
        }}]
