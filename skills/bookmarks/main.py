"""收藏夹插件 — 网址收藏、搜索、分类。"""

import json
import pathlib
from datetime import datetime
from typing import Any

from ports.tool_port import ToolPort

_BM_FILE = pathlib.Path(__file__).parent.parent.parent / "data" / "bookmarks.json"


class BookmarksAdapter(ToolPort):

    def list_tools(self) -> list[dict[str, Any]]:
        return [
            {"type": "function", "function": {
                "name": "add_bookmark",
                "description": "收藏一个网址",
                "parameters": {"type": "object", "properties": {
                    "url": {"type": "string", "description": "网址 URL"},
                    "title": {"type": "string", "description": "标题（可选，不填自动用URL）"},
                    "tags": {"type": "string", "description": "标签，逗号分隔（可选）"},
                    "note": {"type": "string", "description": "备注（可选）"},
                }, "required": ["url"]},
            }},
            {"type": "function", "function": {
                "name": "search_bookmarks",
                "description": "搜索收藏的网址",
                "parameters": {"type": "object", "properties": {
                    "query": {"type": "string", "description": "搜索关键词（匹配标题/URL/标签/备注）"},
                }, "required": ["query"]},
            }},
            {"type": "function", "function": {
                "name": "list_bookmarks",
                "description": "列出所有收藏（最近优先）",
                "parameters": {"type": "object", "properties": {
                    "tag": {"type": "string", "description": "按标签筛选（可选）"},
                    "limit": {"type": "integer", "description": "返回数量（默认20）"},
                }, "required": []},
            }},
        ]

    async def execute(self, tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
        if tool_name == "add_bookmark":
            return self._add(params)
        elif tool_name == "search_bookmarks":
            return self._search(params.get("query", ""))
        elif tool_name == "list_bookmarks":
            return self._list(params.get("tag"), params.get("limit", 20))
        return {"success": False, "error": f"未知工具: {tool_name}"}

    def _load(self) -> list[dict]:
        if _BM_FILE.exists():
            try:
                return json.loads(_BM_FILE.read_text("utf-8"))
            except Exception:
                return []
        return []

    def _save(self, data: list[dict]):
        _BM_FILE.parent.mkdir(parents=True, exist_ok=True)
        _BM_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def _add(self, params: dict) -> dict:
        url = params.get("url", "")
        if not url:
            return {"success": False, "error": "URL 不能为空"}
        bms = self._load()
        bm = {
            "url": url,
            "title": params.get("title", url),
            "tags": [t.strip() for t in params.get("tags", "").split(",") if t.strip()],
            "note": params.get("note", ""),
            "created": datetime.now().isoformat(),
        }
        bms.insert(0, bm)
        self._save(bms)
        return {"success": True, "result": f"已收藏: {bm['title']} ({url})"}

    def _search(self, query: str) -> dict:
        if not query:
            return {"success": False, "error": "请提供搜索关键词"}
        q = query.lower()
        results = []
        for bm in self._load():
            text = f"{bm.get('title','')} {bm.get('url','')} {' '.join(bm.get('tags',[]))} {bm.get('note','')}".lower()
            if q in text:
                results.append(bm)
            if len(results) >= 10:
                break
        return {"success": True, "result": f"找到 {len(results)} 条收藏", "bookmarks": results}

    def _list(self, tag: str | None, limit: int) -> dict:
        bms = self._load()
        if tag:
            bms = [b for b in bms if tag.lower() in [t.lower() for t in b.get("tags", [])]]
        return {"success": True, "result": f"共 {len(bms[:limit])} 条收藏", "bookmarks": bms[:limit]}
