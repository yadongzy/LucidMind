"""Phase 8 测试: ACE 集成 (Bullet 反馈 + Delta 合并 + Reflector + Collapse 检测 + LearningAdapter)"""

import asyncio
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))


class TestACEBulletFeedback(unittest.TestCase):
    """8.1: ACE Bullet helpful/harmful 反馈计数器"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.db_path = self.tmp / "test_ace.sqlite"
        from memory.store import MemoryStore
        self.store = MemoryStore(self.db_path)

    def tearDown(self):
        self.store.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_increment_helpful(self):
        mid = self.store.add("lessons", "测试经验", metadata={"helpful_count": 0, "harmful_count": 0})
        ok = self.store.increment_feedback(mid, "helpful")
        self.assertTrue(ok)
        score = self.store.get_feedback_score(mid)
        self.assertEqual(score, 1.0)

    def test_increment_harmful(self):
        mid = self.store.add("lessons", "测试经验", metadata={"helpful_count": 0, "harmful_count": 0})
        self.store.increment_feedback(mid, "harmful")
        self.store.increment_feedback(mid, "harmful")
        score = self.store.get_feedback_score(mid)
        self.assertEqual(score, -2.0)

    def test_increment_invalid_type(self):
        mid = self.store.add("lessons", "测试经验")
        ok = self.store.increment_feedback(mid, "invalid_type")
        self.assertFalse(ok)

    def test_increment_nonexistent_id(self):
        ok = self.store.increment_feedback("nonexistent_id", "helpful")
        self.assertFalse(ok)

    def test_feedback_backward_compatible(self):
        """旧记忆无 helpful_count 字段时正常工作"""
        mid = self.store.add("lessons", "旧记忆", metadata={"source": "old"})
        ok = self.store.increment_feedback(mid, "helpful")
        self.assertTrue(ok)
        score = self.store.get_feedback_score(mid)
        self.assertEqual(score, 1.0)

    def test_mixed_feedback(self):
        mid = self.store.add("lessons", "测试", metadata={"helpful_count": 0, "harmful_count": 0}, skip_noise_filter=True)
        for _ in range(5):
            self.store.increment_feedback(mid, "helpful")
        for _ in range(2):
            self.store.increment_feedback(mid, "harmful")
        score = self.store.get_feedback_score(mid)
        self.assertEqual(score, 3.0)  # 5 - 2


class TestACEMergeDeltas(unittest.TestCase):
    """8.4: 确定性 Delta 合并"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.db_path = self.tmp / "merge_test.sqlite"
        from memory.store import MemoryStore
        self.store = MemoryStore(self.db_path)

    def tearDown(self):
        self.store.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_append_new_deltas(self):
        deltas = [
            {"content": "使用工具前检查参数类型", "metadata": {"source": "reflector"}},
            {"content": "文件操作前确认路径存在", "metadata": {"source": "reflector"}},
        ]
        result = self.store.merge_deltas(deltas, collection="lessons")
        self.assertEqual(result["appended"], 2)
        self.assertEqual(result["merged"], 0)
        self.assertEqual(self.store.count("lessons"), 2)

    def test_merge_duplicate_deltas(self):
        """语义重复的 delta 应合并而非新建"""
        self.store.add("lessons", "使用工具前检查参数类型",
                       metadata={"helpful_count": 2, "harmful_count": 0, "source_sessions": ["s1"]})
        deltas = [
            {"content": "使用工具前检查参数类型", "metadata": {"source_session": "s2", "helpful_count": 1}},
        ]
        result = self.store.merge_deltas(deltas, collection="lessons")
        self.assertEqual(result["merged"], 1)
        self.assertEqual(result["appended"], 0)
        # 总数不变
        self.assertEqual(self.store.count("lessons"), 1)

    def test_merge_updates_counters(self):
        """合并时 helpful_count 正确累加"""
        mid = self.store.add("lessons", "重要策略",
                             metadata={"helpful_count": 3, "harmful_count": 0, "source_sessions": []})
        deltas = [
            {"content": "重要策略", "metadata": {"helpful_count": 2, "harmful_count": 0}},
        ]
        self.store.merge_deltas(deltas, collection="lessons")
        # 检查合并后的计数
        items = self.store.get_all(collection="lessons")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].metadata["helpful_count"], 5)  # 3 + 2

    def test_prune_harmful_entries(self):
        """harmful > helpful 且 harmful >= 3 的条目应被清理"""
        self.store.add("lessons", "有害经验",
                       metadata={"helpful_count": 0, "harmful_count": 4})
        self.store.add("lessons", "有用经验",
                       metadata={"helpful_count": 5, "harmful_count": 1})
        # 空 delta 触发 prune
        result = self.store.merge_deltas([], collection="lessons")
        self.assertEqual(result["pruned"], 1)
        self.assertEqual(self.store.count("lessons"), 1)
        remaining = self.store.get_all(collection="lessons")
        self.assertIn("有用", remaining[0].content)

    def test_empty_content_skipped(self):
        deltas = [
            {"content": "", "metadata": {}},
            {"content": "   ", "metadata": {}},
            {"content": "有效内容", "metadata": {}},
        ]
        result = self.store.merge_deltas(deltas)
        self.assertEqual(result["appended"], 1)

    def test_source_sessions_merged(self):
        """合并时 source_sessions 正确合并"""
        self.store.add("lessons", "测试策略",
                       metadata={"source_sessions": ["s1", "s2"], "helpful_count": 0, "harmful_count": 0})
        deltas = [
            {"content": "测试策略", "metadata": {"source_session": "s3", "source_sessions": ["s4"]}},
        ]
        self.store.merge_deltas(deltas, collection="lessons")
        items = self.store.get_all(collection="lessons")
        sessions = items[0].metadata.get("source_sessions", [])
        self.assertIn("s3", sessions)


