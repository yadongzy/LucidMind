"""笔记插件 — Markdown 笔记的创建、搜索、列表。"""

import pathlib
from datetime import datetime
from typing import Any

from ports.tool_port import ToolPort

_NOTES_DIR = pathlib.Path(__file__).parent.parent.parent / "data" / "notes"


class NotesAdapter(ToolPort):

    def list_tools(self) -> list[dict[str, Any]]:
        return [
            {"type": "function", "function": {
                "name": "create_note",
                "description": "创建一条 Markdown 笔记",
                "parameters": {"type": "object", "properties": {
                    "title": {"type": "string", "description": "笔记标题"},
                    "content": {"type": "string", "description": "笔记正文（Markdown）"},
                    "tags": {"type": "string", "description": "标签，逗号分隔（可选）"},
                }, "required": ["title", "content"]},
            }},
            {"type": "function", "function": {
                "name": "search_notes",
                "description": "搜索笔记（按关键词匹配标题和内容）",
                "parameters": {"type": "object", "properties": {
                    "query": {"type": "string", "description": "搜索关键词"},
                }, "required": ["query"]},
            }},
            {"type": "function", "function": {
                "name": "list_notes",
                "description": "列出所有笔记（最近优先）",
                "parameters": {"type": "object", "properties": {
                    "limit": {"type": "integer", "description": "返回数量（默认20）"},
                }, "required": []},
            }},
        ]

    async def execute(self, tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
        _NOTES_DIR.mkdir(parents=True, exist_ok=True)
        if tool_name == "create_note":
            return self._create(params)
        elif tool_name == "search_notes":
            return self._search(params.get("query", ""))
        elif tool_name == "list_notes":
            return self._list(params.get("limit", 20))
        return {"success": False, "error": f"未知工具: {tool_name}"}

    def _create(self, params: dict) -> dict:
        title = params.get("title", "无标题")
        content = params.get("content", "")
        tags = params.get("tags", "")
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_title = "".join(c if c.isalnum() or c in "-_ " else "" for c in title)[:50].strip()
        filename = f"{ts}_{safe_title}.md"
        header = f"# {title}\n\n> 创建时间: {datetime.now().isoformat()}\n"
        if tags:
            header += f"> 标签: {tags}\n"
        header += f"\n{content}\n"
        (_NOTES_DIR / filename).write_text(header, encoding="utf-8")
        return {"success": True, "result": f"笔记已创建: {filename}"}

    def _search(self, query: str) -> dict:
        if not query:
            return {"success": False, "error": "请提供搜索关键词"}
        results = []
        for f in sorted(_NOTES_DIR.glob("*.md"), reverse=True):
            text = f.read_text(encoding="utf-8")
            if query.lower() in text.lower():
                first_line = text.split("\n")[0].replace("# ", "")
                results.append({"file": f.name, "title": first_line, "preview": text[:200]})
            if len(results) >= 10:
                break
        return {"success": True, "result": f"找到 {len(results)} 条笔记", "notes": results}

    def _list(self, limit: int) -> dict:
        notes = []
        for f in sorted(_NOTES_DIR.glob("*.md"), reverse=True)[:limit]:
            text = f.read_text(encoding="utf-8")
            first_line = text.split("\n")[0].replace("# ", "")
            notes.append({"file": f.name, "title": first_line})
        return {"success": True, "result": f"共 {len(notes)} 条笔记", "notes": notes}
