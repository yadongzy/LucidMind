"""Image Tool Adapter — 图表/图片生成（matplotlib + PIL）。

新 Adapter，不修改 brain.py（规则 06）。
提供：生成图表（折线/柱状/饼图）、生成简单图片。
"""

import asyncio
import functools
from pathlib import Path
from typing import Any

from ports.tool_port import ToolPort
from logs import get_logger

logger = get_logger("tools.image")

_OUTPUT_DIR = Path(__file__).parent.parent.parent / "data" / "output"
_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


class ImageToolAdapter(ToolPort):
    """图片工具：生成图表和简单图片。"""

    def list_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "create_chart",
                    "description": "生成图表（折线图/柱状图/饼图）。chart_type: line/bar/pie。labels 是标签列表，values 是数值列表。title 是图表标题。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "chart_type": {"type": "string", "enum": ["line", "bar", "pie"], "description": "图表类型"},
                            "title": {"type": "string", "description": "图表标题"},
                            "labels": {"type": "array", "items": {"type": "string"}, "description": "标签列表"},
                            "values": {"type": "array", "items": {"type": "number"}, "description": "数值列表"},
                            "filename": {"type": "string", "description": "输出文件名"},
                        },
                        "required": ["chart_type", "title", "labels", "values"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "create_image",
                    "description": "用 Python 代码生成图片。code 是 matplotlib/PIL 绘图代码，必须将结果保存到变量 output_path。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "code": {"type": "string", "description": "Python 绘图代码（matplotlib/PIL）"},
                            "filename": {"type": "string", "description": "输出文件名"},
                        },
                        "required": ["code", "filename"],
                    },
                },
            },
        ]

    async def execute(self, tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
        handlers = {
            "create_chart": self._create_chart,
            "create_image": self._create_image,
        }
        handler = handlers.get(tool_name)
        if not handler:
            return {"success": False, "error": f"Unknown tool: {tool_name}"}
        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, functools.partial(handler, params))
            return {"success": True, "result": result}
        except Exception as e:
            logger.error(f"图片工具失败: {tool_name} — {e}")
            return {"success": False, "error": str(e)}

    def _create_chart(self, params: dict) -> str:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'DejaVu Sans']
        plt.rcParams['axes.unicode_minus'] = False

        chart_type = params.get("chart_type", "bar")
        title = params.get("title", "Chart")
        labels = params.get("labels", [])
        values = params.get("values", [])
        filename = params.get("filename", "chart.png")
        if not filename.endswith(".png"):
            filename += ".png"

        fig, ax = plt.subplots(figsize=(10, 6))

        if chart_type == "line":
            ax.plot(labels, values, marker='o', linewidth=2, markersize=8)
        elif chart_type == "pie":
            ax.pie(values, labels=labels, autopct='%1.1f%%', startangle=90)
            ax.axis('equal')
        else:  # bar
            colors = plt.cm.Set3([i / max(len(labels), 1) for i in range(len(labels))])
            ax.bar(labels, values, color=colors)

        ax.set_title(title, fontsize=16, fontweight='bold')
        if chart_type != "pie":
            ax.grid(True, alpha=0.3)
            plt.xticks(rotation=45, ha='right')

        plt.tight_layout()
        path = _OUTPUT_DIR / filename
        fig.savefig(str(path), dpi=150, bbox_inches='tight')
        plt.close(fig)

        logger.info(f"图表已创建: {path} (type={chart_type})")
        return f"已创建图表 {path} (类型: {chart_type}, {len(labels)} 个数据点)"

    def _create_image(self, params: dict) -> str:
        code = params.get("code", "")
        filename = params.get("filename", "output.png")
        if not filename.endswith(".png"):
            filename += ".png"
        output_path = str(_OUTPUT_DIR / filename)

        # 安全执行：限制可用模块
        safe_globals = {
            "__builtins__": {"range": range, "len": len, "int": int, "float": float,
                            "str": str, "list": list, "tuple": tuple, "dict": dict,
                            "min": min, "max": max, "sum": sum, "abs": abs,
                            "enumerate": enumerate, "zip": zip, "map": map,
                            "print": print, "round": round},
            "output_path": output_path,
        }
        # 延迟导入
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from PIL import Image, ImageDraw, ImageFont
        safe_globals["plt"] = plt
        safe_globals["Image"] = Image
        safe_globals["ImageDraw"] = ImageDraw
        safe_globals["ImageFont"] = ImageFont

        exec(code, safe_globals)
        plt.close('all')

        logger.info(f"图片已创建: {output_path}")
        return f"已创建图片 {output_path}"
