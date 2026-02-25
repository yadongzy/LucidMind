"""System Monitor Tool Adapter — 系统监控。

提供CPU、内存、磁盘、进程等系统信息。
"""

import asyncio
import functools
import os
import platform
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from ports.tool_port import ToolPort
from logs import get_logger

logger = get_logger("tools")
_pool = ThreadPoolExecutor(max_workers=2)


class SystemMonitorAdapter(ToolPort):
    """系统监控工具。查看CPU/内存/磁盘/进程信息。"""

    async def execute(self, tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
        if tool_name != "system_monitor":
            return {"success": False, "result": None, "error": f"Unknown tool: {tool_name}"}
        target = params.get("target", "overview")
        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(_pool, functools.partial(_gather, target))
            return {"success": True, "result": result}
        except Exception as e:
            return {"success": False, "result": None, "error": str(e)}

    def list_tools(self) -> list[dict[str, Any]]:
        return [{"type": "function", "function": {
            "name": "system_monitor",
            "description": "系统监控。查看CPU/内存/磁盘/进程等系统状态。",
            "parameters": {"type": "object", "properties": {
                "target": {"type": "string", "enum": ["overview", "cpu", "memory", "disk", "processes", "network"],
                           "description": "监控目标: overview=总览, cpu/memory/disk/processes/network=具体项"}
            }, "required": ["target"]}
        }}]


def _run(cmd: str) -> str:
    import subprocess
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
        return r.stdout.strip()[:1500]
    except Exception as e:
        return f"Error: {e}"


def _gather(target: str) -> str:
    is_mac = platform.system() == "Darwin"
    is_linux = platform.system() == "Linux"

    if target == "overview":
        parts = [f"Platform: {platform.system()} {platform.release()}",
                 f"Python: {platform.python_version()}",
                 f"CPU: {os.cpu_count()} cores"]
        if is_mac:
            parts.append("Memory: " + _run("vm_stat | head -5"))
            parts.append("Disk: " + _run("df -h / | tail -1"))
            parts.append("Load: " + _run("uptime"))
        elif is_linux:
            parts.append("Memory: " + _run("free -h | head -2"))
            parts.append("Disk: " + _run("df -h / | tail -1"))
            parts.append("Load: " + _run("uptime"))
        return "\n".join(parts)

    elif target == "cpu":
        if is_mac:
            return _run("top -l 1 -n 0 | head -10")
        return _run("top -bn1 | head -10")

    elif target == "memory":
        if is_mac:
            return _run("vm_stat") + "\n" + _run("sysctl hw.memsize")
        return _run("free -h")

    elif target == "disk":
        return _run("df -h")

    elif target == "processes":
        if is_mac:
            return _run("ps aux --sort=-%mem | head -15")
        return _run("ps aux --sort=-%mem | head -15")

    elif target == "network":
        if is_mac:
            return _run("netstat -an | grep LISTEN | head -15")
        return _run("ss -tlnp | head -15")

    return f"Unknown target: {target}"