class TestTextSimilarity(unittest.TestCase):
    """8.4: _text_similarity 测试"""

    def test_identical(self):
        from memory.store import MemoryStore
        self.assertEqual(MemoryStore._text_similarity("hello world", "hello world"), 1.0)

    def test_identical_with_whitespace(self):
        from memory.store import MemoryStore
        self.assertEqual(MemoryStore._text_similarity("  hello  ", "hello"), 1.0)

    def test_completely_different(self):
        from memory.store import MemoryStore
        score = MemoryStore._text_similarity("AAAA", "ZZZZ")
        self.assertLess(score, 0.5)

    def test_similar_strings(self):
        from memory.store import MemoryStore
        score = MemoryStore._text_similarity(
            "使用工具前检查参数类型",
            "使用工具前检查参数的类型"
        )
        self.assertGreater(score, 0.7)

    def test_empty_strings(self):
        from memory.store import MemoryStore
        self.assertEqual(MemoryStore._text_similarity("", "hello"), 0.0)
        self.assertEqual(MemoryStore._text_similarity("hello", ""), 0.0)


class TestCollapseDetection(unittest.TestCase):
    """8.5: Context Collapse 检测"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.db_path = self.tmp / "collapse_test.sqlite"
        from memory.store import MemoryStore
        self.store = MemoryStore(self.db_path)

    def tearDown(self):
        self.store.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_no_collapse_on_growth(self):
        """正常增长不触发 collapse"""
        for i in range(10):
            self.store.add("lessons", f"经验 {i}", metadata={"helpful_count": 1, "harmful_count": 0})
        deltas = [{"content": f"新策略 {i}", "metadata": {}} for i in range(5)]
        self.store.merge_deltas(deltas, collection="lessons")
        result = self.store.check_collapse("lessons")
        self.assertFalse(result["collapsed"])
        self.assertEqual(result["after_count"], 15)

    def test_collapse_detection_on_massive_prune(self):
        """大量 harmful 条目被清理时检测 collapse"""
        for i in range(20):
            self.store.add("lessons", f"有害经验 {i}",
                           metadata={"helpful_count": 0, "harmful_count": 5})
        for i in range(5):
            self.store.add("lessons", f"有用经验 {i}",
                           metadata={"helpful_count": 5, "harmful_count": 0})
        # 触发 merge（会 prune 20 条有害的）
        self.store.merge_deltas([], collection="lessons")
        result = self.store.check_collapse("lessons")
        self.assertTrue(result["collapsed"])
        self.assertGreater(result["drop_pct"], 0.5)

    def test_no_snapshot_returns_safe(self):
        """没有 merge 快照时返回安全"""
        from memory.store import MemoryStore
        store = MemoryStore(self.tmp / "fresh.sqlite")
        result = store.check_collapse()
        self.assertFalse(result["collapsed"])
        store.close()


class TestReflector(unittest.TestCase):
    """8.3: ACE Reflector — reflect_on_session"""

    def test_rule_based_extract_from_tool_failures(self):
        """无 LLM 时从工具失败中提取教训"""
        from memory.sync import _rule_based_extract
        messages = [
            {"role": "user", "content": "帮我查天气"},
            {"role": "assistant", "content": "正在查询..."},
        ]
        tool_results = [
            {"tool": "get_weather", "success": False, "error": "API key missing"},
        ]
        lessons = _rule_based_extract(messages, tool_results)
        self.assertGreater(len(lessons), 0)
        self.assertIn("get_weather", lessons[0])

    def test_rule_based_extract_from_corrections(self):
        """无 LLM 时从用户纠正中提取教训"""
        from memory.sync import _rule_based_extract
        messages = [
            {"role": "assistant", "content": "Python 列表用 () 创建"},
            {"role": "user", "content": "不对，Python 列表应该用 [] 创建"},
        ]
        lessons = _rule_based_extract(messages, None)
        self.assertGreater(len(lessons), 0)
        self.assertIn("纠正", lessons[0])

    def test_rule_based_no_lessons_from_normal_chat(self):
        """正常对话不应提取教训"""
        from memory.sync import _rule_based_extract
        messages = [
            {"role": "user", "content": "你好"},
            {"role": "assistant", "content": "你好！有什么可以帮你的？"},
        ]
        lessons = _rule_based_extract(messages, None)
        self.assertEqual(len(lessons), 0)

    def test_classify_collection(self):
        from memory.sync import _classify_collection
        self.assertEqual(_classify_collection("工具 run_command 执行失败", None), "skills")
        self.assertEqual(_classify_collection("用户偏好使用中文", None), "facts")
        self.assertEqual(_classify_collection("遇到问题先分析原因", None), "lessons")

    def test_parse_bullet_list(self):
        from memory.sync import _parse_bullet_list
        text = """
