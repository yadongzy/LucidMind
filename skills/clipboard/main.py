"""剪贴板技能 — 读写系统剪贴板。

用途：大脑需要读取用户剪贴板内容或将结果写入剪贴板时调用。
仅支持 macOS (pbcopy/pbpaste)。
"""

import platform
import subprocess
from typing import Any

from ports.tool_port import ToolPort


class ClipboardAdapter(ToolPort):
    """系统剪贴板读写工具。"""

    def list_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "clipboard_read",
                    "description": "读取系统剪贴板的当前内容",
                    "parameters": {"type": "object", "properties": {}, "required": []},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "clipboard_write",
                    "description": "将文本写入系统剪贴板",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "text": {"type": "string", "description": "要写入剪贴板的文本"},
                        },
                        "required": ["text"],
                    },
                },
            },
        ]

    async def execute(self, tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
        if platform.system() != "Darwin":
            return {"success": False, "error": "剪贴板工具仅支持 macOS"}

        if tool_name == "clipboard_read":
            return self._read()
        elif tool_name == "clipboard_write":
            return self._write(params.get("text", ""))
        return {"success": False, "error": f"未知工具: {tool_name}"}

    def _read(self) -> dict[str, Any]:
        try:
            result = subprocess.run(["pbpaste"], capture_output=True, text=True, timeout=5)
            content = result.stdout
            if not content:
                return {"success": True, "result": "(剪贴板为空)"}
            return {"success": True, "result": content[:2000]}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _write(self, text: str) -> dict[str, Any]:
        if not text:
            return {"success": False, "error": "文本为空"}
        try:
            subprocess.run(["pbcopy"], input=text, text=True, timeout=5)
            return {"success": True, "result": f"已写入剪贴板 ({len(text)} 字符)"}
        except Exception as e:
            return {"success": False, "error": str(e)}
