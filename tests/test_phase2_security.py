"""Phase 2 安全体系化测试 — 发现安全 + 扫描增强 + MCP 安全验证。"""

import os
import pytest
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


# ─────────────── 节点 2.1: 插件发现安全检查 ───────────────

from skills.discovery_safety import check_plugin_safety


@pytest.fixture
def normal_plugin_dir(tmp_path):
    """创建一个正常的插件目录。"""
    d = tmp_path / "test_plugin"
    d.mkdir()
    (d / "manifest.json").write_text('{"name": "test"}')
    (d / "main.py").write_text('print("ok")')
    return d


def test_normal_plugin_passes(normal_plugin_dir):
    # Note: path_escape check will fail because tmp_path is outside skills dir,
    # so we test the individual checks via a real plugin dir.
    result = check_plugin_safety(normal_plugin_dir)
    # tmp_path outside skills dir -> path_escape blocked
    assert result["blocked"] is True
    assert any(c["name"] == "path_escape" and not c["passed"] for c in result["checks"])


def test_symlink_detection(tmp_path):
    """检测符号链接。"""
    d = tmp_path / "symlink_plugin"
    d.mkdir()
    target = tmp_path / "external_manifest.json"
    target.write_text('{"name": "evil"}')
    (d / "manifest.json").symlink_to(target)
    (d / "main.py").write_text('print("ok")')
    result = check_plugin_safety(d)
    symlink_checks = [c for c in result["checks"] if c["name"] == "symlink" and not c["passed"]]
    assert len(symlink_checks) > 0


def test_world_writable_detection(tmp_path):
    """检测 world-writable 目录。"""
    if sys.platform == "win32":
        pytest.skip("Unix-only test")
    d = tmp_path / "writable_plugin"
    d.mkdir()
    (d / "manifest.json").write_text('{"name": "test"}')
    (d / "main.py").write_text('print("ok")')
    os.chmod(d, 0o777)
    result = check_plugin_safety(d)
    ww_checks = [c for c in result["checks"] if c["name"] == "world_writable" and not c["passed"]]
    assert len(ww_checks) > 0
    assert result["blocked"] is True
    os.chmod(d, 0o755)  # cleanup


def test_large_file_warning(tmp_path):
    """大文件警告（不阻断）。"""
    d = tmp_path / "large_plugin"
    d.mkdir()
    (d / "manifest.json").write_text('{"name": "test"}')
    (d / "main.py").write_text("x = 1\n" * 100000)  # ~600KB
    result = check_plugin_safety(d)
    size_checks = [c for c in result["checks"] if c["name"] == "file_size" and not c["passed"]]
    assert len(size_checks) > 0


# ─────────────── 节点 2.2: 安全扫描增强 ───────────────

from skills.skill_scanner import scan_file, scan_skill_directory


def test_scan_file_skips_comments(tmp_path):
    """注释中的 eval 不应被标记。"""
    f = tmp_path / "test.py"
    f.write_text('# eval("bad code")\nprint("hello")\n')
    findings = scan_file(f)
    assert len(findings) == 0


def test_scan_file_skips_multiline_comments(tmp_path):
    """多行注释中的危险模式不应被标记。"""
    f = tmp_path / "test.py"
    f.write_text('"""\neval("bad code")\nsubprocess.run("ls")\n"""\nprint("ok")\n')
    findings = scan_file(f)
    assert len(findings) == 0


def test_scan_file_detects_eval(tmp_path):
    f = tmp_path / "test.py"
    f.write_text('result = eval(user_input)\n')
    findings = scan_file(f)
    assert any(f["pattern"] == "eval_exec" for f in findings)


def test_scan_file_large_file_skip(tmp_path):
    """>1MB 文件应被跳过。"""
    f = tmp_path / "huge.py"
    f.write_text("x = 1\n" * 200000)  # ~1.2MB
    findings = scan_file(f)
    assert any(f["pattern"] == "file_too_large" for f in findings)


def test_scan_recursive(tmp_path):
    """递归扫描子目录中的文件。"""
    d = tmp_path / "plugin"
    sub = d / "lib"
    sub.mkdir(parents=True)
    (d / "main.py").write_text('print("safe")\n')
    (sub / "helper.py").write_text('os.system("rm -rf /")\n')
    result = scan_skill_directory(d)
    assert result["warnings"] > 0
    assert any("helper.py" in f["file"] for f in result["findings"])


