"""Phase 1 测试: 三层加载架构 (loader.py + SKILL.md)"""

import json
import os
import sys
import tempfile
import shutil
import unittest
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))


class TestLayer1Scan(unittest.TestCase):
    """Layer 1: manifest.json 元数据扫描"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        # 创建 mock 插件
        for name, enabled, plat in [
            ("alpha", True, []),
            ("beta", False, []),
            ("gamma", True, ["windows"]),  # 平台不匹配
        ]:
            d = self.tmp / name
            d.mkdir()
            manifest = {
                "name": name, "version": "1.0.0", "description": f"{name} plugin",
                "tools": [f"{name}_tool"], "platform": plat, "enabled": enabled,
                "entry": "main.py",
            }
            (d / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            (d / "main.py").write_text("# placeholder", encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_scan_finds_all_plugins(self):
        from skills.loader import layer1_scan, _SKILLS_DIR, _meta_registry, PluginMeta
        import skills.loader as loader
        old_dir = loader._SKILLS_DIR
        loader._SKILLS_DIR = self.tmp
        try:
            result = layer1_scan()
            self.assertEqual(len(result), 3)
            self.assertIn("alpha", result)
            self.assertIn("beta", result)
            self.assertIn("gamma", result)
        finally:
            loader._SKILLS_DIR = old_dir

    def test_disabled_plugin_status(self):
        from skills.loader import layer1_scan
        import skills.loader as loader
        old_dir = loader._SKILLS_DIR
        loader._SKILLS_DIR = self.tmp
        try:
            result = layer1_scan()
            self.assertEqual(result["beta"].status, "disabled")
            self.assertFalse(result["beta"].enabled)
        finally:
            loader._SKILLS_DIR = old_dir

    def test_platform_skip(self):
        import platform
        from skills.loader import layer1_scan
        import skills.loader as loader
        old_dir = loader._SKILLS_DIR
        loader._SKILLS_DIR = self.tmp
        try:
            result = layer1_scan()
            if platform.system().lower() != "windows":
                self.assertEqual(result["gamma"].status, "platform_skip")
        finally:
            loader._SKILLS_DIR = old_dir

    def test_manifest_missing_fields_graceful(self):
        """manifest 缺字段时优雅降级"""
        d = self.tmp / "minimal"
        d.mkdir()
        (d / "manifest.json").write_text('{"name": "minimal"}', encoding="utf-8")
        (d / "main.py").write_text("# placeholder", encoding="utf-8")

        from skills.loader import layer1_scan
        import skills.loader as loader
        old_dir = loader._SKILLS_DIR
        loader._SKILLS_DIR = self.tmp
        try:
            result = layer1_scan()
            self.assertIn("minimal", result)
            self.assertEqual(result["minimal"].version, "0.0.0")
        finally:
            loader._SKILLS_DIR = old_dir


class TestLayer2SkillDoc(unittest.TestCase):
    """Layer 2: SKILL.md 技能描述"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        d = self.tmp / "with_doc"
        d.mkdir()
        (d / "manifest.json").write_text(json.dumps({
            "name": "with_doc", "version": "1.0.0", "tools": ["doc_tool"]
        }), encoding="utf-8")
        (d / "main.py").write_text("# placeholder", encoding="utf-8")
        (d / "SKILL.md").write_text("# My Skill\n使用说明...\n" * 10, encoding="utf-8")

        d2 = self.tmp / "no_doc"
        d2.mkdir()
        (d2 / "manifest.json").write_text(json.dumps({
            "name": "no_doc", "version": "1.0.0", "tools": ["nodoc_tool"]
        }), encoding="utf-8")
        (d2 / "main.py").write_text("# placeholder", encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_load_skill_doc(self):
        from skills.loader import layer1_scan, layer2_load_skill_doc
        import skills.loader as loader
        old_dir = loader._SKILLS_DIR
        loader._SKILLS_DIR = self.tmp
        try:
            layer1_scan()
            doc = layer2_load_skill_doc("with_doc")
            self.assertIsNotNone(doc)
            self.assertIn("My Skill", doc)
        finally:
            loader._SKILLS_DIR = old_dir

    def test_no_skill_doc_returns_none(self):
        from skills.loader import layer1_scan, layer2_load_skill_doc
        import skills.loader as loader
        old_dir = loader._SKILLS_DIR
        loader._SKILLS_DIR = self.tmp
        try:
            layer1_scan()
            doc = layer2_load_skill_doc("no_doc")
            self.assertIsNone(doc)
        finally:
            loader._SKILLS_DIR = old_dir

    def test_skill_doc_truncation(self):
        """SKILL.md > 2000 字符时自动截断"""
        d = self.tmp / "long_doc"
        d.mkdir()
        (d / "manifest.json").write_text(json.dumps({
            "name": "long_doc", "version": "1.0.0", "tools": ["long_tool"]
        }), encoding="utf-8")
        (d / "main.py").write_text("# placeholder", encoding="utf-8")
        (d / "SKILL.md").write_text("A" * 3000, encoding="utf-8")

        from skills.loader import layer1_scan, layer2_load_skill_doc
        import skills.loader as loader
        old_dir = loader._SKILLS_DIR
        loader._SKILLS_DIR = self.tmp
        try:
            layer1_scan()
            doc = layer2_load_skill_doc("long_doc")
            self.assertLessEqual(len(doc), 2100)  # 2000 + truncation notice
            self.assertIn("已截断", doc)
        finally:
            loader._SKILLS_DIR = old_dir


class TestFindPluginByTool(unittest.TestCase):
    """工具名→插件名反查"""

    def test_find_existing_tool(self):
        from skills.loader import layer1_scan, find_plugin_by_tool
        import skills.loader as loader
        # 使用真实 skills 目录
        layer1_scan()  # 扫描真实插件
        # weather 插件应该有 get_weather 工具
        result = find_plugin_by_tool("get_weather")
        if result:
            self.assertEqual(result, "weather")

    def test_find_nonexistent_tool(self):
        from skills.loader import find_plugin_by_tool
        result = find_plugin_by_tool("nonexistent_xyz_tool")
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