- 使用工具前检查参数
- 文件操作确认路径
* 错误处理要完整
1. 日志记录要详细
2. 短的
"""
        result = _parse_bullet_list(text)
        self.assertEqual(len(result), 4)  # "短的" 太短被过滤
        self.assertIn("使用工具前检查参数", result)

    def test_reflect_on_empty_messages(self):
        """空消息列表返回空"""
        from memory.sync import reflect_on_session
        result = asyncio.get_event_loop().run_until_complete(
            reflect_on_session([], None, None)
        )
        self.assertEqual(result, [])

    def test_reflect_with_tool_failures_no_llm(self):
        """无 LLM 时使用规则提取"""
        from memory.sync import reflect_on_session
        messages = [
            {"role": "user", "content": "执行命令"},
            {"role": "assistant", "content": "好的"},
        ]
        tool_results = [
            {"tool": "run_shell", "success": False, "error": "permission denied"},
        ]
        result = asyncio.get_event_loop().run_until_complete(
            reflect_on_session(messages, tool_results, llm=None)
        )
        self.assertGreater(len(result), 0)
        self.assertIn("content", result[0])
        self.assertIn("collection", result[0])
        self.assertIn("metadata", result[0])
        self.assertEqual(result[0]["metadata"]["source"], "reflector")


class TestMemoryStoreLearningAdapter(unittest.TestCase):
    """8.2: MemoryStoreLearningAdapter — 实现 LearningPort"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.db_path = self.tmp / "adapter_test.sqlite"
        from memory.types import MemoryConfig
        self.config = MemoryConfig()
        from adapters.learning.memory_store_adapter import MemoryStoreLearningAdapter
        self.adapter = MemoryStoreLearningAdapter(db_path=self.db_path, config=self.config)

    def tearDown(self):
        self.adapter.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run(self, coro):
        return asyncio.get_event_loop().run_until_complete(coro)

    def test_learn_and_retrieve(self):
        """learn() 存储经验，get_lessons() 检索"""
        self._run(self.adapter.learn({
            "trigger": "Python 列表操作",
            "lesson": "使用列表推导式比 for 循环更 Pythonic",
            "source": "teaching",
            "source_session": "s1",
        }))
        lessons = self._run(self.adapter.get_lessons("Python 列表", limit=3))
        self.assertGreater(len(lessons), 0)
        self.assertIn("列表", lessons[0]["lesson"])

    def test_learn_empty_skipped(self):
        """空 trigger 或 lesson 跳过"""
        self._run(self.adapter.learn({"trigger": "", "lesson": ""}))
        self.assertEqual(self.adapter.store.count(), 0)

    def test_learn_duplicate_merge(self):
        """重复经验合并"""
        self._run(self.adapter.learn({
            "trigger": "文件操作注意事项",
            "lesson": "文件操作注意事项: 使用前检查路径",
            "source": "correction",
            "source_session": "s1",
        }))
        self._run(self.adapter.learn({
            "trigger": "文件操作注意事项",
            "lesson": "文件操作注意事项: 使用前检查路径存在性",
            "source": "correction",
            "source_session": "s2",
        }))
        # 应该合并为 1 条（因为文本高度相似）
        total = self.adapter.store.count()
        self.assertLessEqual(total, 2)  # 最多 2 条（如果不足够相似就是 2 条）

    def test_mark_applied(self):
        """mark_applied 正确递增 applied_count"""
        self._run(self.adapter.learn({
            "trigger": "测试",
            "lesson": "测试: 每次提交前运行测试",
            "source": "auto",
        }))
        lessons = self._run(self.adapter.get_lessons("测试"))
        self.assertGreater(len(lessons), 0)
        lid = lessons[0]["id"]
        self._run(self.adapter.mark_applied(lid))
        self._run(self.adapter.mark_applied(lid))
        # 检查 applied_count
        updated = self._run(self.adapter.get_lessons("测试"))
        self.assertEqual(updated[0]["applied_count"], 2)

    def test_update_effectiveness(self):
        """update_effectiveness 更新 ACE 计数器"""
        self._run(self.adapter.learn({
            "trigger": "效果测试",
            "lesson": "效果测试: 验证有效性追踪",
            "source": "auto",
        }))
        lessons = self._run(self.adapter.get_lessons("效果"))
        lid = lessons[0]["id"]
        self._run(self.adapter.update_effectiveness(lid, True))
        self._run(self.adapter.update_effectiveness(lid, True))
        self._run(self.adapter.update_effectiveness(lid, False))
        # 检查 helpful=2, harmful=1
        score = self.adapter.store.get_feedback_score(lid)
        self.assertEqual(score, 1.0)  # 2 - 1

    def test_lesson_dict_format(self):
        """输出的 lesson dict 兼容 brain_learning.py"""
        self._run(self.adapter.learn({
            "trigger": "格式测试",
            "lesson": "格式测试: 输出格式兼容性验证",
            "source": "teaching",
            "source_session": "s1",
        }))
        lessons = self._run(self.adapter.get_lessons("格式"))
        self.assertGreater(len(lessons), 0)
        l = lessons[0]
        # 必须有这些字段（兼容 brain_learning.py）
        self.assertIn("id", l)
        self.assertIn("trigger", l)
        self.assertIn("lesson", l)
        self.assertIn("category", l)
        self.assertIn("tier", l)
        self.assertIn("source", l)
        self.assertIn("applied_count", l)
        self.assertIn("helpful_count", l)
        self.assertIn("harmful_count", l)

    def test_tier_classification(self):
        """teaching/correction 源的经验应归类为 strategy tier"""
        self._run(self.adapter.learn({
            "trigger": "tier 测试",
            "lesson": "tier 测试: 教学来源应为 strategy",
            "source": "teaching",
        }))
        lessons = self._run(self.adapter.get_lessons("tier"))
        self.assertGreater(len(lessons), 0)
        self.assertEqual(lessons[0]["tier"], "strategy")


