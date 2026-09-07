"""MCP 传输层 — stdio 和 http 两种传输实现。

从 mcp_client.py 拆出以满足 ≤300 行规则。
"""

import asyncio
import json
import os
import re
import shutil
from urllib.parse import urlparse

from logs import get_logger

logger = get_logger("mcp.transport")

_MCP_TIMEOUT = 30

# Safety by Default: MCP Server 配置安全验证
_SAFE_COMMANDS = {"npx", "node", "bun", "python", "python3", "uvx", "uv", "deno"}
_SHELL_META_CHARS = re.compile(r'[|;&`$(){}\[\]<>]')
_PROTECTED_ENV_KEYS = {"PATH", "HOME", "USER", "SHELL", "LOGNAME", "LANG", "LC_ALL"}


def validate_server_config(config: dict) -> tuple[bool, str]:
    """验证 MCP Server 配置的安全性。

    Returns:
        (valid, reason) — valid=True 表示安全，reason 为拒绝原因。
    """
    transport = config.get("transport", "stdio")

    if transport == "stdio":
        command = config.get("command", "")
        if not command:
            return False, "stdio 传输需要 command 参数"
        cmd_base = os.path.basename(command)
        if cmd_base not in _SAFE_COMMANDS:
            if not os.path.isabs(command):
                resolved = shutil.which(command)
                if not resolved:
                    return False, f"command '{command}' 不在安全白名单且未找到可执行文件"
            elif not os.path.exists(command):
                return False, f"command 路径不存在: {command}"

        args = config.get("args", [])
        for i, arg in enumerate(args):
            if _SHELL_META_CHARS.search(str(arg)):
                return False, f"args[{i}] 包含 shell 元字符: {arg!r}"

        env = config.get("env") or {}
        for key in env:
            if key in _PROTECTED_ENV_KEYS:
                return False, f"env 不允许覆盖受保护的环境变量: {key}"

    elif transport == "http":
        url = config.get("url", "")
        if not url:
            return False, "http 传输需要 url 参数"
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False, f"url 协议不安全: {parsed.scheme}:// （仅允许 http/https）"
        if not parsed.hostname:
            return False, f"url 缺少主机名: {url}"

    return True, ""


class StdioTransport:
    """通过 stdin/stdout 与 MCP Server 子进程通信。"""

    def __init__(self, command: str, args: list[str], env: dict[str, str] | None = None):
        self.command = command
        self.args = args
        self.env = env
        self._process: asyncio.subprocess.Process | None = None
        self._request_id = 0
        self._lock = asyncio.Lock()

    async def start(self) -> bool:
        try:
            proc_env = {**os.environ, **(self.env or {})}
            self._process = await asyncio.create_subprocess_exec(
                self.command, *self.args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=proc_env,
            )
            init_resp = await self._send({
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "LucidMind", "version": "1.0.0"},
                },
            })
            if init_resp and "result" in init_resp:
                await self._notify({"method": "notifications/initialized"})
                return True
            return False
        except Exception as e:
            logger.warning(f"MCP stdio 启动失败: {self.command} {self.args}: {e}")
            return False

    async def stop(self):
        if self._process and self._process.returncode is None:
            try:
                self._process.terminate()
                await asyncio.wait_for(self._process.wait(), timeout=5)
            except Exception:
                self._process.kill()

    async def _send(self, message: dict) -> dict | None:
        if not self._process or not self._process.stdin or not self._process.stdout:
            return None
        async with self._lock:
            self._request_id += 1
            msg = {"jsonrpc": "2.0", "id": self._request_id, **message}
            line = json.dumps(msg) + "\n"
            try:
                self._process.stdin.write(line.encode())
                await self._process.stdin.drain()
                deadline = asyncio.get_event_loop().time() + _MCP_TIMEOUT
                while True:
                    remaining = deadline - asyncio.get_event_loop().time()
                    if remaining <= 0:
                        return None
                    resp_line = await asyncio.wait_for(
                        self._process.stdout.readline(), timeout=max(0.1, remaining)
                    )
                    if not resp_line:
                        return None
                    try:
                        resp = json.loads(resp_line.decode().strip())
                        if resp.get("id") == self._request_id:
                            return resp
                    except json.JSONDecodeError:
                        continue
            except Exception as e:
                logger.warning(f"MCP stdio 通信失败: {e}")
                return None
        return None

    async def _notify(self, message: dict):
        if not self._process or not self._process.stdin:
            return
        msg = {"jsonrpc": "2.0", **message}
        line = json.dumps(msg) + "\n"
        try:
            self._process.stdin.write(line.encode())
            await self._process.stdin.drain()
        except Exception:
            pass

    async def request(self, method: str, params: dict | None = None) -> dict | None:
        return await self._send({"method": method, "params": params or {}})


class HttpTransport:
    """通过 HTTP JSON-RPC 与远程 MCP Server 通信。支持 OAuth Bearer token。"""

    def __init__(self, url: str, headers: dict[str, str] | None = None,
                 oauth_token: str | None = None):
        self.url = url
        self._headers = headers or {}
        if oauth_token:
            self._headers["Authorization"] = f"Bearer {oauth_token}"
        self._client = None
        self._request_id = 0

    async def start(self) -> bool:
        try:
            import httpx
            self._client = httpx.AsyncClient(timeout=_MCP_TIMEOUT, headers=self._headers)
        except Exception as e:
            logger.warning(f"MCP HTTP 客户端初始化失败: {e}")
        return True

    async def stop(self):
        if self._client:
            try:
                await self._client.aclose()
            except Exception:
                pass
            self._client = None

    async def request(self, method: str, params: dict | None = None) -> dict | None:
        self._request_id += 1
        try:
            import httpx
            if not self._client:
                self._client = httpx.AsyncClient(timeout=_MCP_TIMEOUT, headers=self._headers)
            resp = await self._client.post(self.url, json={
                "jsonrpc": "2.0", "id": self._request_id,
                "method": method, "params": params or {}
            })
            if resp.status_code == 401:
                logger.warning(f"MCP HTTP 认证失败(401): {self.url}")
                return None
            return resp.json()
        except Exception as e:
            logger.warning(f"MCP HTTP 请求失败: {e}")
            return None
