"""Memory Flush + Vector Cache 扩容测试 — P0 补齐验证。

测试矩阵:
  T10-1: Memory Flush — LLM 提取写入 Markdown
  T10-2: Memory Flush — LLM 失败时规则回退
  T10-3: Memory Flush — 去重（相同内容不重复写入）
  T10-4: Memory Flush — 空消息跳过
  T10-5: Memory Flush — 写入 MemoryStore 闭环
  T10-6: _smart_compact_history 集成调用 Memory Flush
  T11-1: Vector Cache — SQLite 初始化
  T11-2: Vector Cache — 读写 + LRU 淘汰
  T11-3: Vector Cache — JSON 迁移
"""

import asyncio
import json
import shutil
import sqlite3
import struct
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ═══════════════════════════════════════════
# T10: Memory Flush 测试
# ═══════════════════════════════════════════

class TestT10_MemoryFlush:
    """验证压缩前 Memory Flush 持久化机制。"""

    @pytest.fixture
    def tmp_memory_dir(self, tmp_path):
        """临时 memory 目录。"""
        mem_dir = tmp_path / "data" / "memory"
        mem_dir.mkdir(parents=True)
        return mem_dir

    def _make_brain_mixin(self):
        """创建一个最小的 BrainResilienceMixin 实例。"""
        from brain_resilience import BrainResilienceMixin
        mixin = BrainResilienceMixin.__new__(BrainResilienceMixin)
        mixin.llm = AsyncMock()
        mixin.memory = AsyncMock()
        mixin.stream = AsyncMock()
        mixin._history = []
        return mixin

    @pytest.mark.asyncio
    async def test_flush_llm_extraction(self, tmp_memory_dir):
        """T10-1: LLM 成功提取关键信息并写入 Markdown。"""
        mixin = self._make_brain_mixin()
        mixin.llm.chat = AsyncMock(return_value={
            "content": "- 用户偏好中文回答\n- 项目使用 Python 3.12"
        })
        old_msgs = [
            {"role": "user", "content": "请用中文回答我的问题"},
            {"role": "assistant", "content": "好的，我会用中文回答"},
            {"role": "user", "content": "这个项目用什么语言？"},
            {"role": "assistant", "content": "项目使用 Python 3.12"},
        ]

        with patch("brain_resilience._MEMORY_DIR", tmp_memory_dir):
            await mixin._memory_flush_before_compact("test_session", old_msgs)

        # 验证 Markdown 文件写入
        md_files = list(tmp_memory_dir.glob("*.md"))
        assert len(md_files) == 1
        content = md_files[0].read_text(encoding="utf-8")
        assert "用户偏好中文回答" in content
        assert "Python 3.12" in content

    @pytest.mark.asyncio
    async def test_flush_rule_fallback(self, tmp_memory_dir):
        """T10-2: LLM 失败时回退到规则提取。"""
        mixin = self._make_brain_mixin()
        mixin.llm.chat = AsyncMock(side_effect=Exception("LLM timeout"))
        old_msgs = [
            {"role": "user", "content": "我需要一个待办清单功能"},
            {"role": "assistant", "content": "好的，我来帮你实现"},
        ]

        with patch("brain_resilience._MEMORY_DIR", tmp_memory_dir):
            await mixin._memory_flush_before_compact("test_session", old_msgs)

        md_files = list(tmp_memory_dir.glob("*.md"))
        assert len(md_files) == 1
        content = md_files[0].read_text(encoding="utf-8")
        assert "待办清单" in content

    @pytest.mark.asyncio
    async def test_flush_dedup(self, tmp_memory_dir):
        """T10-3: 相同内容不重复写入。"""
        mixin = self._make_brain_mixin()
        extracted = "- 用户偏好使用中文回答所有问题\n- 项目架构使用 Python"
        mixin.llm.chat = AsyncMock(return_value={"content": extracted})
        old_msgs = [
            {"role": "user", "content": "请用中文回答我所有问题"},
            {"role": "assistant", "content": "好的，我会用中文回答"},
        ]

        with patch("brain_resilience._MEMORY_DIR", tmp_memory_dir):
            await mixin._memory_flush_before_compact("s1", old_msgs)
            await mixin._memory_flush_before_compact("s2", old_msgs)

        md_files = list(tmp_memory_dir.glob("*.md"))
        assert len(md_files) == 1
        content = md_files[0].read_text(encoding="utf-8")
        # 应该只出现一次（去重生效）
        assert content.count("用户偏好使用中文回答所有问题") == 1

    @pytest.mark.asyncio
    async def test_flush_empty_messages(self, tmp_memory_dir):
        """T10-4: 空消息列表不写入。"""
        mixin = self._make_brain_mixin()

        with patch("brain_resilience._MEMORY_DIR", tmp_memory_dir):
            await mixin._memory_flush_before_compact("test", [])
            await mixin._memory_flush_before_compact("test", [
                {"role": "tool", "content": "some tool output"}
            ])

        md_files = list(tmp_memory_dir.glob("*.md"))
        assert len(md_files) == 0

    @pytest.mark.asyncio
    async def test_flush_saves_to_memory_store(self, tmp_memory_dir):
        """T10-5: Flush 同时写入 MemoryStore。"""
        mixin = self._make_brain_mixin()
        mixin.llm.chat = AsyncMock(return_value={
            "content": "- 项目目标是构建AI助手"
        })
        old_msgs = [
            {"role": "user", "content": "我们的项目目标是什么？"},
            {"role": "assistant", "content": "构建一个AI助手"},
        ]

        with patch("brain_resilience._MEMORY_DIR", tmp_memory_dir):
            await mixin._memory_flush_before_compact("test", old_msgs)

        # 验证 memory.save 被调用
        assert mixin.memory.save.called
        call_args = mixin.memory.save.call_args
        assert call_args.kwargs["category"] == "sessions"

    @pytest.mark.asyncio
    async def test_compact_calls_flush(self, tmp_memory_dir):
        """T10-6: _smart_compact_history 在压缩前调用 Memory Flush。"""
        mixin = self._make_brain_mixin()
        mixin.llm.chat = AsyncMock(return_value={
            "content": "对话摘要：讨论了项目架构"
        })
        # 构建足够长的历史触发压缩
        mixin._history = [
            {"role": "user", "content": f"消息 {i} " + "x" * 200}
            for i in range(40)
        ]

        flush_called = []
        original_flush = mixin._memory_flush_before_compact

        async def tracked_flush(sid, msgs):
            flush_called.append(len(msgs))
            # 不实际写文件

        mixin._memory_flush_before_compact = tracked_flush

        await mixin._smart_compact_history("test_session")

        # 验证 flush 被调用且传入了旧消息
        assert len(flush_called) == 1
        assert flush_called[0] > 0


