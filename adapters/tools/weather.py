"""Weather Tool Adapter — 天气查询。

参考 OpenClaw weather skill，使用 wttr.in 免费API。
"""

import asyncio
import functools
from concurrent.futures import ThreadPoolExecutor
from typing import Any
import urllib.request

from ports.tool_port import ToolPort
from logs import get_logger

logger = get_logger("tools")
_pool = ThreadPoolExecutor(max_workers=2)


class WeatherAdapter(ToolPort):
    """天气查询工具。支持当前天气和预报。"""

    async def execute(self, tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
        if tool_name != "weather":
            return {"success": False, "result": None, "error": f"Unknown tool: {tool_name}"}
        location = params.get("location", "Beijing")
        mode = params.get("mode", "current")
        try:
            loop = asyncio.get_event_loop()
            if mode == "forecast":
                url = f"https://wttr.in/{location}?format=v2&lang=zh"
            else:
                url = f"https://wttr.in/{location}?format=%l:+%c+%t+(feels+like+%f),+%w+wind,+%h+humidity&lang=zh"
            result = await loop.run_in_executor(_pool, functools.partial(_fetch, url))
            return {"success": True, "result": result}
        except Exception as e:
            return {"success": False, "result": None, "error": str(e)}

    def list_tools(self) -> list[dict[str, Any]]:
        return [{"type": "function", "function": {
            "name": "weather",
            "description": "查询天气。获取指定城市的当前天气或预报。",
            "parameters": {"type": "object", "properties": {
                "location": {"type": "string", "description": "城市名称，如 Beijing, London, New+York"},
                "mode": {"type": "string", "enum": ["current", "forecast"], "description": "current=当前天气, forecast=3天预报"}
            }, "required": ["location"]}
        }}]


def _fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "curl/7.0"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return resp.read().decode("utf-8").strip()[:2000]
