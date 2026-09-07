"""天气插件 — 使用 wttr.in 免费 API 查询天气。"""

import urllib.request
import urllib.parse
import json
from typing import Any

from ports.tool_port import ToolPort


class WeatherAdapter(ToolPort):

    def list_tools(self) -> list[dict[str, Any]]:
        return [
            {"type": "function", "function": {
                "name": "get_weather",
                "description": "查询指定城市的当前天气和未来3天预报",
                "parameters": {"type": "object", "properties": {
                    "city": {"type": "string", "description": "城市名（中文或英文，如 北京、London）"},
                }, "required": ["city"]},
            }},
        ]

    async def execute(self, tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
        if tool_name == "get_weather":
            return self._get_weather(params.get("city", ""))
        return {"success": False, "error": f"未知工具: {tool_name}"}

    def _get_weather(self, city: str) -> dict:
        if not city:
            return {"success": False, "error": "请提供城市名"}
        try:
            encoded_city = urllib.parse.quote(city)
            url = f"https://wttr.in/{encoded_city}?format=j1"
            req = urllib.request.Request(url, headers={"User-Agent": "LucidMind/1.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            current = data.get("current_condition", [{}])[0]
            result_lines = [
                f"📍 {city}",
                f"🌡️ 温度: {current.get('temp_C', '?')}°C（体感 {current.get('FeelsLikeC', '?')}°C）",
                f"☁️ 天气: {current.get('lang_zh', [{}])[0].get('value', current.get('weatherDesc', [{}])[0].get('value', '?'))}",
                f"💨 风速: {current.get('windspeedKmph', '?')} km/h {current.get('winddir16Point', '')}",
                f"💧 湿度: {current.get('humidity', '?')}%",
                f"👁️ 能见度: {current.get('visibility', '?')} km",
            ]

            forecast = data.get("weather", [])
            if forecast:
                result_lines.append("\n📅 未来预报:")
                for day in forecast[:3]:
                    date = day.get("date", "?")
                    max_t = day.get("maxtempC", "?")
                    min_t = day.get("mintempC", "?")
                    desc = ""
                    hourly = day.get("hourly", [])
                    if hourly:
                        mid = hourly[len(hourly) // 2]
                        desc_list = mid.get("lang_zh", [{}])
                        desc = desc_list[0].get("value", "") if desc_list else mid.get("weatherDesc", [{}])[0].get("value", "")
                    result_lines.append(f"  {date}: {min_t}~{max_t}°C {desc}")

            return {"success": True, "result": "\n".join(result_lines)}
        except Exception as e:
            return {"success": False, "error": f"天气查询失败: {e}"}