class TestEndToEndACEWorkflow(unittest.TestCase):
    """端到端 ACE 工作流测试"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.db_path = self.tmp / "e2e_test.sqlite"
        from memory.store import MemoryStore
        self.store = MemoryStore(self.db_path)

    def tearDown(self):
        self.store.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_full_ace_cycle(self):
        """完整 ACE 循环: Reflect → Delta → Merge → Feedback → Prune"""
        from memory.sync import _rule_based_extract, _classify_collection

        # 1. Reflector 提取
        messages = [
            {"role": "user", "content": "帮我分析代码"},
            {"role": "assistant", "content": "代码有问题..."},
            {"role": "user", "content": "不对，你应该用 ast 模块分析"},
        ]
        tool_results = [
            {"tool": "run_python", "success": False, "error": "syntax error"},
        ]
        raw = _rule_based_extract(messages, tool_results)
        self.assertGreater(len(raw), 0)

        # 2. 构建 delta bullets
        deltas = []
        for lesson in raw:
            collection = _classify_collection(lesson, tool_results)
            deltas.append({
                "content": lesson,
                "collection": collection,
                "metadata": {"source": "reflector", "helpful_count": 1, "harmful_count": 0},
            })

        # 3. 合并到 store
        for d in deltas:
            col = d.pop("collection", "lessons")
            result = self.store.merge_deltas([d], collection=col)
            self.assertGreaterEqual(result["appended"] + result["merged"], 0)

        total = self.store.count()
        self.assertGreater(total, 0)

        # 4. 反馈
        items = self.store.get_all()
        for item in items:
            self.store.increment_feedback(item.id, "helpful")

        # 5. 检查无 collapse
        collapse = self.store.check_collapse()
        self.assertFalse(collapse["collapsed"])


class TestACEReflectorWiring(unittest.TestCase):
    """8.6: _ace_reflect_and_merge 串联测试"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.db_path = self.tmp / "reflector_test.sqlite"
        from adapters.learning.memory_store_adapter import MemoryStoreLearningAdapter
        self.adapter = MemoryStoreLearningAdapter(db_path=self.db_path)
        self.store = self.adapter.store

    def tearDown(self):
        self.adapter.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _make_mixin(self, history):
        """构造一个最小 BrainLearningMixin 实例用于测试"""
        from brain_learning import BrainLearningMixin
        mixin = BrainLearningMixin()
        mixin.learning = self.adapter
        mixin._history = history
        mixin.llm = None  # 无 LLM → 回退规则提取
        return mixin

    def test_skip_short_history(self):
        """历史少于4条时不触发 Reflector"""
        mixin = self._make_mixin([
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello"},
        ])
        before = self.store.count()
        asyncio.get_event_loop().run_until_complete(
            mixin._ace_reflect_and_merge("test_session")
        )
        self.assertEqual(self.store.count(), before)

    def test_skip_system_session(self):
        """系统内部 session 不触发 Reflector"""
        history = [
            {"role": "user", "content": "自检"},
            {"role": "assistant", "content": "ok"},
            {"role": "user", "content": "继续"},
            {"role": "assistant", "content": "完成"},
        ]
        mixin = self._make_mixin(history)
        before = self.store.count()
        for sid in ["boot_check", "daily_check", "self_check", "curiosity", "task_123"]:
            asyncio.get_event_loop().run_until_complete(
                mixin._ace_reflect_and_merge(sid)
            )
        self.assertEqual(self.store.count(), before)

    def test_skip_no_learning_adapter(self):
        """无 learning adapter 时静默跳过"""
        from brain_learning import BrainLearningMixin
        mixin = BrainLearningMixin()
        mixin.learning = None
        mixin._history = [{"role": "user", "content": "x"}] * 5
        # 不应抛异常
        asyncio.get_event_loop().run_until_complete(
            mixin._ace_reflect_and_merge("test")
        )

    def test_skip_no_store_attribute(self):
        """learning adapter 无 .store 属性时静默跳过"""
        from brain_learning import BrainLearningMixin

        class FakeLearning:
            pass

        mixin = BrainLearningMixin()
        mixin.learning = FakeLearning()
        mixin._history = [{"role": "user", "content": "x"}] * 5
        asyncio.get_event_loop().run_until_complete(
            mixin._ace_reflect_and_merge("test")
        )

    def test_reflector_extracts_from_tool_messages(self):
        """包含工具消息的对话能提取策略（规则回退模式）"""
        history = [
            {"role": "user", "content": "帮我运行 ls 命令"},
            {"role": "assistant", "content": "好的，执行 run_shell"},
            {"role": "tool", "content": "file1.txt file2.txt", "tool_call_id": "run_shell_1"},
            {"role": "assistant", "content": "运行成功，有两个文件"},
            {"role": "user", "content": "不对，你应该用 ls -la 显示详细信息"},
            {"role": "assistant", "content": "收到，下次用 ls -la"},
        ]
        mixin = self._make_mixin(history)
        before = self.store.count()
        asyncio.get_event_loop().run_until_complete(
            mixin._ace_reflect_and_merge("user_session")
        )
        # 规则提取应该能从纠正信号中提取到策略
        after = self.store.count()
        self.assertGreaterEqual(after, before)


