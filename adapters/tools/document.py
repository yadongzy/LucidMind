"""Document Tool Adapter — PPT/Excel/CSV 生成与格式转换。

新 Adapter，不修改 brain.py（规则 06）。
"""

import asyncio
import functools
from pathlib import Path
from typing import Any

from ports.tool_port import ToolPort
from logs import get_logger

logger = get_logger("tools.document")

_OUTPUT_DIR = Path(__file__).parent.parent.parent / "data" / "output"
_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


class DocumentAdapter(ToolPort):
    """文档工具：生成 PPT、Excel、CSV，格式转换。"""

    def list_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "create_pptx",
                    "description": "创建 PowerPoint 演示文稿。slides 是幻灯片列表，每项含 title 和 content。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "filename": {"type": "string", "description": "输出文件名（不含路径）"},
                            "slides": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "title": {"type": "string"},
                                        "content": {"type": "string"},
                                    },
                                },
                                "description": "幻灯片列表",
                            },
                        },
                        "required": ["filename", "slides"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "create_excel",
                    "description": "创建 Excel 文件。headers 是表头列表，rows 是数据行列表。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "filename": {"type": "string"},
                            "headers": {"type": "array", "items": {"type": "string"}},
                            "rows": {"type": "array", "items": {"type": "array"}},
                            "sheet_name": {"type": "string", "description": "工作表名称"},
                        },
                        "required": ["filename", "headers", "rows"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "create_csv",
                    "description": "创建 CSV 文件。headers 是表头，rows 是数据行。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "filename": {"type": "string"},
                            "headers": {"type": "array", "items": {"type": "string"}},
                            "rows": {"type": "array", "items": {"type": "array"}},
                        },
                        "required": ["filename", "headers", "rows"],
                    },
                },
            },
        ]

    async def execute(self, tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
        handlers = {
            "create_pptx": self._create_pptx,
            "create_excel": self._create_excel,
            "create_csv": self._create_csv,
        }
        handler = handlers.get(tool_name)
        if not handler:
            return {"success": False, "error": f"Unknown tool: {tool_name}"}
        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, functools.partial(handler, params))
            return {"success": True, "result": result}
        except Exception as e:
            logger.error(f"文档工具失败: {tool_name} — {e}")
            return {"success": False, "error": str(e)}

    def _create_pptx(self, params: dict) -> str:
        from pptx import Presentation

        prs = Presentation()
        slides_data = params.get("slides", [])
        for s in slides_data:
            layout = prs.slide_layouts[1]  # Title + Content
            slide = prs.slides.add_slide(layout)
            slide.shapes.title.text = s.get("title", "")
            body = slide.placeholders[1]
            body.text = s.get("content", "")

        filename = params.get("filename", "output.pptx")
        if not filename.endswith(".pptx"):
            filename += ".pptx"
        path = _OUTPUT_DIR / filename
        prs.save(str(path))
        logger.info(f"PPT 已创建: {path} ({len(slides_data)} slides)")
        return f"已创建 {path} ({len(slides_data)} 页幻灯片)"

    def _create_excel(self, params: dict) -> str:
        from openpyxl import Workbook

        wb = Workbook()
        ws = wb.active
        ws.title = params.get("sheet_name", "Sheet1")
        headers = params.get("headers", [])
        rows = params.get("rows", [])

        if headers:
            ws.append(headers)
        for row in rows:
            ws.append(row)

        filename = params.get("filename", "output.xlsx")
        if not filename.endswith(".xlsx"):
            filename += ".xlsx"
        path = _OUTPUT_DIR / filename
        wb.save(str(path))
        logger.info(f"Excel 已创建: {path} ({len(rows)} rows)")
        return f"已创建 {path} ({len(rows)} 行数据)"

    def _create_csv(self, params: dict) -> str:
        import csv

        filename = params.get("filename", "output.csv")
        if not filename.endswith(".csv"):
            filename += ".csv"
        path = _OUTPUT_DIR / filename
        headers = params.get("headers", [])
        rows = params.get("rows", [])

        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            if headers:
                writer.writerow(headers)
            writer.writerows(rows)

        logger.info(f"CSV 已创建: {path} ({len(rows)} rows)")
        return f"已创建 {path} ({len(rows)} 行数据)"
