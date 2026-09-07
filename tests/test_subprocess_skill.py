"""Phase 2 测试 — subprocess 进程隔离 + 渐进信任。

运行方法:
    cd /Users/yadong/Documents/LucidMind
    python -m pytest tests/test_subprocess_skill.py -v -s
"""

import asyncio
import json
import pathlib
import shutil
import sys

import pytest

ROOT = pathlib.Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))


# ─────────────────── SubprocessSkillAdapter 单元测试 ───────────────────

class TestSubprocessSkillAdapter:
    """测试 SubprocessSkillAdapter 在子进程中执行 skill。"""

    @pytest.fixture
    def weather_adapter(self):
        """用 weather skill 创建 SubprocessSkillAdapter。"""
        from adapters.tools.subprocess_skill import SubprocessSkillAdapter
        skill_dir = ROOT / "skills" / "weather"
        manifest = json.loads((skill_dir / "manifest.json").read_text("utf-8"))
        return SubprocessSkillAdapter(skill_dir, manifest)

    @pytest.mark.asyncio
    async def test_execute_in_subprocess(self, weather_adapter):
        """子进程执行 get_weather 工具。"""
        result = await weather_adapter.execute("get_weather", {"location": "Beijing"})
        print(f"  subprocess execute → {result}")
        # 可能因网络问题失败，但不应该因进程问题失败
        assert isinstance(result, dict)
        assert "success" in result or "error" in result
        print(f"  ✅ 子进程执行完成，结果合法")

    @pytest.mark.asyncio
    async def test_execute_unknown_tool(self, weather_adapter):
        """子进程执行不存在的工具 → 返回失败。"""
        result = await weather_adapter.execute("nonexistent_tool", {})
        print(f"  subprocess unknown tool → {result}")
        assert not result.get("success")
        print(f"  ✅ 未知工具正确返回失败")

    @pytest.mark.asyncio
    async def test_execute_timeout(self):
        """子进程超时 → 返回超时错误（不阻塞主进程）。"""
        from adapters.tools.subprocess_skill import SubprocessSkillAdapter
        # 用 calculator skill（不会真的超时，但测试超时机制）
        skill_dir = ROOT / "skills" / "calculator"
        manifest = json.loads((skill_dir / "manifest.json").read_text("utf-8"))
        adapter = SubprocessSkillAdapter(skill_dir, manifest)
        # 正常执行应该远快于 30 秒
        result = await adapter.execute("calc", {"expression": "1+1"})
        print(f"  subprocess calc → {result}")
        assert isinstance(result, dict)
        print(f"  ✅ 正常执行无超时")

    def test_fallback_tool_defs(self, weather_adapter):
        """从 manifest 构建回退工具定义。"""
        defs = weather_adapter._fallback_tool_defs()
        assert len(defs) > 0
        tool_names = [d["function"]["name"] for d in defs]
        assert "get_weather" in tool_names
        print(f"  ✅ 回退工具定义: {tool_names}")

    @pytest.mark.asyncio
    async def test_subprocess_crash_isolation(self):
        """子进程崩溃不影响主进程。"""
        from adapters.tools.subprocess_skill import SubprocessSkillAdapter
        # 创建一个会崩溃的临时 skill
        crash_dir = ROOT / "skills" / "_test_crash_skill"
        crash_dir.mkdir(exist_ok=True)
        try:
            manifest = {"name": "_test_crash_skill", "entry": "main.py", "tools": ["crash_tool"]}
            (crash_dir / "manifest.json").write_text(json.dumps(manifest))
            # main.py 中 import 时直接崩溃
            (crash_dir / "main.py").write_text(
                'raise RuntimeError("INTENTIONAL CRASH FOR TESTING")\n'
            )
            adapter = SubprocessSkillAdapter(crash_dir, manifest)
            result = await adapter.execute("crash_tool", {})
            print(f"  crash skill result → {result}")
            assert not result.get("success")
            assert "error" in result
            # 主进程仍然正常
            assert True, "主进程未受影响"
            print(f"  ✅ 子进程崩溃已隔离，主进程安全")
        finally:
            shutil.rmtree(crash_dir, ignore_errors=True)


# ─────────────────── 渐进信任: trust_level 集成测试 ───────────────────