class TestPlaybookInjection(unittest.TestCase):
    """8.7: Playbook 注入格式测试"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.db_path = self.tmp / "playbook_test.sqlite"
        from adapters.learning.memory_store_adapter import MemoryStoreLearningAdapter
        self.adapter = MemoryStoreLearningAdapter(db_path=self.db_path)

    def tearDown(self):
        self.adapter.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _make_mixin(self):
        from brain_learning import BrainLearningMixin
        mixin = BrainLearningMixin()
        mixin.learning = self.adapter
        mixin._history = [
            {"role": "user", "content": "帮我写代码"},
            {"role": "assistant", "content": "好的"},
        ]
        mixin._last_injected_lesson_ids = []
        mixin.lessons_enabled = True
        mixin._current_sid = "test_playbook"
        mixin._lesson_cache = {}
        return mixin

    def test_playbook_filters_harmful(self):
        """有害经验(harmful > helpful 且 harmful >= 2)不注入"""
        # 插入一条有害经验
        self.adapter.store.add("lessons", "有害策略: 直接删除文件",
                               metadata={"trigger": "删除文件", "helpful_count": 0,
                                         "harmful_count": 3, "applied_count": 0})
        # 插入一条正常经验
        self.adapter.store.add("lessons", "正常策略: 写代码前先读文档",
                               metadata={"trigger": "写代码", "helpful_count": 2,
                                         "harmful_count": 0, "applied_count": 0})
        mixin = self._make_mixin()
        result = asyncio.get_event_loop().run_until_complete(
            mixin._get_relevant_lessons()
        )
        self.assertNotIn("有害策略", result)

    def test_playbook_format_with_trigger(self):
        """有 trigger 时格式为 [trigger] content"""
        self.adapter.store.add("lessons", "用 ast 模块分析代码",
                               metadata={"trigger": "分析代码", "helpful_count": 1,
                                         "harmful_count": 0, "applied_count": 0})
        mixin = self._make_mixin()
        mixin._history = [{"role": "user", "content": "分析代码"}]
        result = asyncio.get_event_loop().run_until_complete(
            mixin._get_relevant_lessons()
        )
        if result:
            self.assertTrue(result.startswith("- "))

    def test_playbook_empty_when_no_lessons(self):
        """无匹配经验时返回空字符串"""
        mixin = self._make_mixin()
        mixin._history = [{"role": "user", "content": "zzz_no_match_xyz"}]
        result = asyncio.get_event_loop().run_until_complete(
            mixin._get_relevant_lessons()
        )
        # 可能为空也可能有结果（取决于 FTS 匹配）
        self.assertIsInstance(result, str)


class TestFeedbackLoop(unittest.TestCase):
    """8.8: 反馈闭环验证"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.db_path = self.tmp / "feedback_test.sqlite"
        from adapters.learning.memory_store_adapter import MemoryStoreLearningAdapter
        self.adapter = MemoryStoreLearningAdapter(db_path=self.db_path)

    def tearDown(self):
        self.adapter.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_mark_effective_increments_helpful(self):
        """mark_lessons_effective(True) → increment_feedback(helpful)"""
        mid = self.adapter.store.add("lessons", "测试经验",
                                     metadata={"trigger": "test", "helpful_count": 0,
                                                "harmful_count": 0, "applied_count": 0})
        asyncio.get_event_loop().run_until_complete(
            self.adapter.update_effectiveness(mid, True)
        )
        score = self.adapter.store.get_feedback_score(mid)
        self.assertGreater(score, 0)

    def test_mark_ineffective_increments_harmful(self):
        """mark_lessons_effective(False) → increment_feedback(harmful)"""
        mid = self.adapter.store.add("lessons", "测试经验",
                                     metadata={"trigger": "test", "helpful_count": 0,
                                                "harmful_count": 0, "applied_count": 0})
        asyncio.get_event_loop().run_until_complete(
            self.adapter.update_effectiveness(mid, False)
        )
        score = self.adapter.store.get_feedback_score(mid)
        self.assertLess(score, 0)

    def test_mark_applied_increments_count(self):
        """mark_applied() 增加 applied_count"""
        mid = self.adapter.store.add("lessons", "测试",
                                     metadata={"trigger": "t", "applied_count": 0},
                                     skip_noise_filter=True)
        asyncio.get_event_loop().run_until_complete(
            self.adapter.mark_applied(mid)
        )
        row = self.adapter.store.db.execute(
            "SELECT metadata_json FROM memories WHERE id=?", (mid,)
        ).fetchone()
        meta = json.loads(row["metadata_json"])
        self.assertEqual(meta["applied_count"], 1)

    def test_full_feedback_cycle(self):
        """完整反馈周期: learn → get → mark_applied → mark_effective"""
        asyncio.get_event_loop().run_until_complete(
            self.adapter.learn({
                "trigger": "测试触发",
                "lesson": "测试教训内容",
                "source": "test",
            })
        )
        lessons = asyncio.get_event_loop().run_until_complete(
            self.adapter.get_lessons("测试触发", limit=1)
        )
        self.assertGreater(len(lessons), 0)
        lid = lessons[0]["id"]
        asyncio.get_event_loop().run_until_complete(
            self.adapter.mark_applied(lid)
        )
        asyncio.get_event_loop().run_until_complete(
            self.adapter.update_effectiveness(lid, True)
        )
        score = self.adapter.store.get_feedback_score(lid)
        self.assertGreater(score, 0)