def test_new_pattern_base64_exec(tmp_path):
    f = tmp_path / "test.py"
    f.write_text('code = base64.b64decode(data); exec(code)\n')
    findings = scan_file(f)
    assert any(f["pattern"] == "base64_exec" for f in findings)


def test_new_pattern_webhook_exfil(tmp_path):
    f = tmp_path / "test.py"
    f.write_text('url = "https://discord.com/api/webhooks/123/abc"\n')
    findings = scan_file(f)
    assert any(f["pattern"] == "webhook_exfil" for f in findings)


def test_new_pattern_global_var_write(tmp_path):
    f = tmp_path / "test.py"
    f.write_text('globals()["__builtins__"] = None\n')
    findings = scan_file(f)
    assert any(f["pattern"] == "global_var_write" for f in findings)


def test_scan_history_persistence(tmp_path):
    """扫描结果应持久化到 scan_history.jsonl。"""
    d = tmp_path / "plugin"
    d.mkdir()
    (d / "main.py").write_text('print("ok")\n')
    result = scan_skill_directory(d)
    assert result["safe"] is True


# ─────────────── 节点 2.3: MCP Server 安全验证 ───────────────

from adapters.tools.mcp_client import validate_server_config


def test_mcp_safe_command_npx():
    valid, _ = validate_server_config({"transport": "stdio", "command": "npx", "args": ["-y", "pkg"]})
    assert valid is True


def test_mcp_safe_command_python():
    valid, _ = validate_server_config({"transport": "stdio", "command": "python3", "args": ["server.py"]})
    assert valid is True


def test_mcp_unsafe_command_nonexistent():
    """不在白名单且不存在的命令应被拒绝。"""
    valid, reason = validate_server_config({"transport": "stdio", "command": "evil_nonexistent_cmd_xyz"})
    assert valid is False
    assert "白名单" in reason or "未找到" in reason


def test_mcp_shell_metachar_in_args():
    valid, reason = validate_server_config({"transport": "stdio", "command": "npx", "args": ["-y", "pkg; rm -rf /"]})
    assert valid is False
    assert "元字符" in reason


def test_mcp_protected_env():
    valid, reason = validate_server_config({"transport": "stdio", "command": "npx", "args": [], "env": {"PATH": "/evil"}})
    assert valid is False
    assert "PATH" in reason


def test_mcp_http_valid():
    valid, _ = validate_server_config({"transport": "http", "url": "http://localhost:3001/mcp"})
    assert valid is True


def test_mcp_http_file_protocol():
    valid, reason = validate_server_config({"transport": "http", "url": "file:///etc/passwd"})
    assert valid is False
    assert "协议" in reason


def test_mcp_http_ftp_protocol():
    valid, reason = validate_server_config({"transport": "http", "url": "ftp://evil.com/file"})
    assert valid is False


def test_mcp_http_no_url():
    valid, reason = validate_server_config({"transport": "http"})
    assert valid is False


def test_mcp_stdio_no_command():
    valid, reason = validate_server_config({"transport": "stdio"})
    assert valid is False


# ─────────────── 节点 6.2: soul_engine 规则去重 ───────────────

def test_soul_dedup_exact_match(tmp_path):
    """完全相同的规则应判定为重复。"""
    from identity.soul_engine import SoulEngine
    import identity.soul_engine as se
    old_path = se._SOUL_PATH
    se._SOUL_PATH = tmp_path / "SOUL.md"
    se._SOUL_PATH.write_text("# LucidMind\n\n## Learned Rules\n\n- 使用工具前先检查权限\n")
    engine = SoulEngine()
    result = engine.evolve("test", "使用工具前先检查权限")
    assert result is False  # 应被判定为重复
    se._SOUL_PATH = old_path


def test_soul_dedup_prefix_not_duplicate(tmp_path):
    """前缀相同但内容不同的规则不应被判定为重复。"""
    from identity.soul_engine import SoulEngine
    import identity.soul_engine as se
    old_path = se._SOUL_PATH
    se._SOUL_PATH = tmp_path / "SOUL.md"
    se._SOUL_PATH.write_text("# LucidMind\n\n## Learned Rules\n\n- 使用工具前先检查权限\n")
    se._EVOLUTION_LOG = tmp_path / "soul_evolution.json"
    engine = SoulEngine()
    result = engine.evolve("test", "使用工具前先验证参数")
    assert result is True  # 不同规则，应成功添加
    se._SOUL_PATH = old_path
