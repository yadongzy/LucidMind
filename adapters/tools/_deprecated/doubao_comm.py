"""Doubao Communication Tool — 与本地豆包应用沟通。

通过 GUI 自动化操作豆包桌面应用，实现大脑与豆包的对话。
"""

import asyncio
import subprocess
from typing import Any

from ports.tool_port import ToolPort
from logs import get_logger

logger = get_logger("tools")


class DoubaoCommAdapter(ToolPort):
    """豆包沟通工具。通过GUI自动化与本地豆包应用对话。"""

    async def execute(self, tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
        if tool_name != "doubao_communicate":
            return {"success": False, "result": None, "error": f"Unknown tool: {tool_name}"}
        message = params.get("message", "")
        if not message:
            return {"success": False, "result": None, "error": "message is required"}
        try:
            result = await _send_to_doubao(message)
            return {"success": True, "result": result}
        except Exception as e:
            logger.error(f"豆包沟通失败: {e}")
            return {"success": False, "result": None, "error": str(e)}

    def list_tools(self) -> list[dict[str, Any]]:
        return [{"type": "function", "function": {
            "name": "doubao_communicate",
            "description": "与本地豆包(Doubao)应用沟通。发送消息给豆包并等待回复。用于跨AI对话和协作。",
            "parameters": {"type": "object", "properties": {
                "message": {"type": "string", "description": "要发送给豆包的消息内容"}
            }, "required": ["message"]}
        }}]


async def _send_to_doubao(message: str) -> str:
    """通过剪贴板+GUI自动化发送消息给豆包并截图获取回复。"""
    loop = asyncio.get_event_loop()

    # 1. 激活豆包窗口
    await loop.run_in_executor(None, lambda: _run_apple(
        'tell application "Doubao" to activate'))
    await asyncio.sleep(1.0)

    # 2. 用剪贴板输入中文（keystroke不支持中文）
    await loop.run_in_executor(None, lambda: subprocess.run(
        ["pbcopy"], input=message, text=True, timeout=5))
    await asyncio.sleep(0.3)

    # 3. 粘贴到输入框
    await loop.run_in_executor(None, lambda: _run_apple(
        'tell application "System Events" to keystroke "v" using command down'))
    await asyncio.sleep(0.5)

    # 4. 按回车发送
    await loop.run_in_executor(None, lambda: _run_apple(
        'tell application "System Events" to key code 36'))

    # 5. 等待豆包回复
    await asyncio.sleep(10)

    # 6. 截图获取回复
    screenshot_path = "/tmp/doubao_reply.png"
    await loop.run_in_executor(None, lambda: subprocess.run(
        ["screencapture", "-x", screenshot_path], timeout=5))

    # 7. 用 vision 分析截图获取回复内容
    try:
        from adapters.tools.vision import _analyze_with_ollama
        reply = await loop.run_in_executor(None, lambda: _analyze_with_ollama(
            screenshot_path, "读取豆包的最新回复内容，只返回回复文字，不要描述界面"))
        return f"已发送消息给豆包。豆包回复: {reply}"
    except Exception as e:
        return f"已发送消息给豆包，但无法读取回复: {e}。请用 gui_screen 截图查看。"


def _run_apple(script: str) -> str:
    try:
        r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=10)
        return r.stdout.strip()
    except Exception as e:
        return f"Error: {e}"
