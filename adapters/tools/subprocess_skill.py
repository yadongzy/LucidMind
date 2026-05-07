"""Subprocess Skill Adapter — 进程隔离执行 skill 工具。

渐进信任 Phase 2: 新安装/创建的 skill 在独立子进程中运行，
崩溃不影响主进程。通过 JSON 协议 stdin/stdout 通信。

信任升级路径:
  Level 2 (SANDBOXED) → subprocess 隔离执行（本文件）
  Level 1 (AUDITED)   → 进程内执行（用户手动升级）
  Level 0 (BUILTIN)   → 内置工具
"""

import asyncio
import json
import sys
import textwrap
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from ports.tool_port import ToolPort
from logs import get_logger

logger = get_logger("tools")

_pool = ThreadPoolExecutor(max_workers=4)

# 子进程中执行 skill 的 runner 脚本（作为 -c 参数传入 python）
_RUNNER_SCRIPT = textwrap.dedent(r'''
import importlib.util
import json
import sys
import os

def main():
    # 从 stdin 读取请求
    raw = sys.stdin.read()
    try:
        req = json.loads(raw)
    except Exception as e:
        print(json.dumps({"success": False, "error": f"JSON parse error: {e}"}))
        return

    action = req.get("action", "execute")
    skill_path = req.get("skill_path", "")
    module_name = req.get("module_name", "skill_module")

    # 加载 skill 模块
    try:
        spec = importlib.util.spec_from_file_location(module_name, skill_path)
        if not spec or not spec.loader:
            print(json.dumps({"success": False, "error": f"Cannot load: {skill_path}"}))
            return
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    except Exception as e:
        print(json.dumps({"success": False, "error": f"Module load error: {e}"}))
        return

    # 找到 Adapter 类
    adapter = None
    for attr_name in dir(mod):
        if attr_name.endswith("Adapter") and attr_name != "ToolPort":
            cls = getattr(mod, attr_name)
            if hasattr(cls, "list_tools") and hasattr(cls, "execute"):
                adapter = cls()
                break

    if not adapter:
        print(json.dumps({"success": False, "error": "No Adapter class found"}))
        return

    if action == "list_tools":
        tools = adapter.list_tools()
        print(json.dumps({"success": True, "tools": tools}))
        return

    if action == "execute":
        import asyncio
        tool_name = req.get("tool_name", "")
        params = req.get("params", {})
        try:
            result = asyncio.run(adapter.execute(tool_name, params))
            # 确保 result 可序列化
            print(json.dumps(result, default=str))
        except Exception as e:
            print(json.dumps({"success": False, "error": f"Execute error: {e}"}))
        return

    print(json.dumps({"success": False, "error": f"Unknown action: {action}"}))

if __name__ == "__main__":
    main()
''').strip()


class SubprocessSkillAdapter(ToolPort):
    """在独立子进程中执行 skill，提供进程级隔离。

    每次工具调用启动一个短生命周期子进程，执行完毕立即退出。
    优点: 崩溃隔离、内存隔离、无残留状态
    缺点: 冷启动开销 ~50-100ms（可接受）
    """

    def __init__(self, skill_dir: Path, manifest: dict):
        self._skill_dir = skill_dir
        self._manifest = manifest
        self._entry = skill_dir / manifest.get("entry", "main.py")
        self._module_name = f"skills.{skill_dir.name}.{self._entry.stem}"
        self._tool_defs: list[dict] | None = None  # 缓存工具定义
        self._python = sys.executable

    @property
    def skill_name(self) -> str:
        return self._manifest.get("name", self._skill_dir.name)

    async def execute(self, tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
        """在子进程中执行工具。"""
        request = {
            "action": "execute",
            "skill_path": str(self._entry),
            "module_name": self._module_name,
            "tool_name": tool_name,
            "params": params,
        }
        return await self._run_subprocess(request, timeout=30)

    def list_tools(self) -> list[dict[str, Any]]:
        """返回缓存的工具定义（首次调用时从子进程获取）。"""
        if self._tool_defs is not None:
            return self._tool_defs

        # 同步获取工具定义（只在初始化时调用一次）
        request = {
            "action": "list_tools",
            "skill_path": str(self._entry),
            "module_name": self._module_name,
        }
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # 在事件循环中，用线程池同步执行
                future = asyncio.run_coroutine_threadsafe(
                    self._run_subprocess(request, timeout=10), loop)
                result = future.result(timeout=10)
            else:
                result = asyncio.run(self._run_subprocess(request, timeout=10))

            if result.get("success") and "tools" in result:
                self._tool_defs = result["tools"]
            else:
                logger.warning(f"子进程获取工具定义失败 [{self.skill_name}]: {result}")
                self._tool_defs = self._fallback_tool_defs()
        except Exception as e:
            logger.warning(f"子进程获取工具定义异常 [{self.skill_name}]: {e}")
            self._tool_defs = self._fallback_tool_defs()

        return self._tool_defs

    def _fallback_tool_defs(self) -> list[dict[str, Any]]:
        """从 manifest 中构建基础工具定义（不启动子进程）。"""
        tools = []
        for tool_name in self._manifest.get("tools", []):
            tools.append({
                "type": "function",
                "function": {
                    "name": tool_name,
                    "description": f"[subprocess] {self.skill_name}: {tool_name}",
                    "parameters": {"type": "object", "properties": {}, "required": []},
                },
            })
        return tools

    async def _run_subprocess(self, request: dict, timeout: float = 30) -> dict:
        """启动子进程执行请求。"""
        request_json = json.dumps(request, ensure_ascii=False)
        try:
            proc = await asyncio.create_subprocess_exec(
                self._python, "-c", _RUNNER_SCRIPT,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self._skill_dir),
                env=self._safe_env(),
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(input=request_json.encode("utf-8")),
                timeout=timeout,
            )

            if proc.returncode != 0:
                err = stderr.decode("utf-8", errors="replace")[:500]
                logger.warning(f"子进程异常退出 [{self.skill_name}] code={proc.returncode}: {err}")
                return {"success": False, "error": f"子进程退出码 {proc.returncode}: {err}"}

            output = stdout.decode("utf-8").strip()
            if not output:
                return {"success": False, "error": "子进程无输出"}

            # 取最后一行（跳过可能的日志输出）
            last_line = output.split("\n")[-1]
            return json.loads(last_line)

        except asyncio.TimeoutError:
            logger.warning(f"子进程超时 [{self.skill_name}] ({timeout}s)")
            try:
                proc.kill()
            except Exception:
                pass
            return {"success": False, "error": f"子进程执行超时 ({timeout}s)"}
        except json.JSONDecodeError as e:
            return {"success": False, "error": f"子进程输出非法 JSON: {e}"}
        except Exception as e:
            return {"success": False, "error": f"子进程启动失败: {e}"}

    @staticmethod
    def _safe_env() -> dict[str, str]:
        """构建安全的环境变量（只传递必要项）。"""
        import os
        safe_keys = {"PATH", "HOME", "LANG", "LC_ALL", "PYTHONPATH",
                     "PYTHONIOENCODING", "VIRTUAL_ENV", "CONDA_PREFIX"}
        env = {k: v for k, v in os.environ.items() if k in safe_keys}
        env["PYTHONIOENCODING"] = "utf-8"
        # 添加项目根目录到 PYTHONPATH
        project_root = str(Path(__file__).resolve().parent.parent.parent)
        existing = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = f"{project_root}:{existing}" if existing else project_root
        return env
