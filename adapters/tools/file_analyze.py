"""文件理解工具 — 读取上传文件内容，提取文本/描述。

支持：txt, md, py, json, csv, pdf(需pypdf), docx(需python-docx), 图片(描述)。
新 Adapter，不修改 brain.py（规则 06）。
"""

from pathlib import Path
from typing import Any

from ports.tool_port import ToolPort
from logs import get_logger

logger = get_logger("tools.analyze")

_UPLOAD_DIR = Path(__file__).parent.parent.parent / "data" / "uploads"
_TEXT_EXTS = {".txt", ".md", ".py", ".js", ".ts", ".json", ".csv", ".yaml", ".yml",
              ".toml", ".ini", ".cfg", ".html", ".css", ".xml", ".sql", ".sh", ".bat",
              ".log", ".rst", ".tex"}
_MAX_TEXT = 8000  # 最大提取字符数


class FileAnalyzeAdapter(ToolPort):
    """文件理解工具：读取上传文件内容。"""

    def list_tools(self) -> list[dict[str, Any]]:
        return [{
            "type": "function",
            "function": {
                "name": "analyze_file",
                "description": "读取并分析上传的文件内容。支持文本文件、CSV、JSON、PDF、DOCX。传入文件名或路径。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "filename": {
                            "type": "string",
                            "description": "文件名或完整路径（如 abc123.txt 或 data/uploads/abc123.txt）"
                        },
                    },
                    "required": ["filename"],
                },
            },
        }]

    async def execute(self, tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
        if tool_name != "analyze_file":
            return {"success": False, "error": f"未知工具: {tool_name}"}
        return self._analyze(params)

    def _resolve_path(self, filename: str) -> Path | None:
        """解析文件路径：支持文件名、相对路径、绝对路径。"""
        # 绝对路径
        p = Path(filename)
        if p.is_absolute() and p.exists():
            return p
        # uploads 目录下查找
        up = _UPLOAD_DIR / filename
        if up.exists():
            return up
        # 按文件名模糊匹配
        if _UPLOAD_DIR.exists():
            for f in _UPLOAD_DIR.iterdir():
                if filename in f.name:
                    return f
        return None

    def _analyze(self, params: dict) -> dict[str, Any]:
        filename = params.get("filename", "")
        if not filename:
            return {"success": False, "error": "未提供文件名"}

        path = self._resolve_path(filename)
        if not path or not path.exists():
            return {"success": False, "error": f"文件不存在: {filename}"}

        ext = path.suffix.lower()
        size = path.stat().st_size
        info = f"文件: {path.name}, 大小: {size} 字节, 类型: {ext}\n\n"

        try:
            # 文本文件
            if ext in _TEXT_EXTS:
                content = path.read_text(encoding="utf-8", errors="replace")[:_MAX_TEXT]
                logger.info(f"分析文本文件: {path.name}, {len(content)}字")
                return {"success": True, "result": info + content}

            # CSV
            if ext == ".csv":
                content = path.read_text(encoding="utf-8", errors="replace")
                lines = content.split("\n")
                preview = "\n".join(lines[:20])
                logger.info(f"分析CSV: {path.name}, {len(lines)}行")
                return {"success": True, "result": info + f"共 {len(lines)} 行\n前20行:\n{preview}"}

            # JSON
            if ext == ".json":
                import json
                data = json.loads(path.read_text(encoding="utf-8"))
                preview = json.dumps(data, ensure_ascii=False, indent=2)[:_MAX_TEXT]
                logger.info(f"分析JSON: {path.name}")
                return {"success": True, "result": info + preview}

            # Excel
            if ext in (".xlsx", ".xls"):
                try:
                    import openpyxl
                    wb = openpyxl.load_workbook(str(path), read_only=True)
                    sheets = wb.sheetnames
                    result = info + f"工作表: {sheets}\n"
                    for sn in sheets[:3]:
                        ws = wb[sn]
                        rows = list(ws.iter_rows(max_row=20, values_only=True))
                        result += f"\n--- {sn} ({ws.max_row}行 x {ws.max_column}列) ---\n"
                        for row in rows:
                            result += "\t".join(str(c) if c is not None else "" for c in row) + "\n"
                    wb.close()
                    logger.info(f"分析Excel: {path.name}, {len(sheets)}个工作表")
                    return {"success": True, "result": result[:_MAX_TEXT]}
                except ImportError:
                    return {"success": False, "error": "需要 openpyxl: pip install openpyxl"}

            # PDF
            if ext == ".pdf":
                try:
                    from pypdf import PdfReader
                    reader = PdfReader(str(path))
                    text = ""
                    for page in reader.pages[:10]:
                        text += page.extract_text() or ""
                    logger.info(f"分析PDF: {path.name}, {len(reader.pages)}页")
                    return {"success": True, "result": info + f"{len(reader.pages)}页\n\n" + text[:_MAX_TEXT]}
                except ImportError:
                    return {"success": False, "error": "需要 pypdf: pip install pypdf"}

            # DOCX
            if ext == ".docx":
                try:
                    from docx import Document
                    doc = Document(str(path))
                    text = "\n".join(p.text for p in doc.paragraphs)
                    logger.info(f"分析DOCX: {path.name}, {len(doc.paragraphs)}段")
                    return {"success": True, "result": info + text[:_MAX_TEXT]}
                except ImportError:
                    return {"success": False, "error": "需要 python-docx: pip install python-docx"}

            # PPTX
            if ext == ".pptx":
                try:
                    from pptx import Presentation
                    prs = Presentation(str(path))
                    text = ""
                    for i, slide in enumerate(prs.slides):
                        text += f"\n--- 幻灯片 {i+1} ---\n"
                        for shape in slide.shapes:
                            if hasattr(shape, "text"):
                                text += shape.text + "\n"
                    logger.info(f"分析PPTX: {path.name}, {len(prs.slides)}页")
                    return {"success": True, "result": info + text[:_MAX_TEXT]}
                except ImportError:
                    return {"success": False, "error": "需要 python-pptx: pip install python-pptx"}

            # 图片 — 返回基本信息
            if ext in (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"):
                try:
                    from PIL import Image
                    img = Image.open(str(path))
                    w, h = img.size
                    mode = img.mode
                    logger.info(f"分析图片: {path.name}, {w}x{h}")
                    return {"success": True, "result": info + f"尺寸: {w}x{h}, 模式: {mode}\n(图片内容需要多模态LLM分析)"}
                except ImportError:
                    return {"success": True, "result": info + "(图片文件，需要PIL或多模态LLM分析内容)"}

            # 其他：尝试当文本读
            try:
                content = path.read_text(encoding="utf-8", errors="replace")[:_MAX_TEXT]
                return {"success": True, "result": info + content}
            except Exception:
                return {"success": True, "result": info + "(二进制文件，无法提取文本内容)"}

        except Exception as e:
            logger.error(f"分析文件失败: {path.name}: {e}")
            return {"success": False, "error": f"分析失败: {e}"}
