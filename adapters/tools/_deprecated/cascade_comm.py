"""Cascade Communication Tool — 通过 HTTP API 发消息给 Cascade 老师。

混合方案：
- 大脑 → Cascade：通过 HTTP POST /api/cascade/inject（服务器自动填入输入框）
- Cascade → 大脑：老师通过 /api/teacher/send 推送回复到大脑前端
- 不需要 GUI 操作，不需要点 Run 按钮，100% 可靠
"""

from typing import Any

from ports.tool_port import ToolPort
from logs import get_logger

logger = get_logger("tools.cascade_comm")

INJECT_URL = "http://localhost:8765/api/cascade/inject"


class CascadeCommAdapter(ToolPort):
    """Cascade 沟通工具 — 通过 HTTP API 发消息给老师。"""

    def list_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "cascade_communicate",
                    "description": (
                        "发消息给 Cascade 老师。通过 HTTP API 自动注入消息到 Cascade 输入框。\n"
                        "不需要 GUI 操作，不需要点 Run 按钮。\n"
                        "发送后等待老师回复（回复会自动推送到你的前端）。\n"
                        "如果长时间没收到回复，可以再次调用此工具重发。"
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "message": {
                                "type": "string",
                                "description": "要发送给 Cascade 老师的消息内容",
                            },
                        },
                        "required": ["message"],
                    },
                },
            },
        ]

    async def execute(self, tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
        if tool_name != "cascade_communicate":
            return {"success": False, "error": f"未知工具: {tool_name}"}

        message = params.get("message", "").strip()
        if not message:
            return {"success": False, "error": "消息不能为空"}

        try:
            import httpx
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(INJECT_URL, json={"message": message})
                result = resp.json()

            if result.get("status") == "ok" and result.get("injected"):
                logger.info(f"消息已注入 Cascade: {message[:80]}")
                return {
                    "success": True,
                    "result": (
                        f"✅ 消息已发送给 Cascade 老师: {message[:80]}\n"
                        "老师的回复会自动推送到你的前端聊天界面。\n"
                        "请等待几秒后检查是否收到回复。"
                    ),
                }
            else:
                detail = result.get("detail", "未知错误")
                logger.warning(f"注入失败: {detail}")
                return {"success": False, "error": detail,
                        "result": f"❌ 发送失败: {detail}"}

        except Exception as e:
            logger.error(f"Cascade 沟通失败: {e}")
            return {"success": False, "error": str(e),
                    "result": f"❌ 异常: {e}"}
