"""Docker 操作插件 — 容器列表、日志、重启。"""

import subprocess
from typing import Any

from ports.tool_port import ToolPort


class DockerOpsAdapter(ToolPort):

    def list_tools(self) -> list[dict[str, Any]]:
        return [
            {"type": "function", "function": {
                "name": "docker_ps",
                "description": "列出运行中的 Docker 容器",
                "parameters": {"type": "object", "properties": {
                    "all": {"type": "boolean", "description": "是否显示所有容器（包括已停止的）"},
                }, "required": []},
            }},
            {"type": "function", "function": {
                "name": "docker_logs",
                "description": "查看 Docker 容器日志",
                "parameters": {"type": "object", "properties": {
                    "container": {"type": "string", "description": "容器名或 ID"},
                    "tail": {"type": "integer", "description": "显示最后 N 行（默认50）"},
                }, "required": ["container"]},
            }},
            {"type": "function", "function": {
                "name": "docker_restart",
                "description": "重启 Docker 容器",
                "parameters": {"type": "object", "properties": {
                    "container": {"type": "string", "description": "容器名或 ID"},
                }, "required": ["container"]},
            }},
        ]

    async def execute(self, tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
        if tool_name == "docker_ps":
            return self._ps(params.get("all", False))
        elif tool_name == "docker_logs":
            return self._logs(params.get("container", ""), params.get("tail", 50))
        elif tool_name == "docker_restart":
            return self._restart(params.get("container", ""))
        return {"success": False, "error": f"未知工具: {tool_name}"}

    def _run(self, cmd: list[str]) -> tuple[str, int]:
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            return r.stdout + r.stderr, r.returncode
        except FileNotFoundError:
            return "docker 命令未找到，请确认已安装 Docker", 1
        except Exception as e:
            return str(e), 1

    def _ps(self, show_all: bool) -> dict:
        cmd = ["docker", "ps", "--format", "table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}"]
        if show_all:
            cmd.insert(2, "-a")
        out, code = self._run(cmd)
        if code != 0:
            return {"success": False, "error": out}
        return {"success": True, "result": out.strip() or "(无运行中的容器)"}

    def _logs(self, container: str, tail: int) -> dict:
        if not container:
            return {"success": False, "error": "请提供容器名或 ID"}
        out, code = self._run(["docker", "logs", "--tail", str(tail), container])
        if code != 0:
            return {"success": False, "error": out}
        return {"success": True, "result": out[-3000:] if len(out) > 3000 else out}

    def _restart(self, container: str) -> dict:
        if not container:
            return {"success": False, "error": "请提供容器名或 ID"}
        out, code = self._run(["docker", "restart", container])
        if code != 0:
            return {"success": False, "error": out}
        return {"success": True, "result": f"容器 {container} 已重启"}
