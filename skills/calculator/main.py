"""计算器插件 — 数学运算和单位换算（安全执行，无需 LLM）。"""

import math
from typing import Any

from ports.tool_port import ToolPort

_UNIT_TABLE = {
    "km_mi": (0.621371, "km", "mi"),
    "mi_km": (1.60934, "mi", "km"),
    "kg_lb": (2.20462, "kg", "lb"),
    "lb_kg": (0.453592, "lb", "kg"),
    "m_ft": (3.28084, "m", "ft"),
    "ft_m": (0.3048, "ft", "m"),
    "c_f": (None, "°C", "°F"),  # special formula
    "f_c": (None, "°F", "°C"),
    "cm_in": (0.393701, "cm", "in"),
    "in_cm": (2.54, "in", "cm"),
    "l_gal": (0.264172, "L", "gal"),
    "gal_l": (3.78541, "gal", "L"),
}


class CalculatorAdapter(ToolPort):

    def list_tools(self) -> list[dict[str, Any]]:
        return [
            {"type": "function", "function": {
                "name": "calc",
                "description": "计算数学表达式（支持 +, -, *, /, **, sqrt, sin, cos, tan, log, pi, e）",
                "parameters": {"type": "object", "properties": {
                    "expression": {"type": "string", "description": "数学表达式，如 '2**10' 或 'sqrt(144)' 或 'sin(pi/4)'"},
                }, "required": ["expression"]},
            }},
            {"type": "function", "function": {
                "name": "unit_convert",
                "description": "单位换算（支持: km/mi, kg/lb, m/ft, °C/°F, cm/in, L/gal）",
                "parameters": {"type": "object", "properties": {
                    "value": {"type": "number", "description": "数值"},
                    "from_to": {"type": "string", "description": "换算方向，如 km_mi, c_f, kg_lb"},
                }, "required": ["value", "from_to"]},
            }},
        ]

    async def execute(self, tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
        if tool_name == "calc":
            return self._calc(params.get("expression") or params.get("expr", ""))
        elif tool_name == "unit_convert":
            return self._convert(params.get("value", 0), params.get("from_to", ""))
        return {"success": False, "error": f"未知工具: {tool_name}"}

    def _calc(self, expr: str) -> dict:
        if not expr:
            return {"success": False, "error": "请提供数学表达式"}
        safe_names = {
            "sqrt": math.sqrt, "sin": math.sin, "cos": math.cos, "tan": math.tan,
            "log": math.log, "log10": math.log10, "log2": math.log2,
            "abs": abs, "round": round, "pi": math.pi, "e": math.e,
            "ceil": math.ceil, "floor": math.floor, "pow": pow,
        }
        try:
            result = eval(expr, {"__builtins__": {}}, safe_names)
            return {"success": True, "result": f"{expr} = {result}"}
        except Exception as e:
            return {"success": False, "error": f"计算失败: {e}"}

    def _convert(self, value: float, from_to: str) -> dict:
        from_to = from_to.lower().replace(" ", "_")
        if from_to not in _UNIT_TABLE:
            supported = ", ".join(_UNIT_TABLE.keys())
            return {"success": False, "error": f"不支持的换算: {from_to}。支持: {supported}"}
        factor, from_unit, to_unit = _UNIT_TABLE[from_to]
        if from_to == "c_f":
            result = value * 9 / 5 + 32
        elif from_to == "f_c":
            result = (value - 32) * 5 / 9
        else:
            result = value * factor
        return {"success": True, "result": f"{value} {from_unit} = {result:.4f} {to_unit}"}
