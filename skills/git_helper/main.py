"""Git 操作插件 — 状态、差异、日志、提交。"""

import subprocess
from typing import Any

from ports.tool_port import ToolPort


class GitHelperAdapter(ToolPort):

    def list_tools(self) -> list[dict[str, Any]]:
        return [
            {"type": "function", "function": {
                "name": "git_status",
                "description": "查看 Git 仓库状态（当前分支、修改文件等）",
                "parameters": {"type": "object", "properties": {
                    "path": {"type": "string", "description": "仓库路径（默认当前目录）"},
                }, "required": []},
            }},
            {"type": "function", "function": {
                "name": "git_diff",
                "description": "查看 Git 差异（未暂存的修改）",
                "parameters": {"type": "object", "properties": {
                    "path": {"type": "string", "description": "仓库路径（默认当前目录）"},
                    "staged": {"type": "boolean", "description": "是否查看已暂存的差异"},
                }, "required": []},
            }},
            {"type": "function", "function": {
                "name": "git_log",
                "description": "查看 Git 提交历史",
                "parameters": {"type": "object", "properties": {
                    "path": {"type": "string", "description": "仓库路径（默认当前目录）"},
                    "limit": {"type": "integer", "description": "显示最近 N 条（默认10）"},
                }, "required": []},
            }},
            {"type": "function", "function": {
                "name": "git_commit",
                "description": "Git 添加所有修改并提交（会自动 git add -A）",
                "parameters": {"type": "object", "properties": {
                    "path": {"type": "string", "description": "仓库路径（默认当前目录）"},
                    "message": {"type": "string", "description": "提交信息"},
                }, "required": ["message"]},
            }},
        ]

    async def execute(self, tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
        path = params.get("path", ".")
        if tool_name == "git_status":
            return self._run_git(path, ["status", "-sb"])
        elif tool_name == "git_diff":
            cmd = ["diff", "--staged"] if params.get("staged") else ["diff"]
            return self._run_git(path, cmd)
        elif tool_name == "git_log":
            limit = params.get("limit", 10)
            return self._run_git(path, ["log", f"-{limit}", "--oneline", "--graph"])
        elif tool_name == "git_commit":
            msg = params.get("message", "")
            if not msg:
                return {"success": False, "error": "请提供提交信息"}
            add_result = self._run_git(path, ["add", "-A"])
            if not add_result["success"]:
                return add_result
            return self._run_git(path, ["commit", "-m", msg])
        return {"success": False, "error": f"未知工具: {tool_name}"}

    def _run_git(self, cwd: str, args: list[str]) -> dict:
        try:
            r = subprocess.run(["git"] + args, cwd=cwd, capture_output=True, text=True, timeout=15)
            output = (r.stdout + r.stderr).strip()
            if r.returncode != 0 and "nothing to commit" not in output:
                return {"success": False, "error": output}
            return {"success": True, "result": output or "(无输出)"}
        except Exception as e:
            return {"success": False, "error": str(e)}
