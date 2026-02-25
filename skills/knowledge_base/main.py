"""知识库插件 — 文本导入、关键词搜索。"""

import json
import pathlib
from datetime import datetime
from typing import Any

from ports.tool_port import ToolPort

_KB_FILE = pathlib.Path(__file__).parent.parent.parent / "data" / "knowledge_base.json"


class KnowledgeBaseAdapter(ToolPort):

    def list_tools(self) -> list[dict[str, Any]]:
        return [
            {"type": "function", "function": {
                "name": "kb_add",
                "description": "向知识库添加一条知识（文本/要点/摘要）",
                "parameters": {"type": "object", "properties": {
                    "title": {"type": "string", "description": "知识标题"},
                    "content": {"type": "string", "description": "知识内容（文本）"},
                    "source": {"type": "string", "description": "来源（URL/书名/文件，可选）"},
                    "tags": {"type": "string", "description": "标签，逗号分隔（可选）"},
                }, "required": ["title", "content"]},
            }},
            {"type": "function", "function": {
                "name": "kb_search",
                "description": "搜索知识库（关键词匹配标题、内容、标签）",
                "parameters": {"type": "object", "properties": {
                    "query": {"type": "string", "description": "搜索关键词"},
                }, "required": ["query"]},
            }},
            {"type": "function", "function": {
                "name": "kb_list",
                "description": "列出知识库所有条目",
                "parameters": {"type": "object", "properties": {
                    "tag": {"type": "string", "description": "按标签筛选（可选）"},
                    "limit": {"type": "integer", "description": "返回数量（默认20）"},
                }, "required": []},
            }},
        ]

    async def execute(self, tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
        if tool_name == "kb_add":
            return self._add(params)
        elif tool_name == "kb_search":
            return self._search(params.get("query", ""))
        elif tool_name == "kb_list":
            return self._list(params.get("tag"), params.get("limit", 20))
        return {"success": False, "error": f"未知工具: {tool_name}"}

    def _load(self) -> list[dict]:
        if _KB_FILE.exists():
            try:
                return json.loads(_KB_FILE.read_text("utf-8"))
            except Exception:
                return []
        return []

    def _save(self, data: list[dict]):
        _KB_FILE.parent.mkdir(parents=True, exist_ok=True)
        _KB_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def _add(self, params: dict) -> dict:
        title = params.get("title", "")
        content = params.get("content", "")
        if not title or not content:
            return {"success": False, "error": "标题和内容不能为空"}
        items = self._load()
        item = {
            "title": title,
            "content": content,
            "source": params.get("source", ""),
            "tags": [t.strip() for t in params.get("tags", "").split(",") if t.strip()],
            "created": datetime.now().isoformat(),
        }
        items.insert(0, item)
        self._save(items)
        return {"success": True, "result": f"知识已添加: {title} (总计 {len(items)} 条)"}

    def _search(self, query: str) -> dict:
        if not query:
            return {"success": False, "error": "请提供搜索关键词"}
        q = query.lower()
        results = []
        for item in self._load():
            text = f"{item.get('title','')} {item.get('content','')} {' '.join(item.get('tags',[]))}".lower()
            if q in text:
                results.append({
                    "title": item["title"],
                    "preview": item["content"][:200],
                    "source": item.get("source", ""),
                    "tags": item.get("tags", []),
                })
            if len(results) >= 10:
                break
        return {"success": True, "result": f"找到 {len(results)} 条知识", "items": results}

    def _list(self, tag: str | None, limit: int) -> dict:
        items = self._load()
        if tag:
            items = [i for i in items if tag.lower() in [t.lower() for t in i.get("tags", [])]]
        display = [{"title": i["title"], "tags": i.get("tags", []), "created": i.get("created", "")[:10]}
                   for i in items[:limit]]
        return {"success": True, "result": f"知识库: {len(display)}/{len(items)} 条", "items": display}
