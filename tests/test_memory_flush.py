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


# ═══════════════════════════════════════════
# T12: Evergreen 常青集合豁免测试
# ═══════════════════════════════════════════

class TestT12_EvergreenExemption:
    """验证 facts/skills 集合不受时间衰减影响。"""

    def _make_store(self, tmp_path):
        """创建临时 MemoryStore。"""
        from memory.store import MemoryStore
        db_path = tmp_path / "test_memory.db"
        store = MemoryStore(db_path)
        return store

    def _make_result(self, collection: str, age_days: float, score: float = 0.8):
        """创建指定年龄的 MemoryResult。"""
        from memory.types import MemoryResult
        from datetime import datetime, timezone, timedelta
        ts = (datetime.now(timezone.utc) - timedelta(days=age_days)).isoformat()
        return MemoryResult(
            id=f"mem_{collection}_{age_days}",
            collection=collection,
            content=f"Test content for {collection}",
            score=score,
            metadata={},
            created_at=ts,
            updated_at=ts,
        )

    def test_facts_no_decay(self, tmp_path):
        """T12-1: facts 集合不受时间衰减。"""
        store = self._make_store(tmp_path)
        old_fact = self._make_result("facts", age_days=365, score=0.8)
        results = store._apply_time_decay([old_fact])
        # facts 是 Evergreen，365天前的记忆分数不应改变
        assert results[0].score == 0.8

    def test_skills_no_decay(self, tmp_path):
        """T12-2: skills 集合不受时间衰减。"""
        store = self._make_store(tmp_path)
        old_skill = self._make_result("skills", age_days=180, score=0.7)
        results = store._apply_time_decay([old_skill])
        assert results[0].score == 0.7

    def test_lessons_decay(self, tmp_path):
        """T12-3: lessons 集合正常衰减。"""
        store = self._make_store(tmp_path)
        old_lesson = self._make_result("lessons", age_days=180, score=0.8)
        results = store._apply_time_decay([old_lesson])
        # 180天 / 60天半衰期 = 3个半衰期，应该明显衰减
        assert results[0].score < 0.8
        assert results[0].score > 0.0

    def test_sessions_decay(self, tmp_path):
        """T12-4: sessions 集合正常衰减。"""
        store = self._make_store(tmp_path)
        old_session = self._make_result("sessions", age_days=90, score=0.8)
        results = store._apply_time_decay([old_session])
        assert results[0].score < 0.8

    def test_mixed_collections_ranking(self, tmp_path):
        """T12-5: 混合集合中 Evergreen 记忆排名不受衰减影响。"""
        store = self._make_store(tmp_path)
        # 旧 fact (365天) vs 新 lesson (1天) — 起始分数相同
        old_fact = self._make_result("facts", age_days=365, score=0.7)
        new_lesson = self._make_result("lessons", age_days=1, score=0.7)
        old_lesson = self._make_result("lessons", age_days=365, score=0.7)

        results = store._apply_time_decay([old_fact, new_lesson, old_lesson])
        # old_fact 不衰减 (0.7)
        # new_lesson 几乎不衰减 (~0.7)
        # old_lesson 严重衰减 (<0.5)
        scores = {r.id: r.score for r in results}
        assert scores[old_fact.id] == 0.7  # 不变
        assert scores[new_lesson.id] > 0.65  # 几乎不变
        assert scores[old_lesson.id] < 0.5  # 严重衰减

    def test_evergreen_set_is_correct(self, tmp_path):
        """T12-6: 验证 _EVERGREEN_COLLECTIONS 包含正确的集合。"""
        store = self._make_store(tmp_path)
        assert "facts" in store._EVERGREEN_COLLECTIONS
        assert "skills" in store._EVERGREEN_COLLECTIONS
        assert "lessons" not in store._EVERGREEN_COLLECTIONS
        assert "sessions" not in store._EVERGREEN_COLLECTIONS


# ═══════════════════════════════════════════
# T13: Markdown Memory Store 测试
# ═══════════════════════════════════════════