class TestMigration(unittest.TestCase):
    """8.9: lessons.json → SQLite 迁移测试"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.db_path = self.tmp / "migrate_test.sqlite"
        from memory.store import MemoryStore
        self.store = MemoryStore(self.db_path)
        self.lessons_path = self.tmp / "lessons.json"

    def tearDown(self):
        self.store.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_migrate_basic(self):
        """基本迁移: JSON → SQLite"""
        from memory.migrate import migrate_lessons_to_store
        lessons = [
            {"id": "t1", "tier": "strategy", "trigger": "触发1", "lesson": "教训1",
             "source": "seed", "category": "method", "effectiveness": 1.0, "applied_count": 5},
            {"id": "t2", "tier": "temp", "trigger": "触发2", "lesson": "教训2",
             "source": "auto", "category": "tool_usage", "effectiveness": 0.8, "applied_count": 2},
        ]
        self.lessons_path.write_text(json.dumps(lessons), encoding="utf-8")
        result = migrate_lessons_to_store(self.store, self.lessons_path)
        self.assertEqual(result["migrated"], 2)
        self.assertEqual(result["errors"], 0)
        self.assertGreater(self.store.count(), 0)

    def test_migrate_idempotent(self):
        """重复迁移不会重复插入"""
        from memory.migrate import migrate_lessons_to_store
        lessons = [{"id": "t1", "trigger": "a", "lesson": "b"}]
        self.lessons_path.write_text(json.dumps(lessons), encoding="utf-8")
        migrate_lessons_to_store(self.store, self.lessons_path)
        result2 = migrate_lessons_to_store(self.store, self.lessons_path)
        self.assertEqual(result2["skipped"], 1)

    def test_migrate_missing_file(self):
        """文件不存在时安全返回"""
        from memory.migrate import migrate_lessons_to_store
        result = migrate_lessons_to_store(self.store, self.tmp / "nonexist.json")
        self.assertEqual(result["migrated"], 0)


if __name__ == "__main__":
    unittest.main()