# ═══════════════════════════════════════════
# T11: Vector Cache SQLite 扩容测试
# ═══════════════════════════════════════════

class TestT11_VectorCacheSqlite:
    """验证向量缓存从 JSON 迁移到 SQLite + LRU 淘汰。"""

    @pytest.fixture
    def tmp_data_dir(self, tmp_path):
        """临时 data 目录。"""
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        return data_dir

    def test_sqlite_init(self, tmp_data_dir):
        """T11-1: SQLite 缓存正常初始化。"""
        with patch("adapters.memory.vector_store._DATA_DIR", tmp_data_dir), \
             patch("adapters.memory.vector_store._CACHE_DB_PATH", tmp_data_dir / "test_cache.db"), \
             patch("adapters.memory.vector_store._CACHE_PATH", tmp_data_dir / "old.json"):
            from adapters.memory.vector_store import VectorStore
            store = VectorStore()
            assert store._cache_db is not None
            # 验证表存在
            row = store._cache_db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='embedding_cache'"
            ).fetchone()
            assert row is not None

    def test_cache_read_write(self, tmp_data_dir):
        """T11-2: 向量缓存读写 + LRU 淘汰。"""
        db_path = tmp_data_dir / "test_cache.db"
        with patch("adapters.memory.vector_store._DATA_DIR", tmp_data_dir), \
             patch("adapters.memory.vector_store._CACHE_DB_PATH", db_path), \
             patch("adapters.memory.vector_store._CACHE_PATH", tmp_data_dir / "old.json"):
            from adapters.memory.vector_store import VectorStore
            store = VectorStore()

            # 写入
            vec = [0.1, 0.2, 0.3, 0.4]
            store._cache_put("test_hash_1", vec)
            store._cache_db.commit()

            # 读取
            result = store._cache_get("test_hash_1")
            assert result is not None
            assert len(result) == 4
            assert abs(result[0] - 0.1) < 1e-5

            # 不存在的 key
            assert store._cache_get("nonexistent") is None

    def test_json_migration(self, tmp_data_dir):
        """T11-3: 旧 JSON 缓存自动迁移到 SQLite。"""
        json_path = tmp_data_dir / "embeddings_cache.json"
        db_path = tmp_data_dir / "test_cache.db"

        # 创建旧 JSON 缓存
        old_data = {
            "hash_aaa": [0.1, 0.2, 0.3],
            "hash_bbb": [0.4, 0.5, 0.6],
            "hash_ccc": [0.7, 0.8, 0.9],
        }
        json_path.write_text(json.dumps(old_data), encoding="utf-8")

        with patch("adapters.memory.vector_store._DATA_DIR", tmp_data_dir), \
             patch("adapters.memory.vector_store._CACHE_DB_PATH", db_path), \
             patch("adapters.memory.vector_store._CACHE_PATH", json_path):
            from adapters.memory.vector_store import VectorStore
            store = VectorStore()

            # 验证迁移
            count = store._cache_db.execute(
                "SELECT COUNT(*) FROM embedding_cache"
            ).fetchone()[0]
            assert count == 3

            # 验证可读取迁移的向量
            result = store._cache_get("hash_aaa")
            assert result is not None
            assert len(result) == 3

            # 验证旧文件被重命名
            assert not json_path.exists()
            assert json_path.with_suffix(".json.bak").exists()

    def test_lru_pruning(self, tmp_data_dir):
        """T11-4: LRU 淘汰在超过上限时正确工作。"""
        db_path = tmp_data_dir / "test_cache.db"
        with patch("adapters.memory.vector_store._DATA_DIR", tmp_data_dir), \
             patch("adapters.memory.vector_store._CACHE_DB_PATH", db_path), \
             patch("adapters.memory.vector_store._CACHE_PATH", tmp_data_dir / "old.json"), \
             patch("adapters.memory.vector_store._CACHE_MAX_ENTRIES", 10):
            from adapters.memory.vector_store import VectorStore
            store = VectorStore()

            # 写入超过上限的条目
            import time
            for i in range(15):
                vec = [float(i)] * 4
                h = f"hash_{i:04d}"
                blob = struct.pack(f"4f", *vec)
                store._cache_db.execute(
                    "INSERT OR REPLACE INTO embedding_cache (hash, embedding, dims, accessed_at) VALUES (?,?,?,?)",
                    (h, blob, 4, time.time() - (15 - i)))
            store._cache_db.commit()

            # 触发淘汰
            store._prune_cache()

            count = store._cache_db.execute(
                "SELECT COUNT(*) FROM embedding_cache"
            ).fetchone()[0]
            # 应该淘汰到 80% = 8 条
            assert count == 8

            # 最早的应该被淘汰
            row = store._cache_db.execute(
                "SELECT hash FROM embedding_cache WHERE hash='hash_0000'"
            ).fetchone()
            assert row is None

            # 最新的应该保留
            row = store._cache_db.execute(
                "SELECT hash FROM embedding_cache WHERE hash='hash_0014'"
            ).fetchone()
            assert row is not None