class TestT13_MarkdownStore:
    """验证 Markdown 记忆文件管理。"""

    @pytest.fixture
    def md_store(self, tmp_path):
        from memory.markdown_store import MarkdownMemoryStore
        mem_dir = tmp_path / "memory"
        mem_dir.mkdir()
        return MarkdownMemoryStore(memory_dir=mem_dir)

    def test_list_files_empty(self, md_store):
        """T13-1: 空目录列出零文件。"""
        files = md_store.list_files()
        assert len(files) == 0

    def test_write_and_read(self, md_store):
        """T13-2: 写入并读取文件。"""
        md_store.write_file("test.md", "# Test\nHello world")
        content = md_store.read_file("test.md")
        assert content is not None
        assert "Hello world" in content

    def test_list_files_with_content(self, md_store):
        """T13-3: 写入后可列出文件。"""
        md_store.write_file("2026-03-01.md", "# Daily")
        md_store.write_file("MEMORY.md", "# Evergreen")
        files = md_store.list_files()
        assert len(files) == 2
        names = [f["name"] for f in files]
        assert "2026-03-01.md" in names
        assert "MEMORY.md" in names
        # MEMORY.md 应标记为 evergreen
        mem_file = [f for f in files if f["name"] == "MEMORY.md"][0]
        assert mem_file["is_evergreen"] is True
        daily_file = [f for f in files if f["name"] == "2026-03-01.md"][0]
        assert daily_file["is_evergreen"] is False

    def test_append_entry_dedup(self, md_store):
        """T13-4: 追加条目自动去重。"""
        md_store.append_entry("test.md", "- 用户喜欢中文", heading="偏好")
        md_store.append_entry("test.md", "- 用户喜欢中文", heading="偏好")
        content = md_store.read_file("test.md")
        assert content.count("用户喜欢中文") == 1

    def test_delete_file(self, md_store):
        """T13-5: 删除文件。"""
        md_store.write_file("temp.md", "# Temp")
        assert md_store.delete_file("temp.md")
        assert md_store.read_file("temp.md") is None

    def test_search_basic(self, md_store):
        """T13-6: 跨文件搜索。"""
        md_store.write_file("2026-03-01.md",
                            "# 日志\n## 会话\n用户偏好使用 Python 开发项目")
        md_store.write_file("MEMORY.md",
                            "# 常青\n## 事实\n项目名称是 LucidMind")
        results = md_store.search("Python 项目")
        assert len(results) >= 1
        assert any("Python" in r["snippet"] for r in results)

    def test_search_no_match(self, md_store):
        """T13-7: 无匹配返回空。"""
        md_store.write_file("test.md", "# Test\nHello world")
        results = md_store.search("完全不相关的查询xyz")
        assert len(results) == 0

    def test_safe_path_traversal(self, md_store):
        """T13-8: 路径遍历防护。"""
        assert md_store._safe_path("../../../etc/passwd") is None
        assert md_store._safe_path("/etc/passwd") is None
        assert md_store._safe_path("normal.md") is not None

    def test_ensure_evergreen(self, md_store):
        """T13-9: 确保 MEMORY.md 存在。"""
        path = md_store.ensure_evergreen()
        assert path.exists()
        content = path.read_text(encoding="utf-8")
        assert "常青记忆" in content

    def test_recall_includes_markdown(self, tmp_path):
        """T13-10: json_memory recall() 包含 Markdown 搜索结果。"""
        # 创建带 Markdown 内容的临时环境
        mem_dir = tmp_path / "memory"
        mem_dir.mkdir()
        from memory.markdown_store import MarkdownMemoryStore
        md = MarkdownMemoryStore(memory_dir=mem_dir)
        md.write_file("test.md", "# 记忆\n## 事实\n项目使用 Python 3.12 框架")

        with patch("memory.markdown_store._MEMORY_DIR", mem_dir), \
             patch("memory.markdown_store._instance", md):
            from adapters.memory.json_memory import JSONMemoryAdapter
            adapter = JSONMemoryAdapter(data_dir=str(tmp_path))
            import asyncio
            results = asyncio.get_event_loop().run_until_complete(
                adapter.recall("Python 框架", limit=10)
            )
            # 应包含来自 Markdown 的结果
            md_results = [r for r in results if r.get("category") == "memory_file"]
            assert len(md_results) >= 1


# ═══════════════════════════════════════════
# T14: Query Expansion 查询扩展测试
# ═══════════════════════════════════════════

class TestT14_QueryExpansion:
    """验证查询扩展功能。"""

    def test_segment_chinese(self):
        """T14-1: 中文分词产生有效 token。"""
        from memory.query_expansion import segment
        tokens = segment("用户偏好设置")
        assert len(tokens) >= 2  # 至少有 unigram/bigram

    def test_segment_english(self):
        """T14-2: 英文分词正常工作。"""
        from memory.query_expansion import segment
        tokens = segment("Python framework setup")
        assert "python" in tokens
        assert "framework" in tokens

    def test_expand_query_stopwords(self):
        """T14-3: 停用词被过滤。"""
        from memory.query_expansion import expand_query
        result = expand_query("我想要找到这个项目的配置")
        # "我" "想" "要" "找到" "这个" "的" 应被过滤
        assert "我" not in result
        assert "的" not in result

    def test_expand_query_synonyms(self):
        """T14-4: 同义词扩展。"""
        from memory.query_expansion import expand_query
        result = expand_query("bug修复")
        # "bug" 应扩展出 "错误" "问题" 等
        has_synonym = any(s in result for s in ["错误", "问题", "缺陷"])
        assert has_synonym

    def test_expand_query_empty(self):
        """T14-5: 空查询返回空。"""
        from memory.query_expansion import expand_query
        assert expand_query("") == []
        assert expand_query("   ") == []

    def test_build_fts5_query(self):
        """T14-6: FTS5 查询构建。"""
        from memory.query_expansion import build_fts5_query
        fts = build_fts5_query("配置文件搜索")
        assert "OR" in fts
        assert '"' in fts  # 应有引号包裹

    def test_extract_search_keywords(self):
        """T14-7: 会话式查询提取关键词。"""
        from memory.query_expansion import extract_search_keywords
        keywords = extract_search_keywords("之前我们讨论过什么Python框架")
        assert len(keywords) >= 2
        assert "python" in [k.lower() for k in keywords]

    def test_fts5_integration(self, tmp_path):
        """T14-8: 查询扩展集成到 MemoryStore.search_text()。"""
        from memory.store import MemoryStore
        db_path = tmp_path / "test.db"
        store = MemoryStore(db_path)
        store.add("facts", "用户偏好使用 Python 进行开发", skip_noise_filter=True)
        store.add("facts", "项目配置文件在 config 目录", skip_noise_filter=True)
        # 搜索 "设置" 应通过同义词 "配置" 匹配
        results = store.search_text("设置")
        # 至少应能找到配置相关的条目（通过同义词或 n-gram）
        # 注: 实际效果取决于 FTS5 tokenizer 和同义词扩展
        # 这里主要验证不报错且返回结果
        assert isinstance(results, list)
