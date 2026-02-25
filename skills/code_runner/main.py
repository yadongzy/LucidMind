"""代码执行插件 — 安全沙盒运行 Python/Shell 代码片段。"""

import subprocess
import tempfile
import os
from typing import Any

from ports.tool_port import ToolPort

_TIMEOUT = 30
_MAX_OUTPUT = 5000

# 安全: 只传递必要的环境变量给子进程
_SAFE_ENV_KEYS = {"PATH", "HOME", "LANG", "LC_ALL", "TMPDIR", "PYTHONPATH",
                  "PYTHONDONTWRITEBYTECODE", "VIRTUAL_ENV"}

def _safe_env() -> dict:
    return {k: v for k, v in os.environ.items() if k in _SAFE_ENV_KEYS}


class CodeRunnerAdapter(ToolPort):

    def list_tools(self) -> list[dict[str, Any]]:
        return [
            {"type": "function", "function": {
                "name": "run_python",
                "description": "执行 Python 代码片段并返回输出",
                "parameters": {"type": "object", "properties": {
                    "code": {"type": "string", "description": "Python 代码"},
                }, "required": ["code"]},
            }},
            {"type": "function", "function": {
                "name": "run_script",
                "description": "执行 Shell 脚本并返回输出（注意安全）",
                "parameters": {"type": "object", "properties": {
                    "script": {"type": "string", "description": "Shell 脚本内容"},
                }, "required": ["script"]},
            }},
        ]

    async def execute(self, tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
        if tool_name == "run_python":
            return self._run_python(params.get("code", ""))
        elif tool_name == "run_script":
            return self._run_script(params.get("script", ""))
        return {"success": False, "error": f"未知工具: {tool_name}"}

    def _run_python(self, code: str) -> dict:
        if not code.strip():
            return {"success": False, "error": "代码为空"}
        # 安全检查
        dangerous = ["os.system", "subprocess", "shutil.rmtree", "rm -rf", "__import__",
                      "exec(", "eval(", "open('/etc", "open('/sys",
                      "os.remove", "os.unlink", "os.rmdir", "os.rename",
                      "pathlib.Path.unlink", "send_signal", "os.kill",
                      "socket.socket", "http.server", "ftplib",
                      "ctypes", "importlib", "pkgutil"]
        for d in dangerous:
            if d in code:
                return {"success": False, "error": f"安全限制：代码包含危险操作 '{d}'"}
        try:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
                f.write(code)
                tmp_path = f.name
            r = subprocess.run(
                ["python3", "-u", tmp_path],
                capture_output=True, text=True, timeout=_TIMEOUT,
                env={**_safe_env(), "PYTHONDONTWRITEBYTECODE": "1"},
                cwd=tempfile.gettempdir(),
            )
            os.unlink(tmp_path)
            output = r.stdout
            if r.stderr:
                output += f"\n[STDERR]\n{r.stderr}"
            output = output[:_MAX_OUTPUT]
            return {"success": r.returncode == 0, "result": output or "(无输出)",
                    "error": r.stderr[:500] if r.returncode != 0 else None}
        except subprocess.TimeoutExpired:
            return {"success": False, "error": f"执行超时（{_TIMEOUT}秒）"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _run_script(self, script: str) -> dict:
        if not script.strip():
            return {"success": False, "error": "脚本为空"}
        dangerous = ["rm -rf /", "mkfs", "dd if=", "> /dev/sd", "chmod -R 777 /",
                      "curl | sh", "wget | sh", "curl | bash", "wget | bash",
                      ":(){ :|:& };:", "shutdown", "reboot", "init 0",
                      "passwd", "useradd", "userdel", "visudo"]
        for d in dangerous:
            if d in script:
                return {"success": False, "error": f"安全限制：脚本包含危险操作 '{d}'"}
        try:
            r = subprocess.run(
                ["bash", "-c", script],
                capture_output=True, text=True, timeout=_TIMEOUT,
                env=_safe_env(),
                cwd=tempfile.gettempdir(),
            )
            output = r.stdout
            if r.stderr:
                output += f"\n[STDERR]\n{r.stderr}"
            return {"success": r.returncode == 0, "result": output[:_MAX_OUTPUT] or "(无输出)"}
        except subprocess.TimeoutExpired:
            return {"success": False, "error": f"执行超时（{_TIMEOUT}秒）"}
        except Exception as e:
            return {"success": False, "error": str(e)}
