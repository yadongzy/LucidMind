"""Clipboard Tool Adapter — 剪贴板操作。

读取/写入系统剪贴板。
"""

import asyncio
import functools
import platform
import subprocess
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from ports.tool_port import ToolPort
from logs import get_logger

logger = get_logger("tools")
_pool = ThreadPoolExecutor(max_workers=1)


class ClipboardAdapter(ToolPort):
    """剪贴板工具。读取或写入系统剪贴板内容。"""

    async def execute(self, tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
        if tool_name != "clipboard":
            return {"success": False, "result": None, "error": f"Unknown tool: {tool_name}"}
        action = params.get("action", "read")
        try:
            loop = asyncio.get_event_loop()
            if action == "read":
                result = await loop.run_in_executor(_pool, _read)
                return {"success": True, "result": result[:3000]}
            elif action == "write":
                text = params.get("text", "")
                await loop.run_in_executor(_pool, functools.partial(_write, text))
                return {"success": True, "result": f"已写入剪贴板 ({len(text)} 字符)"}
            return {"success": False, "result": None, "error": f"Unknown action: {action}"}
        except Exception as e:
            return {"success": False, "result": None, "error": str(e)}

    def list_tools(self) -> list[dict[str, Any]]:
        return [{"type": "function", "function": {
            "name": "clipboard",
            "description": "剪贴板操作。读取或写入系统剪贴板。",
            "parameters": {"type": "object", "properties": {
                "action": {"type": "string", "enum": ["read", "write"], "description": "read=读取剪贴板, write=写入剪贴板"},
                "text": {"type": "string", "description": "要写入剪贴板的文本（write时必填）"}
            }, "required": ["action"]}
        }}]


def _read() -> str:
    if platform.system() == "Darwin":
        return subprocess.run(["pbpaste"], capture_output=True, text=True, timeout=5).stdout
    return subprocess.run(["xclip", "-selection", "clipboard", "-o"], capture_output=True, text=True, timeout=5).stdout


def _write(text: str):
    if platform.system() == "Darwin":
        subprocess.run(["pbcopy"], input=text, text=True, timeout=5)
    else:
        subprocess.run(["xclip", "-selection", "clipboard"], input=text, text=True, timeout=5)
