"""Phase B 三层插件加载测试 — Layer 1/2/3 + LazyPluginAdapter + 懒加载 fallback。"""

import asyncio
import os
import sys


sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


# ─────────────── Layer 1: 元数据扫描 ───────────────

def test_layer1_scan_returns_plugin_metas():
    from skills.loader import layer1_scan
    metas = layer1_scan()
    assert len(metas) > 0, "应至少扫描到一个插件"
    for name, meta in metas.items():
        assert meta.name == name
        assert meta.status in ("registered", "disabled", "platform_skip", "error")
        assert meta.load_level == 1


def test_layer1_scan_speed():
    """Layer 1 扫描应 < 200ms。"""
    import time
    from skills.loader import layer1_scan
    t0 = time.time()
    layer1_scan()
    elapsed = (time.time() - t0) * 1000
    assert elapsed < 200, f"Layer 1 扫描耗时 {elapsed:.0f}ms，超过 200ms 限制"


def test_layer1_disabled_plugin_status():
    from skills.loader import layer1_scan
    metas = layer1_scan()
    # 如果有任何 disabled 的插件，验证状态
    for name, meta in metas.items():
        if not meta.enabled:
            assert meta.status == "disabled"


# ─────────────── Layer 2: SKILL.md ───────────────

def test_layer2_load_skill_doc():
    from skills.loader import layer1_scan, layer2_load_skill_doc
    layer1_scan()
    # clipboard 应有 SKILL.md
    doc = layer2_load_skill_doc("clipboard")
    if doc:
        assert "clipboard" in doc.lower() or "剪贴板" in doc
        assert len(doc) <= 2001  # 最多 2000 + 截断标记


def test_layer2_nonexistent_plugin():
    from skills.loader import layer1_scan, layer2_load_skill_doc
    layer1_scan()
    doc = layer2_load_skill_doc("nonexistent_plugin_xyz")
    assert doc is None


def test_layer2_plugin_without_skill_md():
    """没有 SKILL.md 的插件应正常工作（向后兼容）。"""
    from skills.loader import layer1_scan, layer2_load_skill_doc
    metas = layer1_scan()
    # 找一个没有 SKILL.md 的插件
    for name, meta in metas.items():
        if not (meta.path / "SKILL.md").exists():
            doc = layer2_load_skill_doc(name)
            assert doc is None
            break


# ─────────────── Layer 3: 完整加载 ───────────────

def test_layer3_full_load():
    from skills.loader import layer1_scan, layer3_full_load
    metas = layer1_scan()
    # 找一个 registered 的插件
    for name, meta in metas.items():
        if meta.status == "registered":
            adapters = layer3_full_load(name)
            assert isinstance(adapters, list)
            # 加载后状态应为 active 或 error
            assert meta.status in ("active", "error", "security_blocked")
            if meta.status == "active":
                assert meta.load_level == 3
                assert len(meta.tools_actual) > 0
            break


def test_layer3_disabled_plugin_skipped():
    from skills.loader import layer1_scan, layer3_full_load
    metas = layer1_scan()
    for name, meta in metas.items():
        if meta.status == "disabled":
            adapters = layer3_full_load(name)
            assert adapters == []
            break


# ─────────────── LazyPluginAdapter ───────────────

def test_lazy_adapter_list_tools_stub():
    from skills.loader import PluginMeta, LazyPluginAdapter
    import pathlib
    meta = PluginMeta(
        name="test_plugin",
        description="测试插件",
        tool_names=["test_tool_a", "test_tool_b"],
        path=pathlib.Path("/tmp/fake"),
    )
    adapter = LazyPluginAdapter(meta)
    tools = adapter.list_tools()
    assert len(tools) == 2
    assert tools[0]["function"]["name"] == "test_tool_a"
    assert "test_plugin" in tools[0]["function"]["description"]
    assert adapter.is_lazy is True
    assert adapter.is_loaded is False


def test_lazy_adapter_real_plugin():
    """使用真实插件测试 LazyPluginAdapter。"""
    from skills.loader import layer1_scan, LazyPluginAdapter
    metas = layer1_scan()
    for name, meta in metas.items():
        if meta.status == "registered" and meta.tool_names:
            adapter = LazyPluginAdapter(meta)
            # 未加载时返回 stub
            tools_before = adapter.list_tools()
            assert len(tools_before) == len(meta.tool_names)
            assert adapter.is_loaded is False
            # 触发加载（通过 execute）
            result = asyncio.get_event_loop().run_until_complete(
                adapter.execute(meta.tool_names[0], {}))
            # 加载后应返回真实定义
            assert adapter.is_loaded is True
            tools_after = adapter.list_tools()
            # 真实定义应有 parameters
            if tools_after:
                assert "parameters" in tools_after[0]["function"]
            break


# ─────────────── discover_skills_lazy ───────────────

def test_discover_skills_lazy():
    from skills.discovery import discover_skills
    adapters = discover_skills(lazy=True)
    assert isinstance(adapters, list)
    # 应有 LazyPluginAdapter 实例
    lazy_count = sum(1 for a in adapters if getattr(a, 'is_lazy', False))
    assert lazy_count > 0, "应至少有一个 LazyPluginAdapter"


def test_discover_skills_eager_backward_compat():
    """非 lazy 模式应与之前行为一致。"""
    from skills.discovery import discover_skills
    adapters = discover_skills(lazy=False)
    assert isinstance(adapters, list)
    # 没有 LazyPluginAdapter
    lazy_count = sum(1 for a in adapters if getattr(a, 'is_lazy', False))
    assert lazy_count == 0


# ─────────────── find_plugin_by_tool ───────────────

def test_find_plugin_by_tool():
    from skills.loader import layer1_scan, find_plugin_by_tool
    metas = layer1_scan()
    for name, meta in metas.items():
        if meta.tool_names:
            result = find_plugin_by_tool(meta.tool_names[0])
            assert result == name
            break


def test_find_plugin_by_tool_nonexistent():
    from skills.loader import layer1_scan, find_plugin_by_tool
    layer1_scan()
    result = find_plugin_by_tool("nonexistent_tool_xyz_12345")
    assert result is None


# ─────────────── CompositeToolAdapter 懒加载 ───────────────

def test_composite_lazy_load_fallback():
    """CompositeToolAdapter 应在找不到工具时尝试懒加载。"""
    from adapters.tools.composite import CompositeToolAdapter
    from skills.loader import layer1_scan
    layer1_scan()
    adapter = CompositeToolAdapter([])
    # _try_lazy_load 应返回 None 对未知工具
    result = adapter._try_lazy_load("nonexistent_tool_xyz")
    assert result is None


# ─────────────── SKILL.md 存在性 ───────────────

def test_skill_md_exists_for_key_plugins():
    """至少 3 个插件应有 SKILL.md。"""
    from skills.registry import _SKILLS_DIR
    count = 0
    for sub_dir in _SKILLS_DIR.iterdir():
        if sub_dir.is_dir() and (sub_dir / "SKILL.md").exists():
            count += 1
    assert count >= 3, f"只有 {count} 个插件有 SKILL.md，需要至少 3 个"


# ─────────────── PluginMeta.to_dict ───────────────

def test_plugin_meta_to_dict():
    from skills.loader import PluginMeta
    import pathlib
    meta = PluginMeta(name="test", version="1.0", description="desc",
                      path=pathlib.Path("/tmp"))
    d = meta.to_dict()
    assert d["name"] == "test"
    assert d["version"] == "1.0"
    assert "adapters" not in d  # 不应暴露内部实例
