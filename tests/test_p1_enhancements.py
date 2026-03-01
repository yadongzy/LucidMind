"""P1 增强功能测试: Block直注 + 工具观察 + 两阶段提取"""

import asyncio
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))


# ── P1#6: CoreMemoryBlock 测试 ────────────────────────────────

class TestCoreMemoryBlock(unittest.TestCase):
    """高频记忆 Block 直注测试"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.db_path = self.tmp / "block_test.sqlite"
        from memory.store import MemoryStore
        from memory.block_inject import CoreMemoryBlock
        self.store = MemoryStore(self.db_path)
        self.block = CoreMemoryBlock(self.store, max_items=3)

    def tearDown(self):
        self.store.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_empty_store_returns_empty_block(self):
        self.assertEqual(self.block.get_block(), "")
        self.assertEqual(self.block.get_items(), [])

    def test_low_helpful_not_included(self):
        self.store.add("lessons", "普通教训内容，没什么特别的",
                       metadata={"helpful_count": 0, "harmful_count": 0},
                       skip_noise_filter=True)
        self.assertEqual(self.block.get_block(), "")

    def test_high_helpful_included(self):
        self.store.add("lessons", "非常有用的经验教训要记住",
                       metadata={"helpful_count": 3, "harmful_count": 0},
                       skip_noise_filter=True)
        block = self.block.get_block()
        self.assertIn("非常有用", block)

    def test_user_pref_always_included(self):
        self.store.add("facts", "用户偏好使用 Python 开发",
                       metadata={"category": "user_pref", "helpful_count": 0},
                       skip_noise_filter=True)
        block = self.block.get_block()
        self.assertIn("Python", block)
        self.assertIn("⭐", block)

    def test_max_items_respected(self):
        for i in range(10):
            self.store.add("lessons", f"有用的经验教训编号 {i} 需要记住",
                           metadata={"helpful_count": 5, "harmful_count": 0},
                           skip_noise_filter=True)
        items = self.block.get_items()
        self.assertLessEqual(len(items), 3)

    def test_cache_works(self):
        self.store.add("lessons", "缓存测试的有用经验教训内容",
                       metadata={"helpful_count": 5},
                       skip_noise_filter=True)
        block1 = self.block.get_block()
        block2 = self.block.get_block()
        self.assertEqual(block1, block2)

    def test_invalidate_clears_cache(self):
        self.store.add("lessons", "测试失效缓存的经验内容",
                       metadata={"helpful_count": 5},
                       skip_noise_filter=True)
        self.block.get_block()
        self.block.invalidate()
        self.assertEqual(self.block._cached_block, "")

    def test_user_pref_sorted_first(self):
        self.store.add("lessons", "普通高分经验但不是偏好",
                       metadata={"helpful_count": 10, "harmful_count": 0},
                       skip_noise_filter=True)
        self.store.add("facts", "用户偏好使用 Vim 编辑器",
                       metadata={"category": "user_pref", "helpful_count": 1},
                       skip_noise_filter=True)
        items = self.block.get_items()
        self.assertGreater(len(items), 0)
        # 偏好应排在前面
        first_meta = items[0].metadata or {}
        self.assertEqual(first_meta.get("category"), "user_pref")


# ── P1#7: ToolObserver 测试 ──────────────────────────────────

class TestToolObserver(unittest.TestCase):
    """工具级观察采集测试"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.db_path = self.tmp / "observer_test.sqlite"
        from memory.store import MemoryStore
        from memory.tool_observer import ToolObserver
        self.store = MemoryStore(self.db_path)
        self.observer = ToolObserver(self.store, max_observations_per_session=5)

    def tearDown(self):
        self.store.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_record_success(self):
        mid = self.observer.record(
            tool_name="read_file",
            input_args={"path": "/tmp/test.py"},
            output="文件内容...",
            success=True,
            duration_ms=42.5,
            session_id="sess_001",
        )
        self.assertIsNotNone(mid)
        self.assertNotEqual(mid, "")

    def test_record_failure(self):
        mid = self.observer.record(
            tool_name="run_command",
            input_args="ls -la",
            output=None,
            success=False,
            duration_ms=1500,
            session_id="sess_001",
        )
        self.assertIsNotNone(mid)
        obs = self.store.get_all(collection="observations", limit=10)
        self.assertGreater(len(obs), 0)
        self.assertIn("❌", obs[0].content)

    def test_rate_limiting(self):
        for i in range(10):
            self.observer.record(
                tool_name=f"tool_{i}", input_args={}, output="ok",
                success=True, session_id="sess_limit",
            )
        obs = self.store.get_all(collection="observations", limit=100)
        # max_observations_per_session=5
        sess_obs = [o for o in obs if (o.metadata or {}).get("session_id") == "sess_limit"]
        self.assertLessEqual(len(sess_obs), 5)

    def test_get_tool_stats(self):
        self.observer.record("read_file", {}, "ok", True, 10, "s1")
        self.observer.record("read_file", {}, "err", False, 20, "s1")
        stats = self.observer.get_tool_stats("read_file")
        self.assertEqual(len(stats), 2)

    def test_get_failure_patterns(self):
        for _ in range(3):
            self.observer.record("bad_tool", {}, None, False, 100, "s1")
        patterns = self.observer.get_failure_patterns(min_failures=2)
        self.assertIn("bad_tool", patterns)
        self.assertEqual(patterns["bad_tool"], 3)

    def test_no_store_returns_none(self):
        from memory.tool_observer import ToolObserver
        observer = ToolObserver(store=None)
        mid = observer.record("test", {}, "ok", True)
        self.assertIsNone(mid)

    def test_clear_session(self):
        self.observer.record("tool", {}, "ok", True, 10, "sess_x")
        self.observer.clear_session("sess_x")
        self.assertEqual(self.observer._session_counts.get("sess_x", 0), 0)


