"""网页监控插件 — 定期检查网页变化，变化时推送通知。"""

import hashlib
import json
import pathlib
import urllib.request
from datetime import datetime
from typing import Any

from ports.tool_port import ToolPort

_MONITOR_FILE = pathlib.Path(__file__).parent.parent.parent / "data" / "web_monitors.json"


class WebMonitorAdapter(ToolPort):

    def list_tools(self) -> list[dict[str, Any]]:
        return [
            {"type": "function", "function": {
                "name": "monitor_add",
                "description": "添加一个网页监控任务",
                "parameters": {"type": "object", "properties": {
                    "url": {"type": "string", "description": "要监控的网页 URL"},
                    "name": {"type": "string", "description": "监控名称（可选）"},
                }, "required": ["url"]},
            }},
            {"type": "function", "function": {
                "name": "monitor_check",
                "description": "检查所有监控的网页是否有变化",
                "parameters": {"type": "object", "properties": {}, "required": []},
            }},
            {"type": "function", "function": {
                "name": "monitor_list",
                "description": "列出所有监控任务",
                "parameters": {"type": "object", "properties": {}, "required": []},
            }},
        ]

    async def execute(self, tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
        if tool_name == "monitor_add":
            return self._add(params)
        elif tool_name == "monitor_check":
            return self._check()
        elif tool_name == "monitor_list":
            return self._list()
        return {"success": False, "error": f"未知工具: {tool_name}"}

    def _load(self) -> list[dict]:
        if _MONITOR_FILE.exists():
            try:
                return json.loads(_MONITOR_FILE.read_text("utf-8"))
            except Exception:
                return []
        return []

    def _save(self, data: list[dict]):
        _MONITOR_FILE.parent.mkdir(parents=True, exist_ok=True)
        _MONITOR_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def _fetch_hash(self, url: str) -> str | None:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "LucidMind/1.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                content = resp.read()
                return hashlib.sha256(content).hexdigest()
        except Exception:
            return None

    def _add(self, params: dict) -> dict:
        url = params.get("url", "")
        if not url:
            return {"success": False, "error": "URL 不能为空"}
        monitors = self._load()
        # 去重
        if any(m["url"] == url for m in monitors):
            return {"success": True, "result": f"已存在相同监控: {url}"}
        current_hash = self._fetch_hash(url)
        monitor = {
            "url": url,
            "name": params.get("name", url[:60]),
            "hash": current_hash,
            "added": datetime.now().isoformat(),
            "last_check": datetime.now().isoformat(),
            "changed": False,
        }
        monitors.append(monitor)
        self._save(monitors)
        return {"success": True, "result": f"监控已添加: {monitor['name']}"}

    def _check(self) -> dict:
        monitors = self._load()
        if not monitors:
            return {"success": True, "result": "没有监控任务"}
        changes = []
        for m in monitors:
            new_hash = self._fetch_hash(m["url"])
            m["last_check"] = datetime.now().isoformat()
            if new_hash and new_hash != m.get("hash"):
                m["hash"] = new_hash
                m["changed"] = True
                changes.append(m["name"])
            else:
                m["changed"] = False
        self._save(monitors)
        if changes:
            return {"success": True, "result": f"🔔 {len(changes)} 个网页有变化:\n" + "\n".join(f"  - {c}" for c in changes)}
        return {"success": True, "result": f"✅ 所有 {len(monitors)} 个监控网页无变化"}

    def _list(self) -> dict:
        monitors = self._load()
        if not monitors:
            return {"success": True, "result": "没有监控任务"}
        lines = [f"📡 共 {len(monitors)} 个监控:"]
        for m in monitors:
            status = "🔴 有变化" if m.get("changed") else "🟢 无变化"
            lines.append(f"  {status} {m['name']} — 上次检查: {m.get('last_check', '?')[:16]}")
        return {"success": True, "result": "\n".join(lines)}
