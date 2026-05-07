"""Phase 3 测试 — MCP Server Wrapper 自动封装。

运行方法:
    cd /Users/yadong/Documents/LucidMind
    python -m pytest tests/test_mcp_wrapper.py -v -s
"""

import json
import pathlib
import shutil
import sys

import pytest

ROOT = pathlib.Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))


class TestMCPWrapper:
    """测试 MCP Server wrapper 生成和注册。"""

    def test_generate_mcp_server_for_existing_skill(self):
        """为已有 skill 生成 MCP Server 脚本。"""
        from skills.mcp_wrapper import generate_mcp_server
        result = generate_mcp_server("weather")
        assert result.get("success"), f"生成失败: {result}"
        server_path = pathlib.Path(result["path"])
        assert server_path.exists()
        content = server_path.read_text("utf-8")
        assert "MCPServer" in content
        assert "weather" in content
        assert "mcp_server.py" in result["path"]
        print(f"  ✅ weather MCP Server 已生成: {result['path']}")
        # 清理
        server_path.unlink(missing_ok=True)

    def test_generate_mcp_server_nonexistent(self):
        """为不存在的 skill 生成 → 失败。"""
        from skills.mcp_wrapper import generate_mcp_server
        result = generate_mcp_server("nonexistent_skill_xyz")
        assert not result.get("success")
        assert "不存在" in result.get("error", "")
        print("  ✅ 不存在的 skill 正确返回失败")

    def test_register_mcp_server(self):
        """注册 MCP Server 到 data/mcp_servers.json。"""
        from skills.mcp_wrapper import register_mcp_server, unregister_mcp_server
        result = register_mcp_server("calculator")
        assert result.get("success"), f"注册失败: {result}"
        config = result["config"]
        assert config["name"] == "skill-calculator"
        assert config["transport"] == "stdio"
        assert "mcp_server.py" in config["args"][0]
        print(f"  ✅ MCP Server 已注册: {config}")

        # 验证写入配置文件
        config_path = ROOT / "data" / "mcp_servers.json"
        if config_path.exists():
            servers = json.loads(config_path.read_text("utf-8"))
            names = [s["name"] for s in servers]
            assert "skill-calculator" in names
            print(f"  ✅ 配置文件已更新, 服务器数: {len(servers)}")

        # 清理
        unregister_mcp_server("calculator")
        mcp_script = ROOT / "skills" / "calculator" / "mcp_server.py"
        mcp_script.unlink(missing_ok=True)

    def test_unregister_mcp_server(self):
        """注销 MCP Server。"""
        from skills.mcp_wrapper import register_mcp_server, unregister_mcp_server
        register_mcp_server("calculator")
        result = unregister_mcp_server("calculator")
        assert result.get("success")
        print(f"  ✅ MCP Server 已注销: {result}")

        # 验证配置文件中已移除
        config_path = ROOT / "data" / "mcp_servers.json"
        if config_path.exists():
            servers = json.loads(config_path.read_text("utf-8"))
            names = [s["name"] for s in servers]
            assert "skill-calculator" not in names
            print("  ✅ 配置文件已移除 skill-calculator")

        # 清理
        mcp_script = ROOT / "skills" / "calculator" / "mcp_server.py"
        mcp_script.unlink(missing_ok=True)

    def test_register_idempotent(self):
        """重复注册不会产生重复配置。"""
        from skills.mcp_wrapper import register_mcp_server, unregister_mcp_server
        register_mcp_server("calculator")
        register_mcp_server("calculator")  # 第二次注册

        config_path = ROOT / "data" / "mcp_servers.json"
        if config_path.exists():
            servers = json.loads(config_path.read_text("utf-8"))
            count = sum(1 for s in servers if s["name"] == "skill-calculator")
            assert count == 1, f"应只有1个 skill-calculator，实际: {count}"
            print("  ✅ 重复注册去重正确")

        # 清理
        unregister_mcp_server("calculator")
        mcp_script = ROOT / "skills" / "calculator" / "mcp_server.py"
        mcp_script.unlink(missing_ok=True)

    def test_generated_script_is_valid_python(self):
        """生成的 MCP Server 脚本是合法 Python。"""
        from skills.mcp_wrapper import generate_mcp_server
        result = generate_mcp_server("calculator")
        assert result.get("success")
        server_path = pathlib.Path(result["path"])
        content = server_path.read_text("utf-8")
        # 尝试编译检查语法
        try:
            compile(content, server_path, "exec")
            print("  ✅ 生成的脚本语法合法")
        except SyntaxError as e:
            pytest.fail(f"生成的脚本有语法错误: {e}")
        finally:
            server_path.unlink(missing_ok=True)


class TestMCPWrapperIntegration:
    """测试 MCP Wrapper 与 skill 安装/创建的集成。"""

    def test_skill_creator_generates_mcp_server(self):
        """skill_creator 创建 skill 时自动生成 mcp_server.py。"""
        from skills.skill_creator import create_skill
        skill_name = "zztest_mcp_auto"
        skill_dir = ROOT / "skills" / skill_name
        if skill_dir.exists():
            shutil.rmtree(skill_dir)

        try:
            result = create_skill(
                skill_name, "测试 MCP 自动封装",
                [{"name": "mcp_test_tool", "description": "test", "parameters": {}}],
                scan_before_load=False,
            )
            assert result.get("success"), f"创建失败: {result}"
            mcp_script = skill_dir / "mcp_server.py"
            assert mcp_script.exists(), "mcp_server.py 应自动生成"
            content = mcp_script.read_text("utf-8")
            assert "MCPServer" in content
            assert skill_name in content
            print("  ✅ skill_creator 自动生成 mcp_server.py")
        finally:
            if skill_dir.exists():
                shutil.rmtree(skill_dir, ignore_errors=True)
            from skills import hot_reload
            hot_reload()

    def test_mcp_server_script_content(self):
        """验证生成的 MCP Server 包含正确的 skill 信息。"""
        from skills.mcp_wrapper import generate_mcp_server
        result = generate_mcp_server("notes")
        assert result.get("success")
        server_path = pathlib.Path(result["path"])
        content = server_path.read_text("utf-8")
        assert "notes" in content
        assert "initialize" in content
        assert "tools/list" in content
        assert "tools/call" in content
        assert "2024-11-05" in content  # MCP protocol version
        print("  ✅ MCP Server 脚本内容正确")
        server_path.unlink(missing_ok=True)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
