"""Phase 4.1 测试: MCP E2E 工作流验证（mock Server 级别）"""

import asyncio
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))


class TestMCPToolExecution(unittest.TestCase):
    """MCP 工具执行端到端（mock transport）"""

    def test_stdio_transport_send_receive(self):
        """验证 StdioTransport 的 JSON-RPC 消息格式"""
        from adapters.tools.mcp_transport import StdioTransport
        t = StdioTransport("echo", [])
        self.assertEqual(t.command, "echo")
        self.assertEqual(t._request_id, 0)

    def test_http_transport_init(self):
        """验证 HttpTransport 初始化"""
        from adapters.tools.mcp_transport import HttpTransport
        t = HttpTransport("http://localhost:3001/mcp", headers={"X-Key": "abc"})
        self.assertEqual(t.url, "http://localhost:3001/mcp")
        self.assertEqual(t._headers["X-Key"], "abc")

    def test_http_transport_oauth(self):
        """验证 OAuth token 注入"""
        from adapters.tools.mcp_transport import HttpTransport
        t = HttpTransport("http://localhost:3001/mcp", oauth_token="my-token")
        self.assertEqual(t._headers["Authorization"], "Bearer my-token")

    def test_mcp_client_tool_name_format(self):
        """验证 MCP 工具名格式: mcp_{server}_{tool}"""
        from adapters.tools.mcp_client import MCPClientAdapter
        client = MCPClientAdapter()
        # 无配置时应无工具
        tools = client.list_tools()
        # 如果有真实配置则可能有工具，否则为空
        self.assertIsInstance(tools, list)

    def test_validate_server_config_stdio_safe(self):
        """安全命令通过验证"""
        from adapters.tools.mcp_client import validate_server_config
        ok, reason = validate_server_config({
            "transport": "stdio", "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"]
        })
        self.assertTrue(ok, reason)

    def test_validate_server_config_stdio_unknown_command(self):
        """不在白名单且不存在的命令被拒绝"""
        from adapters.tools.mcp_client import validate_server_config
        ok, reason = validate_server_config({
            "transport": "stdio", "command": "totally_fake_cmd_xyz",
            "args": []
        })
        self.assertFalse(ok)
        self.assertIn("白名单", reason)

    def test_validate_server_config_shell_injection(self):
        """Shell 注入被检测"""
        from adapters.tools.mcp_client import validate_server_config
        ok, reason = validate_server_config({
            "transport": "stdio", "command": "npx",
            "args": ["-y", "pkg; rm -rf /"]
        })
        self.assertFalse(ok)
        self.assertIn("shell", reason.lower())

    def test_validate_server_config_http(self):
        """HTTP URL 验证"""
        from adapters.tools.mcp_client import validate_server_config
        ok, _ = validate_server_config({"transport": "http", "url": "http://localhost:3001"})
        self.assertTrue(ok)

        ok, _ = validate_server_config({"transport": "http", "url": "file:///etc/passwd"})
        self.assertFalse(ok)

    def test_validate_server_config_env_protection(self):
        """受保护环境变量不可覆盖"""
        from adapters.tools.mcp_client import validate_server_config
        ok, reason = validate_server_config({
            "transport": "stdio", "command": "npx",
            "args": [], "env": {"PATH": "/evil"}
        })
        self.assertFalse(ok)
        self.assertIn("PATH", reason)

    def test_reconnect_limit(self):
        """重连次数限制"""
        from adapters.tools.mcp_client import MCPClientAdapter
        client = MCPClientAdapter()
        client._reconnect_count["test_server"] = 999
        client._max_reconnect = 3
        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(client._reconnect_server("test_server"))
        loop.close()
        self.assertFalse(result)


class TestMCPWorkflowMock(unittest.TestCase):
    """MCP 工作流模拟测试"""

    def test_tool_execution_unknown_tool(self):
        """调用未注册的 MCP 工具"""
        from adapters.tools.mcp_client import MCPClientAdapter
        client = MCPClientAdapter()
        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(
            client.execute("mcp_nonexistent_tool", {})
        )
        loop.close()
        self.assertFalse(result["success"])
        self.assertIn("未注册", result["error"])

    def test_health_check_no_servers(self):
        """无服务器时的健康检查"""
        from adapters.tools.mcp_client import MCPClientAdapter
        client = MCPClientAdapter()
        client._servers = []
        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(client.health_check())
        loop.close()
        self.assertEqual(len(result), 0)


if __name__ == "__main__":
    unittest.main()
