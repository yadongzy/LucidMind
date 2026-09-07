"""每日摘要插件 — 汇总今日笔记、提醒、任务状态。"""

import json
import pathlib
from datetime import datetime, date
from typing import Any

from ports.tool_port import ToolPort

_DATA_DIR = pathlib.Path(__file__).parent.parent.parent / "data"


class DailyDigestAdapter(ToolPort):

    def list_tools(self) -> list[dict[str, Any]]:
        return [
            {"type": "function", "function": {
                "name": "generate_digest",
                "description": "生成今日摘要：汇总笔记、提醒、任务队列状态",
                "parameters": {"type": "object", "properties": {}, "required": []},
            }},
        ]

    async def execute(self, tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
        if tool_name == "generate_digest":
            return self._digest()
        return {"success": False, "error": f"未知工具: {tool_name}"}

    def _digest(self) -> dict:
        today = date.today().isoformat()
        today_prefix = datetime.now().strftime("%Y%m%d")
        sections = []

        # 1. 今日笔记
        notes_dir = _DATA_DIR / "notes"
        if notes_dir.exists():
            today_notes = [f.name for f in notes_dir.glob(f"{today_prefix}*.md")]
            if today_notes:
                sections.append(f"📝 今日笔记 ({len(today_notes)} 条):\n" + "\n".join(f"  - {n}" for n in today_notes))
            else:
                sections.append("📝 今日笔记: 无")

        # 2. 收藏夹
        bm_file = _DATA_DIR / "bookmarks.json"
        if bm_file.exists():
            try:
                bms = json.loads(bm_file.read_text("utf-8"))
                today_bms = [b for b in bms if b.get("created", "").startswith(today)]
                if today_bms:
                    sections.append(f"🔖 今日收藏 ({len(today_bms)} 条):\n" + "\n".join(f"  - {b.get('title', b.get('url', '?'))}" for b in today_bms))
            except Exception:
                pass

        # 3. 任务队列
        queue_file = _DATA_DIR / "task_queue.json"
        if queue_file.exists():
            try:
                queue = json.loads(queue_file.read_text("utf-8"))
                tasks = queue.get("tasks", [])
                pending = [t for t in tasks if t.get("status") == "pending"]
                done = [t for t in tasks if t.get("status") == "done"]
                sections.append(f"📋 任务队列: {len(pending)} 待处理, {len(done)} 已完成")
            except Exception:
                pass

        # 4. 经验库
        lessons_file = _DATA_DIR / "lessons.json"
        if lessons_file.exists():
            try:
                lessons = json.loads(lessons_file.read_text("utf-8"))
                sections.append(f"📚 经验库: {len(lessons)} 条经验")
            except Exception:
                pass

        if not sections:
            sections.append("今天还没有任何活动记录。")

        header = f"# 📊 每日摘要 — {today}\n\n"
        return {"success": True, "result": header + "\n\n".join(sections)}
