"""P0 噪声过滤 + 自适应跳过 + 自动备份 测试"""

import json
import shutil
import tempfile
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from memory.noise_filter import is_noise, should_skip_retrieval, _effective_length


class TestEffectiveLength(unittest.TestCase):
    """CJK 感知的有效长度计算"""

    def test_ascii_only(self):
        self.assertEqual(_effective_length("hello"), 5)

    def test_cjk_only(self):
        self.assertEqual(_effective_length("测试经验"), 8)

    def test_mixed(self):
        self.assertEqual(_effective_length("测试 test"), 9)  # 2*2 + 5

    def test_empty(self):
        self.assertEqual(_effective_length(""), 0)


class TestIsNoise(unittest.TestCase):
    """噪声过滤测试"""

    def test_empty_is_noise(self):
        self.assertTrue(is_noise(""))
        self.assertTrue(is_noise(None))
        self.assertTrue(is_noise("   "))

    def test_too_short_ascii(self):
        self.assertTrue(is_noise("hi"))
        self.assertTrue(is_noise("ok"))

    def test_short_cjk_passes(self):
        self.assertFalse(is_noise("测试经验内容"))

    def test_denial_filtered(self):
        self.assertTrue(is_noise("I cannot access that file for you"))
        self.assertTrue(is_noise("I'm sorry, I'm unable to help with that"))
        self.assertTrue(is_noise("As an AI assistant, I don't have access"))
        self.assertTrue(is_noise("我无法访问那个文件"))

    def test_boilerplate_filtered(self):
        self.assertTrue(is_noise("你好！"))
        self.assertTrue(is_noise("谢谢！"))
        self.assertTrue(is_noise("好的。"))
        self.assertTrue(is_noise("Hello!"))

    def test_error_noise_filtered(self):
        self.assertTrue(is_noise("Ralph 循环 — 尝试了 5 次均失败"))
        self.assertTrue(is_noise("client error 404 for url https://example.com"))
        self.assertTrue(is_noise("Traceback (most recent call last)"))
        self.assertTrue(is_noise("got an unexpected keyword argument 'foo'"))

    def test_valid_content_passes(self):
        self.assertFalse(is_noise("使用工具前应检查参数类型是否正确"))
        self.assertFalse(is_noise("用户偏好使用 TypeScript 而非 JavaScript"))
        self.assertFalse(is_noise("When deploying, always run tests first"))
        self.assertFalse(is_noise("处理大文件时应该分块读取避免内存溢出"))


class TestShouldSkipRetrieval(unittest.TestCase):
    """自适应检索跳过测试"""

    def test_empty_skip(self):
        self.assertTrue(should_skip_retrieval(""))
        self.assertTrue(should_skip_retrieval(" "))

    def test_greeting_skip(self):
        self.assertTrue(should_skip_retrieval("你好"))
        self.assertTrue(should_skip_retrieval("Hello!"))
        self.assertTrue(should_skip_retrieval("hi"))

    def test_affirmation_skip(self):
        self.assertTrue(should_skip_retrieval("好的"))
        self.assertTrue(should_skip_retrieval("ok"))
        self.assertTrue(should_skip_retrieval("yes"))

    def test_command_skip(self):
        self.assertTrue(should_skip_retrieval("继续"))
        self.assertTrue(should_skip_retrieval("stop"))

    def test_normal_query_no_skip(self):
        self.assertFalse(should_skip_retrieval("如何部署应用到生产环境"))
        self.assertFalse(should_skip_retrieval("帮我写一个排序算法"))

    def test_memory_keyword_forces_retrieval(self):
        self.assertFalse(should_skip_retrieval("你记得上次的部署步骤吗"))
        self.assertFalse(should_skip_retrieval("之前我们讨论过这个问题"))
        self.assertFalse(should_skip_retrieval("我的偏好是什么"))


class TestNoiseFilterIntegration(unittest.TestCase):
    """噪声过滤集成到 MemoryStore 的测试"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.db_path = self.tmp / "test.sqlite"
        from memory.store import MemoryStore
        self.store = MemoryStore(self.db_path)

    def tearDown(self):
        self.store.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_noise_blocked_at_add(self):
        mid = self.store.add("lessons", "I cannot access that file")
        self.assertEqual(mid, "")
        self.assertEqual(self.store.count(), 0)

    def test_valid_content_stored(self):
        mid = self.store.add("lessons", "使用工具前应检查参数类型是否正确")
        self.assertNotEqual(mid, "")
        self.assertEqual(self.store.count(), 1)

    def test_skip_noise_filter_flag(self):
        mid = self.store.add("lessons", "hi", skip_noise_filter=True)
        self.assertNotEqual(mid, "")
        self.assertEqual(self.store.count(), 1)

    def test_adaptive_skip_in_search(self):
        self.store.add("lessons", "部署应用前需要运行完整测试套件")
        results = self.store.search_hybrid("你好")
        self.assertEqual(len(results), 0)

    def test_normal_search_works(self):
        self.store.add("lessons", "部署应用前需要运行完整测试套件确保通过")
        results = self.store.search_hybrid("部署应用")
        self.assertGreater(len(results), 0)


class TestBackupJsonl(unittest.TestCase):
    """自动备份 JSONL 测试"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.db_path = self.tmp / "test.sqlite"
        from memory.store import MemoryStore
        self.store = MemoryStore(self.db_path)

    def tearDown(self):
        self.store.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_backup_creates_file(self):
        self.store.add("lessons", "使用工具前应检查参数类型是否正确")
        self.store.add("facts", "用户偏好使用 Python 进行开发工作")
        path = self.store.backup_jsonl()
        self.assertIsNotNone(path)
        self.assertTrue(path.exists())
        with open(path) as f:
            lines = f.readlines()
        self.assertEqual(len(lines), 2)
        record = json.loads(lines[0])
        self.assertIn("id", record)
        self.assertIn("collection", record)
        self.assertIn("content", record)

    def test_backup_rotation(self):
        self.store.add("lessons", "使用工具前应检查参数类型是否正确")
        backup_dir = self.tmp / "backups"
        import time
        for i in range(5):
            self.store.backup_jsonl(backup_dir, max_backups=3)
            time.sleep(0.01)
        files = list(backup_dir.glob("memory_backup_*.jsonl"))
        self.assertLessEqual(len(files), 3)

    def test_backup_empty_db(self):
        path = self.store.backup_jsonl()
        self.assertIsNotNone(path)
        with open(path) as f:
            lines = f.readlines()
        self.assertEqual(len(lines), 0)


if __name__ == "__main__":
    unittest.main()
