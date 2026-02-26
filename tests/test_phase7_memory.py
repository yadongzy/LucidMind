"""Phase 7 测试: 记忆架构升级 (MemoryStore + Chunking + Collections + Config)"""

import json
import os
import sys
import tempfile
import shutil
import unittest
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))


class TestMemoryStore(unittest.TestCase):
    """7.1: SQLite + FTS5 存储后端"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.db_path = self.tmp / "test.sqlite"
        from memory.store import MemoryStore
        self.store = MemoryStore(self.db_path, embedding_dim=768)

    def tearDown(self):
        self.store.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_add_and_count(self):
        self.store.add("lessons", "测试经验1")
        self.store.add("lessons", "测试经验2")
        self.store.add("facts", "用户偏好")
        self.assertEqual(self.store.count(), 3)
        self.assertEqual(self.store.count("lessons"), 2)
        self.assertEqual(self.store.count("facts"), 1)

    def test_search_text(self):
        self.store.add("lessons", "Python 列表推导式是一种简洁的创建列表的方法")
        self.store.add("lessons", "JavaScript 的 map 函数可以遍历数组")
        self.store.add("facts", "用户喜欢 Python")
        results = self.store.search_text("Python")
        self.assertGreater(len(results), 0)
        self.assertTrue(any("Python" in r.content for r in results))

    def test_search_text_with_collection_filter(self):
        self.store.add("lessons", "Python 很好用")
        self.store.add("facts", "Python 是用户最爱")
        results = self.store.search_text("Python", collection="facts")
        self.assertTrue(all(r.collection == "facts" for r in results))

    def test_search_hybrid_without_vector(self):
        """无向量时，混合搜索退化为纯文本搜索"""
        self.store.add("lessons", "使用工具前先检查权限")
        self.store.add("lessons", "文件操作用 read_file 而非 cat")
        results = self.store.search_hybrid("工具 权限", limit=2)
        self.assertGreater(len(results), 0)

    def test_delete(self):
        mid = self.store.add("lessons", "待删除的经验")
        self.assertEqual(self.store.count(), 1)
        ok = self.store.delete(mid)
        self.assertTrue(ok)
        self.assertEqual(self.store.count(), 0)

    def test_delete_nonexistent(self):
        ok = self.store.delete("nonexistent_id")
        self.assertFalse(ok)

    def test_update(self):
        mid = self.store.add("lessons", "原始内容")
        ok = self.store.update(mid, content="更新后的内容")
        self.assertTrue(ok)
        results = self.store.get_all()
        self.assertEqual(results[0].content, "更新后的内容")

    def test_update_metadata(self):
        mid = self.store.add("lessons", "测试", metadata={"source": "test"})
        self.store.update(mid, metadata={"source": "updated", "extra": True})
        results = self.store.get_all()
        self.assertEqual(results[0].metadata["source"], "updated")

    def test_list_collections(self):
        self.store.add("lessons", "l1")
        self.store.add("lessons", "l2")
        self.store.add("facts", "f1")
        self.store.add("sessions", "s1")
        cols = self.store.list_collections()
        self.assertEqual(cols["lessons"], 2)
        self.assertEqual(cols["facts"], 1)
        self.assertEqual(cols["sessions"], 1)

    def test_get_all_pagination(self):
        for i in range(20):
            self.store.add("lessons", f"经验 {i}")
        page1 = self.store.get_all(limit=10, offset=0)
        page2 = self.store.get_all(limit=10, offset=10)
        self.assertEqual(len(page1), 10)
        self.assertEqual(len(page2), 10)
        ids1 = {r.id for r in page1}
        ids2 = {r.id for r in page2}
        self.assertEqual(len(ids1 & ids2), 0)  # 无重叠

    def test_collection_isolation(self):
        """不同 collection 之间数据隔离"""
        self.store.add("lessons", "lessons 内容")
        self.store.add("facts", "facts 内容")
        lessons_only = self.store.get_all(collection="lessons")
        self.assertEqual(len(lessons_only), 1)
        self.assertEqual(lessons_only[0].collection, "lessons")

    def test_metadata_json_roundtrip(self):
        meta = {"tier": "strategy", "score": 0.95, "tags": ["重要", "核心"]}
        mid = self.store.add("lessons", "带元数据的经验", metadata=meta)
        results = self.store.get_all()
        self.assertEqual(results[0].metadata["tier"], "strategy")
        self.assertEqual(results[0].metadata["score"], 0.95)
        self.assertIn("核心", results[0].metadata["tags"])


class TestChunking(unittest.TestCase):
    """7.2: 文本分块"""

    def test_short_text_no_chunk(self):
        from memory.chunking import chunk_text
        result = chunk_text("短文本", max_tokens=400)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0], "短文本")

    def test_empty_text(self):
        from memory.chunking import chunk_text
        self.assertEqual(chunk_text(""), [])
        self.assertEqual(chunk_text("  "), [])

    def test_long_text_chunks(self):
        from memory.chunking import chunk_text
        text = "这是一段很长的中文文本。" * 200  # ~2400 中文字符 ≈ 1600 tokens
        chunks = chunk_text(text, max_tokens=400, overlap=80)
        self.assertGreater(len(chunks), 1)
        for chunk in chunks:
            self.assertGreater(len(chunk), 0)

    def test_overlap_exists(self):
        from memory.chunking import chunk_text
        text = "ABCDEFGHIJ" * 200
        chunks = chunk_text(text, max_tokens=100, overlap=20)
        if len(chunks) >= 2:
            # 后一个块的开头应与前一个块的结尾有重叠
            overlap_found = False
            for i in range(len(chunks) - 1):
                tail = chunks[i][-50:]
                head = chunks[i+1][:50]
                if any(c in head for c in tail):
                    overlap_found = True
                    break
            # 至少应该有某种重叠
            self.assertTrue(overlap_found or len(chunks) <= 1)

    def test_chunk_messages(self):
        from memory.chunking import chunk_messages
        messages = [
            {"role": "user", "content": "你好" * 100},
            {"role": "assistant", "content": "你好！" * 100},
            {"role": "user", "content": "帮我分析一下" * 100},
        ]
        chunks = chunk_messages(messages, max_tokens=200)
        self.assertGreater(len(chunks), 0)


class TestMemoryConfig(unittest.TestCase):
    """7.4: 记忆配置系统"""

    def test_default_config(self):
        from memory.types import MemoryConfig
        cfg = MemoryConfig()
        self.assertTrue(cfg.enabled)
        self.assertEqual(cfg.embedding_provider, "ollama")
        self.assertEqual(cfg.vector_weight, 0.7)
        self.assertEqual(cfg.text_weight, 0.3)

    def test_from_dict(self):
        from memory.types import MemoryConfig
        cfg = MemoryConfig.from_dict({
            "embedding_provider": "openai",
            "max_results": 10,
            "vector_weight": 0.8,
            "text_weight": 0.2,
        })
        self.assertEqual(cfg.embedding_provider, "openai")
        self.assertEqual(cfg.max_results, 10)
        self.assertAlmostEqual(cfg.vector_weight, 0.8, places=1)

    def test_clamp_invalid_values(self):
        from memory.types import MemoryConfig
        cfg = MemoryConfig.from_dict({
            "min_score": 2.0,  # 超出 [0, 1]
            "max_results": -5,  # 负数
            "chunk_tokens": 10,  # 太小但合法
        })
        self.assertLessEqual(cfg.min_score, 1.0)
        self.assertGreaterEqual(cfg.max_results, 1)
        self.assertGreaterEqual(cfg.chunk_tokens, 50)

    def test_weight_normalization(self):
        from memory.types import MemoryConfig
        cfg = MemoryConfig.from_dict({
            "vector_weight": 3.0,
            "text_weight": 1.0,
        })
        # 应归一化
        self.assertAlmostEqual(cfg.vector_weight + cfg.text_weight, 1.0, places=5)

    def test_missing_fields_use_defaults(self):
        from memory.types import MemoryConfig
        cfg = MemoryConfig.from_dict({"enabled": False})
        self.assertFalse(cfg.enabled)
        self.assertEqual(cfg.chunk_tokens, 400)  # 默认值
        self.assertEqual(cfg.chunk_overlap, 80)

    def test_config_load_save(self):
        import tempfile
        from memory.types import MemoryConfig
        from memory import config as cfg_mod

        tmp = tempfile.mkdtemp()
        old_path = cfg_mod._CONFIG_PATH
        cfg_mod._CONFIG_PATH = Path(tmp) / "test_memory_config.json"
        cfg_mod._cached_config = None
        try:
            # 无文件时用默认值
            c1 = cfg_mod.load_config()
            self.assertTrue(c1.enabled)

            # 保存
            c1.max_results = 20
            cfg_mod.save_config(c1)

            # 重新加载
            cfg_mod._cached_config = None
            c2 = cfg_mod.load_config()
            self.assertEqual(c2.max_results, 20)
        finally:
            cfg_mod._CONFIG_PATH = old_path
            cfg_mod._cached_config = None
            shutil.rmtree(tmp, ignore_errors=True)


class TestMigration(unittest.TestCase):
    """7.1: lessons.json 迁移"""

    def test_migrate_lessons(self):
        tmp = Path(tempfile.mkdtemp())
        db_path = tmp / "migrate_test.sqlite"
        lessons_path = tmp / "lessons.json"

        lessons = [
            {"id": "l1", "trigger": "测试触发", "lesson": "测试教训",
             "source": "test", "category": "general", "tier": "strategy",
             "effectiveness": 0.8, "applied_count": 3},
            {"id": "l2", "trigger": "错误修复", "lesson": "重试前先检查",
             "source": "auto", "category": "error_fix", "tier": "temp"},
        ]
        lessons_path.write_text(json.dumps(lessons), encoding="utf-8")

        from memory.store import MemoryStore
        from memory.migrate import migrate_lessons_to_store
        store = MemoryStore(db_path)
        result = migrate_lessons_to_store(store, lessons_path)

        self.assertEqual(result["migrated"], 2)
        self.assertEqual(result["errors"], 0)
        # strategy tier 应进入 facts collection
        self.assertEqual(store.count("facts"), 1)
        self.assertEqual(store.count("lessons"), 1)

        store.close()
        shutil.rmtree(tmp, ignore_errors=True)

    def test_migrate_empty_file(self):
        tmp = Path(tempfile.mkdtemp())
        db_path = tmp / "empty_test.sqlite"
        lessons_path = tmp / "lessons.json"
        lessons_path.write_text("[]", encoding="utf-8")

        from memory.store import MemoryStore
        from memory.migrate import migrate_lessons_to_store
        store = MemoryStore(db_path)
        result = migrate_lessons_to_store(store, lessons_path)
        self.assertEqual(result["migrated"], 0)

        store.close()
        shutil.rmtree(tmp, ignore_errors=True)

    def test_migrate_no_file(self):
        tmp = Path(tempfile.mkdtemp())
        db_path = tmp / "nofile_test.sqlite"

        from memory.store import MemoryStore
        from memory.migrate import migrate_lessons_to_store
        store = MemoryStore(db_path)
        result = migrate_lessons_to_store(store, tmp / "nonexistent.json")
        self.assertEqual(result["migrated"], 0)

        store.close()
        shutil.rmtree(tmp, ignore_errors=True)


class TestMemorySync(unittest.TestCase):
    """7.2: 同步管理器"""

    def test_track_and_threshold(self):
        from memory.store import MemoryStore
        from memory.sync import MemorySyncManager
        from memory.types import MemoryConfig

        tmp = Path(tempfile.mkdtemp())
        store = MemoryStore(tmp / "sync_test.sqlite")
        cfg = MemoryConfig(sync_delta_messages=3)
        mgr = MemorySyncManager(store, cfg)

        mgr.on_session_start("s1")
        self.assertFalse(mgr.should_sync("s1"))

        for i in range(3):
            mgr.track_message("s1", {"role": "user", "content": f"消息{i}"})

        self.assertTrue(mgr.should_sync("s1"))

        store.close()
        shutil.rmtree(tmp, ignore_errors=True)


class TestCollections(unittest.TestCase):
    """7.3: 集合定义"""

    def test_default_collections(self):
        from memory.types import COLLECTIONS
        self.assertIn("lessons", COLLECTIONS)
        self.assertIn("facts", COLLECTIONS)
        self.assertIn("sessions", COLLECTIONS)
        self.assertIn("skills", COLLECTIONS)
        self.assertGreaterEqual(len(COLLECTIONS), 4)

    def test_cross_collection_search(self):
        tmp = Path(tempfile.mkdtemp())
        from memory.store import MemoryStore
        store = MemoryStore(tmp / "cross.sqlite")
        store.add("lessons", "Python 列表操作经验")
        store.add("facts", "用户精通 Python")
        store.add("skills", "Python 代码运行技巧")

        results = store.search_text("Python")
        collections_found = {r.collection for r in results}
        self.assertGreater(len(collections_found), 1)

        store.close()
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
