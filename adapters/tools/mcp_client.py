"""MCP (Model Context Protocol) 客户端工具适配器。

支持两种传输方式：
  1. stdio — 启动子进程，通过 stdin/stdout 通信（主流方式，大多数 MCP Server 用此方式）
  2. http  — 通过 HTTP JSON-RPC 连接远程 MCP Server

配置文件：data/mcp_servers.json
  [
    {"name": "filesystem", "transport": "stdio", "command": "npx", "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"]},
    {"name": "weather", "transport": "http", "url": "http://localhost:3001/mcp"}
  ]

也支持环境变量 MCP_SERVERS（JSON 数组，同上格式）。
"""

import asyncio
import json
import os
import pathlib
import sys
from typing import Any

from ports.tool_port import ToolPort
from logs import get_logger

logger = get_logger("mcp")

_MCP_TIMEOUT = 30
_CONFIG_PATH = pathlib.Path(__file__).parent.parent.parent / "data" / "mcp_servers.json"


class _StdioTransport:
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
            # 发送 initialize 请求
            init_resp = await self._send({
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "LucidMind", "version": "1.0.0"},
                },
            })
            if init_resp and "result" in init_resp:
                # 发送 initialized 通知
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
        """发送 JSON-RPC 请求并等待响应。"""
        if not self._process or not self._process.stdin or not self._process.stdout:
            return None
        async with self._lock:
            self._request_id += 1
            msg = {"jsonrpc": "2.0", "id": self._request_id, **message}
            line = json.dumps(msg) + "\n"
            try:
                self._process.stdin.write(line.encode())
                await self._process.stdin.drain()
                # 读取响应（跳过通知，等待匹配 id 的响应）
                deadline = asyncio.get_event_loop().time() + _MCP_TIMEOUT
                while asyncio.get_event_loop().time() < deadline:
                    resp_line = await asyncio.wait_for(
                        self._process.stdout.readline(), timeout=_MCP_TIMEOUT
                    )
                    if not resp_line:
                        return None
                    try:
                        resp = json.loads(resp_line.decode().strip())
                        if resp.get("id") == self._request_id:
                            return resp
                        # 否则是通知，继续读
                    except json.JSONDecodeError:
                        continue
            except Exception as e:
                logger.warning(f"MCP stdio 通信失败: {e}")
                return None
        return None

    async def _notify(self, message: dict):
        """发送 JSON-RPC 通知（不需要响应）。"""
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


class _HttpTransport:
    """通过 HTTP JSON-RPC 与远程 MCP Server 通信。"""

    def __init__(self, url: str):
        self.url = url

    async def start(self) -> bool:
        return True

    async def stop(self):
        pass

    async def request(self, method: str, params: dict | None = None) -> dict | None:
        try:
            import httpx
            async with httpx.AsyncClient(timeout=_MCP_TIMEOUT) as client:
                resp = await client.post(self.url, json={
                    "jsonrpc": "2.0", "id": 1,
                    "method": method, "params": params or {}
                })
                return resp.json()
        except Exception as e:
            logger.warning(f"MCP HTTP 请求失败: {e}")
            return None