# ── P1#8: TwoStageExtractor 测试 ─────────────────────────────

class TestTwoStageExtractor(unittest.TestCase):
    """两阶段提取+动作决策测试"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.db_path = self.tmp / "extractor_test.sqlite"
        from memory.store import MemoryStore
        from memory.two_stage_extractor import TwoStageExtractor
        self.store = MemoryStore(self.db_path)
        self.extractor = TwoStageExtractor(self.store)

    def tearDown(self):
        self.store.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_empty_messages(self):
        result = asyncio.get_event_loop().run_until_complete(
            self.extractor.extract_and_decide([])
        )
        self.assertEqual(result, [])

    def test_rule_extract_preferences(self):
        messages = [
            {"role": "user", "content": "我喜欢用 Python 写代码"},
            {"role": "assistant", "content": "好的，记住了"},
        ]
        result = asyncio.get_event_loop().run_until_complete(
            self.extractor.extract_and_decide(messages, llm=None)
        )
        self.assertGreater(len(result), 0)
        self.assertEqual(result[0]["action"], "ADD")
        self.assertEqual(result[0]["type"], "PREFERENCE")

    def test_rule_extract_corrections(self):
        messages = [
            {"role": "assistant", "content": "使用 npm install"},
            {"role": "user", "content": "不对，应该是 pnpm install"},
        ]
        result = asyncio.get_event_loop().run_until_complete(
            self.extractor.extract_and_decide(messages, llm=None)
        )
        self.assertGreater(len(result), 0)
        self.assertEqual(result[0]["type"], "LESSON")

    def test_apply_add_decisions(self):
        decisions = [
            {"action": "ADD", "content": "用户偏好使用 TypeScript 开发项目",
             "type": "PREFERENCE", "session_id": "s1"},
        ]
        stats = asyncio.get_event_loop().run_until_complete(
            self.extractor.apply_decisions(decisions)
        )
        self.assertEqual(stats["added"], 1)
        self.assertEqual(self.store.count(), 1)

    def test_apply_update_decisions(self):
        mid = self.store.add("facts", "用户使用 Python 3.10 进行开发",
                             skip_noise_filter=True)
        decisions = [
            {"action": "UPDATE", "content": "用户使用 Python 3.12 进行开发",
             "type": "FACT", "memory_id": mid, "session_id": "s1"},
        ]
        stats = asyncio.get_event_loop().run_until_complete(
            self.extractor.apply_decisions(decisions)
        )
        self.assertEqual(stats["updated"], 1)
        updated = self.store.get_all()
        self.assertIn("3.12", updated[0].content)

    def test_apply_delete_decisions(self):
        mid = self.store.add("facts", "用户喜欢使用 Java 编程语言",
                             skip_noise_filter=True)
        decisions = [
            {"action": "DELETE", "content": "",
             "type": "FACT", "memory_id": mid, "session_id": "s1"},
        ]
        stats = asyncio.get_event_loop().run_until_complete(
            self.extractor.apply_decisions(decisions)
        )
        self.assertEqual(stats["deleted"], 1)
        self.assertEqual(self.store.count(), 0)

    def test_apply_skip_decisions(self):
        decisions = [
            {"action": "SKIP", "content": "已知信息",
             "type": "FACT", "session_id": "s1"},
        ]
        stats = asyncio.get_event_loop().run_until_complete(
            self.extractor.apply_decisions(decisions)
        )
        self.assertEqual(stats["skipped"], 1)

    def test_update_nonexistent_falls_back_to_add(self):
        decisions = [
            {"action": "UPDATE", "content": "新的用户偏好信息需要记录",
             "type": "FACT", "memory_id": "nonexistent_id", "session_id": "s1"},
        ]
        stats = asyncio.get_event_loop().run_until_complete(
            self.extractor.apply_decisions(decisions)
        )
        self.assertEqual(stats["added"], 1)

    def test_no_store_returns_empty(self):
        from memory.two_stage_extractor import TwoStageExtractor
        ext = TwoStageExtractor(store=None)
        stats = asyncio.get_event_loop().run_until_complete(
            ext.apply_decisions([{"action": "ADD", "content": "test"}])
        )
        self.assertEqual(stats["added"], 0)


# ── JSON 解析测试 ────────────────────────────────────────────

class TestParseJsonArray(unittest.TestCase):
    """JSON 解析辅助函数测试"""

    def test_parse_clean_json(self):
        from memory.two_stage_extractor import _parse_json_array
        result = _parse_json_array('[{"type": "FACT", "content": "test"}]')
        self.assertEqual(len(result), 1)

    def test_parse_markdown_wrapped(self):
        from memory.two_stage_extractor import _parse_json_array
        text = '```json\n[{"type": "FACT", "content": "test"}]\n```'
        result = _parse_json_array(text)
        self.assertEqual(len(result), 1)

    def test_parse_empty(self):
        from memory.two_stage_extractor import _parse_json_array
        result = _parse_json_array("[]")
        self.assertEqual(result, [])

    def test_parse_invalid(self):
        from memory.two_stage_extractor import _parse_json_array
        result = _parse_json_array("not json at all")
        self.assertEqual(result, [])


# ── 集成测试: Adapter + Block + Observer ──────────────────────

class TestAdapterIntegration(unittest.TestCase):
    """MemoryStoreLearningAdapter 集成测试"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.db_path = self.tmp / "integration_test.sqlite"
        from adapters.learning.memory_store_adapter import MemoryStoreLearningAdapter
        self.adapter = MemoryStoreLearningAdapter(db_path=self.db_path)

    def tearDown(self):
        self.adapter.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_core_block_initialized(self):
        self.assertIsNotNone(self.adapter._core_block)

    def test_tool_observer_initialized(self):
        self.assertIsNotNone(self.adapter._tool_observer)

    def test_get_lessons_with_core_block(self):
        # 添加一条高频记忆
        self.adapter.store.add(
            "facts", "用户偏好使用 Python 进行开发工作",
            metadata={"category": "user_pref", "helpful_count": 5,
                      "harmful_count": 0, "tier": "strategy"},
            skip_noise_filter=True,
        )
        lessons = asyncio.get_event_loop().run_until_complete(
            self.adapter.get_lessons("如何开发", limit=5)
        )
        self.assertGreater(len(lessons), 0)
        # 核心记忆应在结果中
        contents = [l["lesson"] for l in lessons]
        self.assertTrue(any("Python" in c for c in contents))

    def test_tool_observer_record(self):
        mid = self.adapter._tool_observer.record(
            "test_tool", {"arg": 1}, "result", True, 50.0, "s1"
        )
        self.assertIsNotNone(mid)


if __name__ == "__main__":
    unittest.main()
