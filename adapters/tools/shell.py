"""Shell Tool Adapter — 执行系统命令。

对标 OpenAkita shell.py (343行)。
我们的优势: 安全控制 + 命令日志 + 更简洁。
"""

import asyncio
import functools
import platform
import subprocess
from typing import Any

from ports.tool_port import ToolPort
from logs import get_logger

logger = get_logger("tools")

# S19-1: 安全运行时强制
_BLOCKED_PATTERNS = [
    # 文件系统破坏
    "rm -rf /", "rm -rf ~", "rm -rf .", "rm -rf *",
    "del /s /q c:", "format c:", "format d:",
    "mkfs", ":(){:|:&};:",  # fork bomb
    # 权限提升
    "sudo ", "su -", "doas ",
    # 系统控制
    "shutdown", "reboot", "halt", "poweroff",
    "reg delete", "bcdedit", "diskpart",
    # 危险操作
    "chmod 777", "chmod -r 777",
    "dd if=", "dd of=/dev/",
    # 远程代码执行
    "| bash", "| sh", "| zsh",
    "curl | ", "wget | ",
    # 网络攻击工具
    "nmap ", "nikto", "sqlmap",
    # 密钥/凭证操作
    "ssh-keygen -f /", "gpg --delete",
]
_SENSITIVE_PATHS = [
    ".env", ".git/", ".git\\", "/etc/passwd", "/etc/shadow",
    "c:\\windows\\system32", "c:\\windows\\syswow64",
    "id_rsa", "id_ed25519", ".ssh/",
    ".aws/credentials", ".kube/config",
]


class ShellAdapter(ToolPort):
    """Shell 工具适配器。执行系统命令并返回结果。"""

    def __init__(self, timeout: int = 30):
        self.timeout = timeout
        self._is_windows = platform.system() == "Windows"
        logger.info(f"初始化: 平台={platform.system()}, 超时={timeout}s")

    def list_tools(self) -> list[dict[str, Any]]:
        """返回 LLM 可用的工具定义。"""
        return [
            {
                "type": "function",
                "function": {
                    "name": "run_command",
                    "description": "在系统终端执行命令并返回输出。用于获取系统信息、运行脚本等。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "command": {
                                "type": "string",
                                "description": "要执行的命令",
                            },
                        },
                        "required": ["command"],
                    },
                },
            }
        ]

    async def execute(self, tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
        """执行工具。"""
        if tool_name == "run_command":
            return await self._run_command(params.get("command", ""))
        return {"success": False, "result": None, "error": f"未知工具: {tool_name}"}

    async def _run_command(self, command: str) -> dict[str, Any]:
        """执行系统命令。使用 subprocess.run + 线程池，兼容 Windows uvicorn。"""
        if not command.strip():
            return {"success": False, "result": None, "error": "命令为空"}

        # S19-1: 安全检查 — 危险命令 + 敏感路径
        cmd_lower = command.lower()
        for blocked in _BLOCKED_PATTERNS:
            if blocked in cmd_lower:
                logger.warning(f"命令被拦截(危险): {command}")
                return {"success": False, "result": None, "error": f"命令被安全策略拦截: 包含危险操作 '{blocked}'"}
        for path in _SENSITIVE_PATHS:
            if path in cmd_lower:
                logger.warning(f"命令被拦截(敏感路径): {command}")
                return {"success": False, "result": None, "error": f"命令被安全策略拦截: 涉及敏感路径 '{path}'"}

        logger.info(f"执行命令: {command[:200]}")

        try:
            loop = asyncio.get_event_loop()
            result = await asyncio.wait_for(
                loop.run_in_executor(None, functools.partial(self._sync_run, command)),
                timeout=self.timeout,
            )
            return result

        except asyncio.TimeoutError:
            logger.error(f"命令超时: {self.timeout}s")
            return {
                "success": False,
                "result": None,
                "error": f"命令执行超时 ({self.timeout}秒)",
            }
        except Exception as e:
            logger.error(f"命令执行失败: {type(e).__name__}: {e}", exc_info=True)
            return {
                "success": False,
                "result": None,
                "error": f"{type(e).__name__}: {e}" if str(e) else f"{type(e).__name__}",
            }

    def _sync_run(self, command: str) -> dict[str, Any]:
        """同步执行命令（在线程池中调用）。"""
        proc = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            timeout=self.timeout,
        )

        # Windows CMD 默认 GBK 编码
        if self._is_windows:
            try:
                stdout_text = proc.stdout.decode("gbk").strip()
            except UnicodeDecodeError:
                stdout_text = proc.stdout.decode("utf-8", errors="replace").strip()
            try:
                stderr_text = proc.stderr.decode("gbk").strip()
            except UnicodeDecodeError:
                stderr_text = proc.stderr.decode("utf-8", errors="replace").strip()
        else:
            stdout_text = proc.stdout.decode("utf-8", errors="replace").strip()
            stderr_text = proc.stderr.decode("utf-8", errors="replace").strip()

        returncode = proc.returncode

        # 截断过长输出
        max_len = 4000
        if len(stdout_text) > max_len:
            stdout_text = stdout_text[:max_len] + "\n... (截断)"

        output = stdout_text
        if stderr_text and returncode != 0:
            output += f"\n[stderr] {stderr_text}"

        logger.info(f"命令完成: code={returncode}, 输出={len(stdout_text)}字")

        return {
            "success": returncode == 0,
            "result": output or "(无输出)",
            "error": stderr_text if returncode != 0 else None,
        }
