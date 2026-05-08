"""MCP (Model Context Protocol) 客户端工具适配器。

支持两种传输方式：
  1. stdio — 启动子进程，通过 stdin/stdout 通信（主流方式）
  2. http  — 通过 HTTP JSON-RPC 连接远程 MCP Server

配置文件：data/mcp_servers.json
也支持环境变量 MCP_SERVERS（JSON 数组）。

传输层实现见 mcp_transport.py。
"""

import json
import os
import pathlib
from typing import Any

from ports.tool_port import ToolPort
from adapters.tools.mcp_transport import (
    StdioTransport, HttpTransport,
)
from logs import get_logger

logger = get_logger("mcp")

_CONFIG_PATH = pathlib.Path(__file__).parent.parent.parent / "data" / "mcp_servers.json"


class MCPClientAdapter(ToolPort):
    """MCP 客户端 — 连接外部 MCP 服务器，代理其工具调用。

    支持 stdio（子进程）和 http（远程）两种传输。
    工具名格式：mcp_{server_name}_{tool_name}

    B5: 连接健康监控 + 自动重连
    B6: 工具名冲突检测与自动去重
    """

    def __init__(self):
        self._servers: list[dict] = []
        self._transports: dict[str, StdioTransport | HttpTransport] = {}
        self._tools: list[dict] = []
        self._tool_server: dict[str, dict] = {}
        self._server_configs: dict[str, dict] = {}  # name -> config (for reconnect)
        self._reconnect_count: dict[str, int] = {}   # name -> reconnect attempts
        self._max_reconnect = 3
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
        conflicts = 0
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
                transport = StdioTransport(command, args, env)
            elif transport_type == "http":
                url = srv.get("url", "")
                if not url:
                    logger.warning(f"MCP: {name} 缺少 url 配置")
                    continue
                transport = HttpTransport(url, headers=srv.get("headers"),
                                          oauth_token=srv.get("oauth_token") or srv.get("env", {}).get("OAUTH_TOKEN"))
            else:
                logger.warning(f"MCP: {name} 未知传输类型: {transport_type}")
                continue

            # 启动连接
            ok = await transport.start()
            if not ok:
                logger.warning(f"MCP: {name} 连接失败")
                continue
            self._transports[name] = transport
            self._server_configs[name] = srv
            self._reconnect_count[name] = 0

            # 发现工具
            try:
                resp = await transport.request("tools/list")
                if not resp:
                    continue
                tools = resp.get("result", {}).get("tools", [])
                for t in tools:
                    tool_name = f"mcp_{name}_{t['name']}"
                    # B6: 工具名冲突检测
                    if tool_name in self._tool_server:
                        existing = self._tool_server[tool_name]["server"]
                        logger.warning(f"MCP 工具名冲突: {tool_name} 已在 {existing}，{name} 的版本将被跳过")
                        conflicts += 1
                        continue
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
        if conflicts:
            logger.warning(f"MCP: {conflicts} 个工具名冲突被跳过")
        logger.info(f"MCP: 共发现 {count} 个外部工具 ({len(self._transports)} 个服务器已连接)")
        return count

    async def _reconnect_server(self, server_name: str) -> bool:
        """B5: 尝试重连单个 MCP Server。"""
        cfg = self._server_configs.get(server_name)
        if not cfg:
            return False
        attempts = self._reconnect_count.get(server_name, 0)
        if attempts >= self._max_reconnect:
            logger.warning(f"MCP: {server_name} 已达到最大重连次数 ({self._max_reconnect})，放弃")
            return False
        self._reconnect_count[server_name] = attempts + 1
        logger.info(f"MCP: 正在重连 {server_name} (第 {attempts + 1} 次)...")
        # 清理旧连接
        old = self._transports.pop(server_name, None)
        if old:
            try:
                await old.stop()
            except Exception:
                pass
        # 创建新传输层
        transport_type = cfg.get("transport", "http")
        if transport_type == "stdio":
            transport = StdioTransport(cfg.get("command", ""), cfg.get("args", []), cfg.get("env"))
        elif transport_type == "http":
            transport = HttpTransport(cfg.get("url", ""), headers=cfg.get("headers"),
                                      oauth_token=cfg.get("oauth_token") or cfg.get("env", {}).get("OAUTH_TOKEN"))
        else:
            return False
        ok = await transport.start()
        if not ok:
            logger.warning(f"MCP: {server_name} 重连失败")
            return False
        self._transports[server_name] = transport
        self._reconnect_count[server_name] = 0
        logger.info(f"MCP: {server_name} 重连成功")
        return True

    async def health_check(self) -> dict[str, Any]:
        """B5: 检查所有 MCP Server 连接健康状态。"""
        results = {}
        for srv in self._servers:
            name = srv.get("name", "unknown")
            if not srv.get("enabled", True):
                results[name] = {"status": "disabled"}
                continue
            transport = self._transports.get(name)
            if not transport:
                results[name] = {"status": "disconnected"}
                continue
            # 尝试 ping (发送 tools/list 作为心跳)
            try:
                resp = await transport.request("tools/list")
                if resp and "result" in resp:
                    tool_count = len(resp.get("result", {}).get("tools", []))
                    results[name] = {"status": "healthy", "tools": tool_count}
                    self._reconnect_count[name] = 0
                else:
                    results[name] = {"status": "unhealthy", "error": "no response"}
            except Exception as e:
                results[name] = {"status": "unhealthy", "error": str(e)}
        return results

    async def shutdown(self):
        """关闭所有 MCP 连接。"""
        for name, transport in self._transports.items():
            try:
                await transport.stop()
                logger.info(f"MCP: {name} 已断开")
            except Exception:
                pass
        self._transports.clear()
        self._server_configs.clear()
        self._reconnect_count.clear()

    def list_tools(self) -> list[dict[str, Any]]:
        return self._tools

    async def execute(self, tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
        info = self._tool_server.get(tool_name)
        if not info:
            return {"success": False, "result": None, "error": f"MCP工具未注册: {tool_name}"}
        server_name = info["server"]
        transport = self._transports.get(server_name)
        # B5+: 主动检测 stdio 进程是否还活着
        if transport and hasattr(transport, 'is_alive') and not transport.is_alive:
            logger.warning(f"MCP: {server_name} 进程已退出，主动重连")
            transport = None
            self._transports.pop(server_name, None)
        if not transport:
            self._reconnect_count[server_name] = 0  # 重置计数允许新一轮重连
            reconnected = await self._reconnect_server(server_name)
            if reconnected:
                transport = self._transports.get(server_name)
            if not transport:
                return {"success": False, "result": None, "error": f"MCP Server 未连接且重连失败: {server_name}"}
        try:
            resp = await transport.request("tools/call", {
                "name": info["original_name"], "arguments": params
            })
            if not resp:
                # B5: 无响应，尝试重连一次
                logger.warning(f"MCP: {tool_name} 无响应，尝试重连 {server_name}")
                reconnected = await self._reconnect_server(server_name)
                if reconnected:
                    transport = self._transports.get(server_name)
                    if transport:
                        resp = await transport.request("tools/call", {
                            "name": info["original_name"], "arguments": params
                        })
                if not resp:
                    return {"success": False, "result": None, "error": "MCP Server 无响应(重连后仍失败)"}
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


import re as _re
import shutil as _shutil

_SAFE_COMMANDS = {"npx", "node", "python3", "python", "uvx", "deno", "bun",
                  "docker", "podman", "ruby", "java", "go", "cargo"}
_SHELL_METACHARS = _re.compile(r"[;&|`$(){}!<>]")
_PROTECTED_ENV_KEYS = {"PATH", "HOME", "USER", "SHELL", "LD_PRELOAD", "DYLD_INSERT_LIBRARIES"}


def validate_server_config(config: dict) -> tuple[bool, str]:
    transport = config.get("transport", "")

    if transport == "stdio":
        command = config.get("command", "")
        if not command:
            return False, "缺少 command 字段"

        cmd_base = pathlib.Path(command).name
        if cmd_base not in _SAFE_COMMANDS:
            if not _shutil.which(command):
                return False, f"命令 '{command}' 不在白名单且未找到"

        args = config.get("args", [])
        for arg in args:
            if _SHELL_METACHARS.search(str(arg)):
                return False, f"参数包含 shell 元字符: {arg}"

        env = config.get("env", {})
        for key in env:
            if key in _PROTECTED_ENV_KEYS:
                return False, f"不允许覆盖受保护环境变量: {key} (PATH 等)"

        return True, ""

    elif transport == "http":
        url = config.get("url", "")
        if not url:
            return False, "缺少 url 字段"

        if not url.startswith(("http://", "https://")):
            return False, "不安全的协议: 仅允许 http/https"

        return True, ""

    else:
        return False, f"未知传输方式: {transport}"
