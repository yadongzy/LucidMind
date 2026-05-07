"""Memory Store — SQLite + FTS5 + 向量存储后端（对标 OpenClaw memory/sqlite.ts）。

支持:
- 集合(Collection)隔离
- FTS5 全文搜索
- 向量相似度搜索（sqlite-vec 可选，无则纯 FTS5）
- 混合搜索（vector_weight + text_weight）
- CRUD 操作

排序管线方法见 store_ranking.py, ACE 反馈/合并方法见 store_feedback.py。
"""

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from memory.types import MemoryResult
from memory.store_ranking import StoreRankingMixin
from memory.store_feedback import StoreFeedbackMixin
from logs import get_logger

logger = get_logger("memory.store")

_VEC_AVAILABLE = False
try:
    import sqlite_vec
    _VEC_AVAILABLE = True
except ImportError:
    logger.info("sqlite-vec 未安装，将仅使用 FTS5 文本搜索")


class MemoryStore(StoreRankingMixin, StoreFeedbackMixin):
    """SQLite + FTS5 + 可选向量存储后端。"""

    def __init__(self, db_path: Path, embedding_dim: int = 768,
                 embed_fn: "Callable[[str], list[float] | None] | None" = None):
        self.db_path = Path(db_path)
        self.embedding_dim = embedding_dim
        self._vec_enabled = _VEC_AVAILABLE
        self._embed_fn = embed_fn
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(self.db_path))
        self.db.row_factory = sqlite3.Row
        self._init_schema()
        logger.info(f"MemoryStore 初始化: {self.db_path} (vec={self._vec_enabled})")

    def _init_schema(self) -> None:
        """创建表结构。"""
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS memories (
                id TEXT PRIMARY KEY,
                collection TEXT NOT NULL DEFAULT 'lessons',
                content TEXT NOT NULL,
                metadata_json TEXT DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_memories_collection ON memories(collection);
            CREATE INDEX IF NOT EXISTS idx_memories_created ON memories(created_at);
        """)
        # FTS5 全文搜索（trigram tokenizer 支持 CJK 子串匹配）
        try:
            self.db.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts
                USING fts5(id, content, collection, tokenize='trigram')
            """)
        except sqlite3.OperationalError:
            try:
                # trigram 不可用时回退到 unicode61
                self.db.execute("""
                    CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts
                    USING fts5(id, content, collection, tokenize='unicode61')
                """)
            except sqlite3.OperationalError:
                logger.warning("FTS5 创建失败，文本搜索将降级")

        # 向量表（sqlite-vec）
        if self._vec_enabled:
            try:
                self.db.enable_load_extension(True)
                sqlite_vec.load(self.db)
                self.db.execute(f"""
                    CREATE VIRTUAL TABLE IF NOT EXISTS memory_vectors
                    USING vec0(id TEXT PRIMARY KEY, embedding float[{self.embedding_dim}])
                """)
            except Exception as e:
                logger.warning(f"sqlite-vec 初始化失败: {e}")
                self._vec_enabled = False

        self.db.commit()

    def add(self, collection: str, content: str, embedding: list[float] | None = None,
            metadata: dict | None = None, skip_noise_filter: bool = False) -> str:
        """添加一条记忆。"""
        if not skip_noise_filter:
            from memory.noise_filter import is_noise
            if is_noise(content):
                logger.info(f"噪声过滤: 跳过存储 ({content[:50]}...)")
                return ""
        mem_id = f"mem_{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc).isoformat()
        meta_json = json.dumps(metadata or {}, ensure_ascii=False)

        self.db.execute(
            "INSERT INTO memories (id, collection, content, metadata_json, created_at, updated_at) VALUES (?,?,?,?,?,?)",
            (mem_id, collection, content, meta_json, now, now)
        )
        # FTS5
        try:
            self.db.execute(
                "INSERT INTO memories_fts (id, content, collection) VALUES (?,?,?)",
                (mem_id, content, collection)
            )
        except Exception:
            pass
        # 向量: 优先用外部传入，否则自动生成
        if self._vec_enabled and not embedding and self._embed_fn:
            try:
                embedding = self._embed_fn(content[:512])
            except Exception as e:
                logger.debug(f"自动 embedding 失败: {e}")
        if self._vec_enabled and embedding:
            try:
                import struct
                blob = struct.pack(f"{len(embedding)}f", *embedding)
                self.db.execute(
                    "INSERT INTO memory_vectors (id, embedding) VALUES (?,?)",
                    (mem_id, blob)
                )
            except Exception as e:
                logger.warning(f"向量写入失败: {e}")

        self.db.commit()
        return mem_id

    def _fts5_query(self, query: str) -> str:
        """将用户查询转换为 FTS5 兼容的查询语法（增强版: 分词+同义词扩展）。"""
        try:
            from memory.query_expansion import build_fts5_query
            return build_fts5_query(query)
        except Exception:
            # 回退到基础实现
            import re
            cleaned = re.sub(r'[^\w\s]', ' ', query)
            terms = [t.strip() for t in cleaned.split() if t.strip()]
            if not terms:
                return query
            return " OR ".join(f'"{t}"' for t in terms)

    def search_text(self, query: str, collection: str | None = None,
                    limit: int = 6) -> list[MemoryResult]:
        """FTS5 全文搜索。"""
        results = []
        fts_query = self._fts5_query(query)
        try:
            if collection:
                rows = self.db.execute("""
                    SELECT f.id, f.content, f.collection, rank
                    FROM memories_fts f
                    WHERE memories_fts MATCH ? AND f.collection = ?
                    ORDER BY rank
                    LIMIT ?
                """, (fts_query, collection, limit)).fetchall()
            else:
                rows = self.db.execute("""
                    SELECT f.id, f.content, f.collection, rank
                    FROM memories_fts f
                    WHERE memories_fts MATCH ?
                    ORDER BY rank
                    LIMIT ?
                """, (fts_query, limit)).fetchall()

            for row in rows:
                # FTS5 rank is negative (more negative = better match)
                score = 1.0 / (1.0 + abs(row["rank"]))
                meta_row = self.db.execute(
                    "SELECT metadata_json, created_at, updated_at FROM memories WHERE id=?",
                    (row["id"],)
                ).fetchone()
                results.append(MemoryResult(
                    id=row["id"],
                    collection=row["collection"],
                    content=row["content"],
                    score=score,
                    metadata=json.loads(meta_row["metadata_json"]) if meta_row else {},
                    created_at=meta_row["created_at"] if meta_row else "",
                    updated_at=meta_row["updated_at"] if meta_row else "",
                ))
        except Exception as e:
            logger.debug(f"FTS5 搜索异常: {e}")
        # FTS5 无结果时降级到 LIKE 搜索（CJK 兼容）
        if not results:
            results = self._fallback_search(query, collection, limit)
        return results

    def _fallback_search(self, query: str, collection: str | None,
                         limit: int) -> list[MemoryResult]:
        """降级搜索: 使用 LIKE 模糊匹配（多词 OR，支持 CJK 分词）。"""
        terms = [t.strip() for t in query.split() if t.strip()]
        # CJK 文本无空格时用 segment 分词
        if len(terms) <= 1 and len(query) >= 2:
            try:
                from memory.query_expansion import segment
                seg_terms = [t for t in segment(query) if len(t) >= 2]
                if seg_terms:
                    terms = seg_terms
            except Exception:
                pass
        if not terms:
            terms = [query]
        like_clauses = " OR ".join(["content LIKE ?"] * len(terms))
        params: list[Any] = [f"%{t}%" for t in terms]
        sql = f"SELECT * FROM memories WHERE ({like_clauses})"
        if collection:
            sql += " AND collection = ?"
            params.append(collection)
        sql += " ORDER BY updated_at DESC LIMIT ?"
        params.append(limit)

        results = []
        for row in self.db.execute(sql, params).fetchall():
            results.append(MemoryResult(
                id=row["id"],
                collection=row["collection"],
                content=row["content"],
                score=0.5,
                metadata=json.loads(row["metadata_json"]),
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            ))
        return results

    def search_vector(self, embedding: list[float], collection: str | None = None,
                      limit: int = 6, min_score: float = 0.0) -> list[MemoryResult]:
        """向量相似度搜索（需要 sqlite-vec）。"""
        if not self._vec_enabled or not embedding:
            return []
        try:
            import struct
            blob = struct.pack(f"{len(embedding)}f", *embedding)
            rows = self.db.execute("""
                SELECT v.id, v.distance
                FROM memory_vectors v
                WHERE v.embedding MATCH ?
                ORDER BY v.distance
                LIMIT ?
            """, (blob, limit * 3)).fetchall()  # 多取一些用于后续过滤

            results = []
            for row in rows:
                # distance → score (cosine: 0=identical, 2=opposite)
                score = 1.0 - (row["distance"] / 2.0)
                if score < min_score:
                    continue
                mem_row = self.db.execute(
                    "SELECT * FROM memories WHERE id=?", (row["id"],)
                ).fetchone()
                if not mem_row:
                    continue
                if collection and mem_row["collection"] != collection:
                    continue
                results.append(MemoryResult(
                    id=mem_row["id"],
                    collection=mem_row["collection"],
                    content=mem_row["content"],
                    score=score,
                    metadata=json.loads(mem_row["metadata_json"]),
                    created_at=mem_row["created_at"],
                    updated_at=mem_row["updated_at"],
                ))
                if len(results) >= limit:
                    break
            return results
        except Exception as e:
            logger.warning(f"向量搜索失败: {e}")
            return []

    # ── Multi-Stage Retrieval Pipeline ──
    # 管线参数 & 排序方法定义在 StoreRankingMixin (store_ranking.py)

    def search_hybrid(self, query_text: str, query_embedding: list[float] | None = None,
                      collection: str | None = None,
                      vector_weight: float = 0.7, text_weight: float = 0.3,
                      limit: int = 6, min_score: float = 0.35) -> list[MemoryResult]:
        """Multi-Stage Hybrid Retrieval Pipeline.

        管线阶段:
        0. 自适应跳过: 简单问候/命令直接返回空
        1. 并行检索: Vector Search + FTS5 BM25
        2. RRF 融合: 向量分数为基底，FTS5 命中给 15% 加成
        3. Recency Boost: 新记忆加分 (指数衰减 + 加性)
        4. Importance Weight: 按 helpful/harmful 反馈调权
        5. Length Normalization: 惩罚过长条目
        6. Time Decay: 乘性惩罚旧条目
        7. Hard Min Score: 最终过滤
        8. MMR Diversity: 去重近似条目
        """
        # Stage 0: 自适应跳过
        from memory.noise_filter import should_skip_retrieval
        if should_skip_retrieval(query_text):
            logger.debug(f"自适应跳过检索: {query_text[:40]}")
            return []

        candidate_pool = max(limit * 4, 20)

        # Stage 1: 并行检索
        text_results = self.search_text(query_text, collection, limit=candidate_pool)
        vec_results = []
        if not query_embedding and self._vec_enabled and self._embed_fn:
            try:
                query_embedding = self._embed_fn(query_text[:512])
            except Exception as e:
                logger.debug(f"查询 embedding 失败: {e}")
        if query_embedding and self._vec_enabled:
            vec_results = self.search_vector(query_embedding, collection,
                                             limit=candidate_pool, min_score=0.1)

        # Stage 2: RRF-style 融合
        fused = self._fuse_results(text_results, vec_results, vector_weight, text_weight)

        # 软阈值初筛
        fused = [r for r in fused if r.score >= min_score * 0.5]

        # Stage 3: Recency Boost
        fused = self._apply_recency_boost(fused)

        # Stage 4: Importance Weight (ACE 反馈)
        fused = self._apply_importance_weight(fused)

        # Stage 5: Length Normalization
        fused = self._apply_length_normalization(fused)

        # Stage 6: Time Decay
        fused = self._apply_time_decay(fused)

        # Stage 7: Hard Min Score
        fused = [r for r in fused if r.score >= max(min_score, self._HARD_MIN_SCORE)]

        # Stage 8: MMR Diversity
        fused = self._apply_mmr_diversity(fused)

        # Stage 9: Version Filter — 过滤被 superseded 和 dormant 的记忆
        fused = [r for r in fused
                 if not r.metadata.get("superseded_by")
                 and not r.metadata.get("dormant")]

        return fused[:limit]

    def delete(self, memory_id: str) -> bool:
        """删除一条记忆。"""
        cur = self.db.execute("DELETE FROM memories WHERE id=?", (memory_id,))
        try:
            self.db.execute("DELETE FROM memories_fts WHERE id=?", (memory_id,))
        except Exception:
            pass
        if self._vec_enabled:
            try:
                self.db.execute("DELETE FROM memory_vectors WHERE id=?", (memory_id,))
            except Exception:
                pass
        self.db.commit()
        return cur.rowcount > 0

    def update(self, memory_id: str, content: str | None = None,
               embedding: list[float] | None = None,
               metadata: dict | None = None) -> bool:
        """更新一条记忆。"""
        now = datetime.now(timezone.utc).isoformat()
        updates = ["updated_at=?"]
        params: list[Any] = [now]
        if content is not None:
            updates.append("content=?")
            params.append(content)
        if metadata is not None:
            updates.append("metadata_json=?")
            params.append(json.dumps(metadata, ensure_ascii=False))
        params.append(memory_id)

        cur = self.db.execute(
            f"UPDATE memories SET {','.join(updates)} WHERE id=?", params
        )
        if content is not None:
            try:
                self.db.execute("DELETE FROM memories_fts WHERE id=?", (memory_id,))
                row = self.db.execute("SELECT collection FROM memories WHERE id=?", (memory_id,)).fetchone()
                if row:
                    self.db.execute(
                        "INSERT INTO memories_fts (id, content, collection) VALUES (?,?,?)",
                        (memory_id, content, row["collection"])
                    )
            except Exception:
                pass
        if embedding and self._vec_enabled:
            try:
                import struct
                blob = struct.pack(f"{len(embedding)}f", *embedding)
                self.db.execute("DELETE FROM memory_vectors WHERE id=?", (memory_id,))
                self.db.execute(
                    "INSERT INTO memory_vectors (id, embedding) VALUES (?,?)",
                    (memory_id, blob)
                )
            except Exception:
                pass
        self.db.commit()
        return cur.rowcount > 0

    def count(self, collection: str | None = None) -> int:
        """统计记忆数量。"""
        if collection:
            row = self.db.execute(
                "SELECT COUNT(*) as cnt FROM memories WHERE collection=?", (collection,)
            ).fetchone()
        else:
            row = self.db.execute("SELECT COUNT(*) as cnt FROM memories").fetchone()
        return row["cnt"] if row else 0

    def list_collections(self) -> dict[str, int]:
        """列出所有集合及其记忆数量。"""
        rows = self.db.execute(
            "SELECT collection, COUNT(*) as cnt FROM memories GROUP BY collection"
        ).fetchall()
        return {row["collection"]: row["cnt"] for row in rows}

    def get_all(self, collection: str | None = None, limit: int = 100,
                offset: int = 0) -> list[MemoryResult]:
        """获取所有记忆（分页）。"""
        if collection:
            rows = self.db.execute(
                "SELECT * FROM memories WHERE collection=? ORDER BY updated_at DESC LIMIT ? OFFSET ?",
                (collection, limit, offset)
            ).fetchall()
        else:
            rows = self.db.execute(
                "SELECT * FROM memories ORDER BY updated_at DESC LIMIT ? OFFSET ?",
                (limit, offset)
            ).fetchall()
        return [
            MemoryResult(
                id=row["id"], collection=row["collection"], content=row["content"],
                metadata=json.loads(row["metadata_json"]),
                created_at=row["created_at"], updated_at=row["updated_at"],
            )
            for row in rows
        ]

    # ── ACE 反馈/合并/备份方法定义在 StoreFeedbackMixin (store_feedback.py) ──

    def close(self) -> None:
        """关闭数据库连接。"""
        try:
            self.db.close()
        except Exception:
            pass