class MCPClientAdapter(ToolPort):
    """MCP 客户端 — 连接外部 MCP 服务器，代理其工具调用。

    支持 stdio（子进程）和 http（远程）两种传输。
    工具名格式：mcp_{server_name}_{tool_name}
    """

    def __init__(self):
        self._servers: list[dict] = []
        self._transports: dict[str, _StdioTransport | _HttpTransport] = {}
        self._tools: list[dict] = []
        self._tool_server: dict[str, dict] = {}
        self._load_config()

    def _load_config(self):
        """加载 MCP 服务器配置（配置文件优先，其次环境变量）。"""
        # 1. 配置文件
        if _CONFIG_PATH.exists():
            try:
                self._servers = json.loads(_CONFIG_PATH.read_text("utf-8"))
                logger.info(f"MCP: 从配置文件加载 {len(self._servers)} 个服务器")
                return
            except Exception as e:
                logger.warning(f"MCP: 配置文件解析失败: {e}")
        # 2. 环境变量
        raw = os.getenv("MCP_SERVERS", "")
        if raw:
            try:
                self._servers = json.loads(raw)
                logger.info(f"MCP: 从环境变量加载 {len(self._servers)} 个服务器")
            except (json.JSONDecodeError, TypeError) as e:
                logger.warning(f"MCP: 环境变量解析失败: {e}")
        if not self._servers:
            logger.info("MCP: 未配置任何 MCP Server")

    def save_config(self):
        """保存当前配置到文件。"""
        _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        _CONFIG_PATH.write_text(json.dumps(self._servers, ensure_ascii=False, indent=2), encoding="utf-8")

    def add_server(self, config: dict):
        """添加一个 MCP Server 配置。"""
        name = config.get("name", "")
        if not name:
            return
        # 去重
        self._servers = [s for s in self._servers if s.get("name") != name]
        self._servers.append(config)
        self.save_config()

    def remove_server(self, name: str) -> bool:
        """移除一个 MCP Server 配置。"""
        before = len(self._servers)
        self._servers = [s for s in self._servers if s.get("name") != name]
        if len(self._servers) < before:
            self.save_config()
            return True
        return False

    def get_servers(self) -> list[dict]:
        """返回所有服务器配置及状态。"""
        result = []
        for srv in self._servers:
            name = srv.get("name", "unknown")
            transport = srv.get("transport", "http")
            connected = name in self._transports
            tool_count = sum(1 for t in self._tool_server.values() if t.get("server") == name)
            result.append({
                **srv, "connected": connected, "tool_count": tool_count,
            })
        return result

    async def discover(self) -> int:
        """发现所有 MCP 服务器的工具（启动时调用一次）。"""
        self._tools.clear()
        self._tool_server.clear()
        count = 0
        for srv in self._servers:
            name = srv.get("name", "unknown")
            transport_type = srv.get("transport", "http")
            enabled = srv.get("enabled", True)
            if not enabled:
                logger.info(f"MCP: {name} 已禁用，跳过")
                continue
            # 创建传输层
            if transport_type == "stdio":
                command = srv.get("command", "")
                args = srv.get("args", [])
                env = srv.get("env")
                if not command:
                    logger.warning(f"MCP: {name} 缺少 command 配置")
                    continue
                transport = _StdioTransport(command, args, env)
            elif transport_type == "http":
                url = srv.get("url", "")
                if not url:
                    logger.warning(f"MCP: {name} 缺少 url 配置")
                    continue
                transport = _HttpTransport(url)
            else:
                logger.warning(f"MCP: {name} 未知传输类型: {transport_type}")
                continue

            # 启动连接
            ok = await transport.start()
            if not ok:
                logger.warning(f"MCP: {name} 连接失败")
                continue
            self._transports[name] = transport

            # 发现工具
            try:
                resp = await transport.request("tools/list")
                if not resp:
                    continue
                tools = resp.get("result", {}).get("tools", [])
                for t in tools:
                    tool_name = f"mcp_{name}_{t['name']}"
                    tool_def = {
                        "type": "function",
                        "function": {
                            "name": tool_name,
                            "description": f"[MCP:{name}] {t.get('description', '')}",
                            "parameters": t.get("inputSchema", {"type": "object", "properties": {}})
                        }
                    }
                    self._tools.append(tool_def)
                    self._tool_server[tool_name] = {
                        "original_name": t["name"], "server": name
                    }
                    count += 1
                logger.info(f"MCP: {name} ({transport_type}) → {len(tools)} 个工具")
            except Exception as e:
                logger.warning(f"MCP: {name} 工具发现失败: {e}")
        logger.info(f"MCP: 共发现 {count} 个外部工具 ({len(self._transports)} 个服务器已连接)")
        return count

    async def shutdown(self):
        """关闭所有 MCP 连接。"""
        for name, transport in self._transports.items():
            try:
                await transport.stop()
                logger.info(f"MCP: {name} 已断开")
            except Exception:
                pass
        self._transports.clear()

    def list_tools(self) -> list[dict[str, Any]]:
        return self._tools

    async def execute(self, tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
        info = self._tool_server.get(tool_name)
        if not info:
            return {"success": False, "result": None, "error": f"MCP工具未注册: {tool_name}"}
        server_name = info["server"]
        transport = self._transports.get(server_name)
        if not transport:
            return {"success": False, "result": None, "error": f"MCP Server 未连接: {server_name}"}
        try:
            resp = await transport.request("tools/call", {
                "name": info["original_name"], "arguments": params
            })
            if not resp:
                return {"success": False, "result": None, "error": "MCP Server 无响应"}
            if "error" in resp:
                err = resp["error"]
                logger.warning(f"MCP: {tool_name} 错误: {err}")
                return {"success": False, "result": None, "error": str(err)}
            result = resp.get("result", {})
            content = result.get("content", [])
            text = "\n".join(c.get("text", str(c)) for c in content) if content else str(result)
            logger.info(f"MCP: {tool_name} 执行成功 ({len(text)} chars)")
            return {"success": True, "result": text, "error": None}
        except Exception as e:
            logger.error(f"MCP: {tool_name} 执行异常: {e}")
            return {"success": False, "result": None, "error": str(e)}