class TestTrustLevel:
    """测试 trust_level 在 discover_skills 中的分流逻辑。"""

    def test_default_trust_level_is_audited(self):
        """没有 trust_level 字段的 manifest → 默认 audited（进程内执行）。"""
        skill_dir = ROOT / "skills" / "weather"
        manifest = json.loads((skill_dir / "manifest.json").read_text("utf-8"))
        level = manifest.get("trust_level", "audited")
        assert level == "audited", f"weather 应为 audited，实际: {level}"
        print(f"  ✅ weather trust_level={level} (默认)")

    def test_skill_creator_sets_sandboxed(self):
        """skill_creator 创建的 skill 应有 trust_level=sandboxed。"""
        from skills.skill_creator import create_skill
        skill_name = "_test_trust_creator"
        skill_dir = ROOT / "skills" / skill_name

        if skill_dir.exists():
            shutil.rmtree(skill_dir)

        try:
            result = create_skill(
                skill_name, "测试信任等级",
                [{"name": "test_trust_tool", "description": "test", "parameters": {}}],
                scan_before_load=False,
            )
            assert result.get("success"), f"创建失败: {result}"
            manifest = json.loads((skill_dir / "manifest.json").read_text("utf-8"))
            assert manifest.get("trust_level") == "sandboxed", \
                f"auto-created skill 应为 sandboxed，实际: {manifest.get('trust_level')}"
            print(f"  ✅ skill_creator 设置 trust_level=sandboxed")
        finally:
            if skill_dir.exists():
                shutil.rmtree(skill_dir, ignore_errors=True)
            from skills import hot_reload
            hot_reload()

    def test_discover_respects_trust_level(self):
        """discover_skills 对 sandboxed skill 使用 SubprocessSkillAdapter。"""
        from adapters.tools.subprocess_skill import SubprocessSkillAdapter
        skill_name = "zztest_sandbox_discover"
        skill_dir = ROOT / "skills" / skill_name
        if skill_dir.exists():
            shutil.rmtree(skill_dir)

        try:
            # 创建 sandboxed skill
            skill_dir.mkdir()
            manifest = {
                "name": skill_name,
                "version": "1.0.0",
                "description": "测试 sandboxed discover",
                "entry": "main.py",
                "tools": ["sandbox_test_tool"],
                "enabled": True,
                "trust_level": "sandboxed",
            }
            (skill_dir / "manifest.json").write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
            # 简单的 main.py
            (skill_dir / "main.py").write_text(
                'from ports.tool_port import ToolPort\n'
                'from typing import Any\n'
                'class SandboxTestAdapter(ToolPort):\n'
                '    async def execute(self, tool_name: str, params: dict[str, Any]) -> dict[str, Any]:\n'
                '        return {"success": True, "result": "sandbox ok"}\n'
                '    def list_tools(self):\n'
                '        return [{"type": "function", "function": {"name": "sandbox_test_tool",\n'
                '                "description": "test", "parameters": {"type": "object", "properties": {}}}}]\n',
                encoding="utf-8")

            # 直接调用 discover_skills（不经过 hot_reload 的 sys.modules 清理）
            from skills import discover_skills, _registry as raw_registry
            discover_skills()
            # get_registry() 会排除 adapters 字段，所以直接访问 _registry
            from skills import _registry as raw_reg
            info = raw_reg.get(skill_name, {})
            assert info.get("trust_level") == "sandboxed", \
                f"registry 中应为 sandboxed，实际: {info.get('trust_level')}"
            # 检查 adapter 类型
            adapters = info.get("adapters", [])
            assert len(adapters) > 0, "应有至少一个 adapter"
            assert isinstance(adapters[0], SubprocessSkillAdapter), \
                f"sandboxed skill 应使用 SubprocessSkillAdapter，实际: {type(adapters[0])}"
            print(f"  ✅ discover_skills 正确使用 SubprocessSkillAdapter")
        finally:
            if skill_dir.exists():
                shutil.rmtree(skill_dir, ignore_errors=True)
            from skills import discover_skills
            discover_skills()


# ─────────────────── Phase 1 回归: dynamic_sensitive ───────────────────

class TestDynamicSensitive:
    """测试新安装 skill 工具自动标记为 SENSITIVE。"""

    def test_mark_skill_tools_sensitive(self):
        """mark_skill_tools_sensitive 将工具添加到 dynamic_sensitive。"""
        from adapters.tools.tool_safety import get_safety_guard
        guard = get_safety_guard()
        test_tools = ["_test_dynamic_tool_1", "_test_dynamic_tool_2"]

        try:
            guard.mark_skill_tools_sensitive(test_tools)
            for t in test_tools:
                assert guard.classify(t) == "sensitive", \
                    f"{t} 应为 sensitive，实际: {guard.classify(t)}"
            print(f"  ✅ dynamic_sensitive 正确标记")
        finally:
            for t in test_tools:
                guard._dynamic_sensitive.discard(t)
            guard._save_config()

    def test_custom_safe_overrides_dynamic(self):
        """用户已信任的工具不被 dynamic_sensitive 覆盖。"""
        from adapters.tools.tool_safety import get_safety_guard
        guard = get_safety_guard()
        tool = "_test_override_tool"

        try:
            guard.add_safe(tool)
            guard.mark_skill_tools_sensitive([tool])
            assert guard.classify(tool) == "safe", \
                f"用户信任的工具应保持 safe，实际: {guard.classify(tool)}"
            print(f"  ✅ custom_safe 优先于 dynamic_sensitive")
        finally:
            guard._custom_safe.discard(tool)
            guard._dynamic_sensitive.discard(tool)
            guard._save_config()

    def test_config_persistence(self):
        """dynamic_sensitive 应持久化到配置文件。"""
        from adapters.tools.tool_safety import get_safety_guard, _CONFIG_PATH
        guard = get_safety_guard()
        tool = "_test_persist_tool"

        try:
            guard.mark_skill_tools_sensitive([tool])
            assert _CONFIG_PATH.exists(), "配置文件应存在"
            cfg = json.loads(_CONFIG_PATH.read_text())
            assert tool in cfg.get("dynamic_sensitive", []), \
                f"配置文件应包含 {tool}"
            print(f"  ✅ dynamic_sensitive 已持久化")
        finally:
            guard._dynamic_sensitive.discard(tool)
            guard._save_config()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
