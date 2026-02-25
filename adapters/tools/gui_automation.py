"""GUI Automation Adapter — 鼠标/键盘/截图控制。

新 Adapter，不修改 brain.py（规则 06）。
提供：鼠标移动/点击、键盘输入、屏幕截图、窗口信息。
大脑自己决定如何使用这些能力（规则 03）。
"""

import asyncio
import platform
from pathlib import Path
from typing import Any

from ports.tool_port import ToolPort
from logs import get_logger

logger = get_logger("tools.gui")

_SCREENSHOT_DIR = Path(__file__).parent.parent.parent / "data" / "screenshots"
_SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)


class GUIAutomationAdapter(ToolPort):
    """GUI 自动化工具：鼠标、键盘、截图、窗口。"""

    def list_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "gui_mouse",
                    "description": (
                        "控制鼠标。action: move(移动到x,y), click(点击x,y), "
                        "double_click(双击), right_click(右键), position(获取当前位置)"
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "action": {
                                "type": "string",
                                "enum": ["move", "click", "double_click",
                                         "right_click", "position"],
                            },
                            "x": {"type": "integer", "description": "X坐标"},
                            "y": {"type": "integer", "description": "Y坐标"},
                        },
                        "required": ["action"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "gui_keyboard",
                    "description": (
                        "控制键盘。action: type(打字), hotkey(组合键如cmd+v), "
                        "press(按单个键如enter/tab/escape)"
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "action": {
                                "type": "string",
                                "enum": ["type", "hotkey", "press"],
                            },
                            "text": {
                                "type": "string",
                                "description": "要输入的文字(type)或按键名(press/hotkey)",
                            },
                        },
                        "required": ["action", "text"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "gui_screen",
                    "description": (
                        "屏幕操作。action: screenshot(截图), size(获取分辨率), "
                        "find_text(在截图中查找文字位置)"
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "action": {
                                "type": "string",
                                "enum": ["screenshot", "size", "find_text"],
                            },
                            "text": {
                                "type": "string",
                                "description": "要查找的文字(find_text时使用)",
                            },
                        },
                        "required": ["action"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "gui_window",
                    "description": (
                        "窗口操作。action: list(列出可见窗口), "
                        "activate(激活指定应用窗口), frontmost(获取当前前台应用)"
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "action": {
                                "type": "string",
                                "enum": ["list", "activate", "frontmost"],
                            },
                            "app_name": {
                                "type": "string",
                                "description": "应用名称(activate时使用)",
                            },
                        },
                        "required": ["action"],
                    },
                },
            },
        ]

    async def execute(self, tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
        router = {
            "gui_mouse": self._mouse,
            "gui_keyboard": self._keyboard,
            "gui_screen": self._screen,
            "gui_window": self._window,
        }
        handler = router.get(tool_name)
        if not handler:
            return {"success": False, "error": f"未知工具: {tool_name}"}
        try:
            return await handler(params)
        except Exception as e:
            logger.error(f"GUI工具异常: {tool_name} {params} → {e}")
            return {"success": False, "error": str(e)}

    async def _mouse(self, p: dict) -> dict[str, Any]:
        import pyautogui
        action, x, y = p.get("action", ""), p.get("x"), p.get("y")
        if action == "position":
            pos = pyautogui.position()
            return {"success": True, "result": f"鼠标位置: ({pos.x}, {pos.y})"}
        if action in ("move", "click", "double_click", "right_click"):
            if x is None or y is None:
                return {"success": False, "error": "需要 x 和 y 坐标"}
            w, h = pyautogui.size()
            if not (0 <= x <= w and 0 <= y <= h):
                return {"success": False, "error": f"坐标({x},{y})超出屏幕({w}x{h})"}
        ops = {"move": pyautogui.moveTo, "click": pyautogui.click,
               "double_click": pyautogui.doubleClick, "right_click": pyautogui.rightClick}
        fn = ops.get(action)
        if fn:
            fn(x, y, duration=0.3) if action == "move" else fn(x, y)
            logger.info(f"鼠标{action}: ({x}, {y})")
            return {"success": True, "result": f"已{action} ({x}, {y})"}
        return {"success": False, "error": f"未知鼠标动作: {action}"}

    async def _keyboard(self, p: dict) -> dict[str, Any]:
        action = p.get("action", "")
        text = p.get("text", "")
        if not text:
            return {"success": False, "error": "需要 text 参数"}

        if action == "type":
            return await self._type_text(text)

        if action == "press":
            import pyautogui
            pyautogui.press(text)
            logger.info(f"按键: {text}")
            return {"success": True, "result": f"已按下 {text}"}

        if action == "hotkey":
            import pyautogui
            keys = [k.strip() for k in text.split("+")]
            keys = ["command" if k in ("cmd", "meta") else k for k in keys]
            pyautogui.hotkey(*keys)
            await asyncio.sleep(0.3)
            logger.info(f"组合键: {'+'.join(keys)}")
            return {"success": True, "result": f"已按下组合键 {'+'.join(keys)}"}

        return {"success": False, "error": f"未知键盘动作: {action}"}

    async def _type_text(self, text: str) -> dict[str, Any]:
        """打字 — 非ASCII用剪贴板，纯ASCII用 pyautogui。"""
        if not text.isascii() or platform.system() == "Darwin":
            return await self._type_via_clipboard(text)
        import pyautogui
        pyautogui.typewrite(text, interval=0.02)
        logger.info(f"打字: {text[:40]}")
        return {"success": True, "result": f"已输入: {text[:60]}"}

    async def _type_via_clipboard(self, text: str) -> dict[str, Any]:
        """通过剪贴板粘贴文字（支持中文，仅 macOS）。"""
        if platform.system() != "Darwin":
            return {"success": False, "error": "剪贴板输入仅支持 macOS"}
        import pyautogui
        proc = await asyncio.create_subprocess_exec(
            "pbcopy", stdin=asyncio.subprocess.PIPE)
        await proc.communicate(text.encode("utf-8"))
        await asyncio.sleep(0.1)
        pyautogui.hotkey("command", "v")
        await asyncio.sleep(0.2)
        logger.info(f"剪贴板粘贴: {text[:40]}")
        return {"success": True, "result": f"已通过剪贴板输入: {text[:60]}"}

    async def _screen(self, p: dict) -> dict[str, Any]:
        import pyautogui
        action = p.get("action", "")
        if action == "size":
            sz = pyautogui.size()
            return {"success": True, "result": f"屏幕分辨率: {sz.width}x{sz.height}"}
        if action == "screenshot":
            path = str(_SCREENSHOT_DIR / "gui_screenshot.png")
            pyautogui.screenshot().save(path)
            logger.info(f"截图: {path}")
            return {"success": True, "result": f"截图已保存: {path}", "path": path}
        if action == "find_text":
            text = p.get("text", "")
            if not text:
                return {"success": False, "error": "需要 text 参数"}
            path = str(_SCREENSHOT_DIR / "_find_text_tmp.png")
            pyautogui.screenshot().save(path)
            return {"success": True,
                    "result": f"截图已保存: {path}\n请用 vision 工具分析截图定位 '{text}'"}
        return {"success": False, "error": f"未知屏幕动作: {action}"}

    async def _osascript(self, script: str) -> tuple[int, str, str]:
        """异步执行 osascript（规则 13.3: 不在 async 中阻塞）。"""
        proc = await asyncio.create_subprocess_exec(
            "osascript", "-e", script,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=5)
        return proc.returncode, stdout.decode().strip(), stderr.decode().strip()

    async def _window(self, p: dict) -> dict[str, Any]:
        if platform.system() != "Darwin":
            return {"success": False, "error": "窗口操作仅支持 macOS"}
        action = p.get("action", "")

        if action == "frontmost":
            _, out, _ = await self._osascript(
                'tell application "System Events" to return '
                'name of first process whose frontmost is true')
            return {"success": True, "result": f"当前前台应用: {out}"}

        if action == "list":
            _, out, _ = await self._osascript(
                'tell application "System Events" to return '
                'name of every process whose visible is true')
            return {"success": True, "result": f"可见应用: {out}"}

        if action == "activate":
            app = p.get("app_name", "")
            if not app:
                return {"success": False, "error": "需要 app_name"}
            # 先尝试通过 System Events 按进程名激活（适用于 Electron 等进程名≠应用名的情况）
            rc, _, err = await self._osascript(
                f'tell application "System Events" to set frontmost of '
                f'process "{app}" to true')
            if rc == 0:
                await asyncio.sleep(0.5)
                logger.info(f"激活窗口(进程): {app}")
                return {"success": True, "result": f"已激活: {app}"}
            # 回退：尝试直接用应用名激活
            rc2, _, err2 = await self._osascript(f'tell application "{app}" to activate')
            if rc2 == 0:
                await asyncio.sleep(0.5)
                logger.info(f"激活窗口(应用): {app}")
                return {"success": True, "result": f"已激活: {app}"}
            return {"success": False, "error": f"进程方式: {err}; 应用方式: {err2}"}

        return {"success": False, "error": f"未知窗口动作: {action}"}
