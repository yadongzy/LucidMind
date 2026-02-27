"""Memory Store — SQLite + FTS5 + 向量存储后端（对标 OpenClaw memory/sqlite.ts）。

支持:
- 集合(Collection)隔离
- FTS5 全文搜索
- 向量相似度搜索（sqlite-vec 可选，无则纯 FTS5）
- 混合搜索（vector_weight + text_weight）
- CRUD 操作
"""

import json
import math
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from memory.types import MemoryResult
from logs import get_logger

logger = get_logger("memory.store")

_VEC_AVAILABLE = False
try:
    import sqlite_vec
    _VEC_AVAILABLE = True
except ImportError:
    logger.info("sqlite-vec 未安装，将仅使用 FTS5 文本搜索")


class MemoryStore:
    """SQLite + FTS5 + 可选向量存储后端。"""

    def __init__(self, db_path: Path, embedding_dim: int = 768):
        self.db_path = Path(db_path)
        self.embedding_dim = embedding_dim
        self._vec_enabled = _VEC_AVAILABLE
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
            metadata: dict | None = None) -> str:
        """添加一条记忆。"""
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
        # 向量
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
        """将用户查询转换为 FTS5 兼容的查询语法。"""
        # 去除 FTS5 特殊字符，拆分为词，用 OR 连接
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
        """降级搜索: 使用 LIKE 模糊匹配（多词 OR）。"""
        terms = [t.strip() for t in query.split() if t.strip()]
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

    # ── Multi-Stage Retrieval Pipeline (对标 memory-lancedb-pro) ──

    # 管线参数
    _RECENCY_HALF_LIFE_DAYS = 14    # 新鲜度加成半衰期
    _RECENCY_WEIGHT = 0.10          # 新鲜度加成权重上限
    _TIME_DECAY_HALF_LIFE_DAYS = 60 # 时间衰减半衰期
    _LENGTH_NORM_ANCHOR = 500       # 长度归一化锚点（字符数）
    _HARD_MIN_SCORE = 0.20          # 最终硬过滤阈值
    _MMR_SIMILARITY_THRESHOLD = 0.85 # MMR 去重相似度阈值

    def search_hybrid(self, query_text: str, query_embedding: list[float] | None = None,
                      collection: str | None = None,
                      vector_weight: float = 0.7, text_weight: float = 0.3,
                      limit: int = 6, min_score: float = 0.35) -> list[MemoryResult]:
        """Multi-Stage Hybrid Retrieval Pipeline.

        管线阶段:
        1. 并行检索: Vector Search + FTS5 BM25
        2. RRF 融合: 向量分数为基底，FTS5 命中给 15% 加成
        3. Recency Boost: 新记忆加分 (指数衰减 + 加性)
        4. Importance Weight: 按 helpful/harmful 反馈调权
        5. Length Normalization: 惩罚过长条目
        6. Time Decay: 乘性惩罚旧条目
        7. Hard Min Score: 最终过滤
        8. MMR Diversity: 去重近似条目
        """
        candidate_pool = max(limit * 4, 20)

        # Stage 1: 并行检索
        text_results = self.search_text(query_text, collection, limit=candidate_pool)
        vec_results = []
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

        return fused[:limit]

    def _fuse_results(self, text_results: list[MemoryResult],
                      vec_results: list[MemoryResult],
                      vector_weight: float, text_weight: float) -> list[MemoryResult]:
        """RRF-style 融合: 向量分数为基底，FTS5 命中给加成。"""
        vec_map: dict[str, MemoryResult] = {r.id: r for r in vec_results}
        text_map: dict[str, MemoryResult] = {r.id: r for r in text_results}
        all_ids = set(vec_map.keys()) | set(text_map.keys())

        fused: list[MemoryResult] = []
        for mid in all_ids:
            v = vec_map.get(mid)
            t = text_map.get(mid)
            base = v or t
            assert base is not None

            if v and t:
                # 向量分数为基底，FTS5 命中给 15% 加成（对标 memory-lancedb-pro）
                score = min(1.0, v.score + 0.15 * v.score)
            elif v:
                score = v.score
            else:
                # 纯 FTS5 命中，给底分 0.5 保底（关键词精确匹配不应被埋没）
                score = max(t.score, 0.5) if t else 0.3

            fused.append(MemoryResult(
                id=base.id, collection=base.collection, content=base.content,
                score=score, metadata=base.metadata,
                created_at=base.created_at, updated_at=base.updated_at,
            ))

        fused.sort(key=lambda r: r.score, reverse=True)
        return fused

    def _apply_recency_boost(self, results: list[MemoryResult]) -> list[MemoryResult]:
        """新鲜度加成: 新记忆获得小幅加分，确保纠正/更新自然排在旧条目前面。

        Formula: boost = exp(-ageDays / halfLife) * weight
        """
        if not self._RECENCY_HALF_LIFE_DAYS or not self._RECENCY_WEIGHT:
            return results

        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)

        for r in results:
            age_days = self._calc_age_days(r, now)
            boost = math.exp(-age_days / self._RECENCY_HALF_LIFE_DAYS) * self._RECENCY_WEIGHT
            r.score = min(1.0, r.score + boost)

        results.sort(key=lambda r: r.score, reverse=True)
        return results

    def _apply_importance_weight(self, results: list[MemoryResult]) -> list[MemoryResult]:
        """按 ACE 反馈权重调整: helpful 多的记忆加权，harmful 多的降权。

        Formula: score *= (0.7 + 0.3 * importance)
        importance = clamp(0.5 + 0.1 * net_feedback, 0, 1)
        """
        for r in results:
            helpful = r.metadata.get("helpful_count", 0)
            harmful = r.metadata.get("harmful_count", 0)
            net = helpful - harmful
            importance = max(0.0, min(1.0, 0.5 + 0.1 * net))
            factor = 0.7 + 0.3 * importance
            r.score = min(1.0, r.score * factor)

        results.sort(key=lambda r: r.score, reverse=True)
        return results

    def _apply_length_normalization(self, results: list[MemoryResult]) -> list[MemoryResult]:
        """长度归一化: 防止长条目靠关键词密度霸占搜索结果。

        Formula: score *= 1 / (1 + 0.5 * log2(max(charLen/anchor, 1)))
        """
        anchor = self._LENGTH_NORM_ANCHOR
        if anchor <= 0:
            return results

        for r in results:
            char_len = len(r.content)
            ratio = char_len / anchor
            log_ratio = math.log2(max(ratio, 1.0))
            factor = 1.0 / (1.0 + 0.5 * log_ratio)
            r.score = max(0.0, r.score * factor)

        results.sort(key=lambda r: r.score, reverse=True)
        return results

    def _apply_time_decay(self, results: list[MemoryResult]) -> list[MemoryResult]:
        """时间衰减: 乘性惩罚旧条目。不同于 recency_boost（加性奖励新条目）。

        Formula: score *= 0.5 + 0.5 * exp(-ageDays / halfLife)
        Floor at 0.5x (永远不会惩罚超过一半)
        """
        half_life = self._TIME_DECAY_HALF_LIFE_DAYS
        if half_life <= 0:
            return results

        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)

        for r in results:
            age_days = self._calc_age_days(r, now)
            factor = 0.5 + 0.5 * math.exp(-age_days / half_life)
            r.score = max(0.0, r.score * factor)

        results.sort(key=lambda r: r.score, reverse=True)
        return results

    def _apply_mmr_diversity(self, results: list[MemoryResult]) -> list[MemoryResult]:
        """MMR 多样性去重: 相似度 > threshold 的条目被延后排列。

        使用 bigram Jaccard 文本相似度（不需要向量）。
        """
        if len(results) <= 1:
            return results

        selected: list[MemoryResult] = []
        deferred: list[MemoryResult] = []

        for candidate in results:
            too_similar = any(
                self._text_similarity(candidate.content, s.content) > self._MMR_SIMILARITY_THRESHOLD
                for s in selected
            )
            if too_similar:
                deferred.append(candidate)
            else:
                selected.append(candidate)

        return selected + deferred

    def _calc_age_days(self, r: MemoryResult, now) -> float:
        """计算记忆条目的年龄（天数）。"""
        from datetime import datetime, timezone
        ts_str = r.updated_at or r.created_at
        if not ts_str:
            return 30.0  # 默认 30 天
        try:
            ts = datetime.fromisoformat(ts_str)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            delta = now - ts
            return max(0.0, delta.total_seconds() / 86400.0)
        except (ValueError, TypeError):
            return 30.0

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

    # ── ACE Bullet 反馈机制 (Phase 8.1) ──────────────────────────

    def increment_feedback(self, memory_id: str, feedback_type: str) -> bool:
        """ACE Bullet: 递增 helpful_count 或 harmful_count 计数器。

        Args:
            memory_id: 记忆条目 ID
            feedback_type: "helpful" 或 "harmful"
        Returns:
            是否成功更新
        """
        if feedback_type not in ("helpful", "harmful"):
            logger.warning(f"无效的反馈类型: {feedback_type}")
            return False
        row = self.db.execute(
            "SELECT metadata_json FROM memories WHERE id=?", (memory_id,)
        ).fetchone()
        if not row:
            return False
        meta = json.loads(row["metadata_json"])
        key = f"{feedback_type}_count"
        meta[key] = meta.get(key, 0) + 1
        now = datetime.now(timezone.utc).isoformat()
        self.db.execute(
            "UPDATE memories SET metadata_json=?, updated_at=? WHERE id=?",
            (json.dumps(meta, ensure_ascii=False), now, memory_id)
        )
        self.db.commit()
        return True

    def get_feedback_score(self, memory_id: str) -> float:
        """ACE Bullet: 计算反馈净分 = helpful - harmful。"""
        row = self.db.execute(
            "SELECT metadata_json FROM memories WHERE id=?", (memory_id,)
        ).fetchone()
        if not row:
            return 0.0
        meta = json.loads(row["metadata_json"])
        return meta.get("helpful_count", 0) - meta.get("harmful_count", 0)

    # ── ACE Delta 合并 (Phase 8.4) ────────────────────────────────

    def merge_deltas(self, deltas: list[dict], collection: str = "lessons",
                     dedup_threshold: float = 0.85) -> dict:
        """ACE Curator: 确定性合并 delta bullets 到记忆库。

        每个 delta: {"content": str, "metadata": dict, "embedding": list|None}

        - 新条目 → 追加
        - 语义重复（文本相似度 > threshold）→ 更新计数器 + 合并 source_sessions
        - harmful_count > helpful_count 的条目被降权清理

        Returns:
            {"appended": int, "merged": int, "pruned": int}
        """
        snapshot_before = self.count(collection)
        appended = 0
        merged = 0
        pruned = 0

        for delta in deltas:
            content = delta.get("content", "").strip()
            if not content:
                continue
            meta = delta.get("metadata", {})
            embedding = delta.get("embedding")

            # 查找语义重复
            dup = self._find_semantic_duplicate(content, collection, dedup_threshold)
            if dup:
                # 合并到已有条目
                existing_meta = dup.metadata
                existing_meta["helpful_count"] = existing_meta.get("helpful_count", 0) + meta.get("helpful_count", 0)
                existing_meta["harmful_count"] = existing_meta.get("harmful_count", 0) + meta.get("harmful_count", 0)
                # 合并 source_sessions
                existing_sessions = set(existing_meta.get("source_sessions", []))
                new_sessions = meta.get("source_sessions", [])
                if meta.get("source_session"):
                    new_sessions.append(meta["source_session"])
                existing_sessions.update(new_sessions)
                existing_meta["source_sessions"] = list(existing_sessions)[-20:]  # 保留最近 20 个
                self.update(dup.id, metadata=existing_meta)
                merged += 1
            else:
                # 新条目追加
                meta.setdefault("helpful_count", 0)
                meta.setdefault("harmful_count", 0)
                meta.setdefault("source_sessions", [])
                if meta.get("source_session"):
                    meta["source_sessions"].append(meta["source_session"])
                self.add(collection, content, embedding=embedding, metadata=meta)
                appended += 1

        # Prune: 清理 harmful > helpful 的条目
        pruned = self._prune_harmful(collection)

        # Collapse 检测
        self._last_merge_snapshot = {
            "before": snapshot_before,
            "after": self.count(collection),
            "appended": appended,
            "merged": merged,
            "pruned": pruned,
        }

        result = {"appended": appended, "merged": merged, "pruned": pruned}
        logger.info(f"ACE merge_deltas: {result}")
        return result

    def _find_semantic_duplicate(self, content: str, collection: str,
                                  threshold: float) -> MemoryResult | None:
        """在指定集合中查找与 content 语义重复的条目。

        使用文本相似度（Jaccard + 子串匹配）作为轻量判断，无需向量。
        """
        existing = self.get_all(collection=collection, limit=500)
        best_match = None
        best_score = 0.0
        for entry in existing:
            sim = self._text_similarity(content, entry.content)
            if sim > best_score:
                best_score = sim
                best_match = entry
        if best_score >= threshold:
            return best_match
        return None

    @staticmethod
    def _text_similarity(a: str, b: str) -> float:
        """轻量文本相似度: 结合 Jaccard 字符 bigram 与长度比。"""
        if not a or not b:
            return 0.0
        # 完全相同
        if a.strip() == b.strip():
            return 1.0
        # Bigram Jaccard
        def bigrams(s: str) -> set:
            s = s.lower().strip()
            return {s[i:i+2] for i in range(len(s) - 1)} if len(s) >= 2 else {s}
        bg_a = bigrams(a)
        bg_b = bigrams(b)
        if not bg_a or not bg_b:
            return 0.0
        intersection = len(bg_a & bg_b)
        union = len(bg_a | bg_b)
        jaccard = intersection / union if union > 0 else 0.0
        # 长度惩罚（长度差异大时降权）
        len_ratio = min(len(a), len(b)) / max(len(a), len(b))
        return jaccard * 0.7 + len_ratio * 0.3

    def _prune_harmful(self, collection: str) -> int:
        """清理 harmful_count > helpful_count 的条目。"""
        rows = self.db.execute(
            "SELECT id, metadata_json FROM memories WHERE collection=?", (collection,)
        ).fetchall()
        pruned = 0
        for row in rows:
            meta = json.loads(row["metadata_json"])
            helpful = meta.get("helpful_count", 0)
            harmful = meta.get("harmful_count", 0)
            if harmful > helpful and harmful >= 3:
                self.delete(row["id"])
                pruned += 1
                logger.info(f"ACE prune: {row['id']} (helpful={helpful}, harmful={harmful})")
        return pruned

    # ── ACE Collapse 检测 (Phase 8.5) ─────────────────────────────

    def check_collapse(self, collection: str | None = None) -> dict:
        """检测记忆库是否出现 context collapse（信息骤降）。

        Returns:
            {"collapsed": bool, "before_count": int, "after_count": int, "drop_pct": float}
        """
        snapshot = getattr(self, "_last_merge_snapshot", None)
        if not snapshot:
            current = self.count(collection)
            return {"collapsed": False, "before_count": current, "after_count": current, "drop_pct": 0.0}

        before = snapshot.get("before", 0)
        after = snapshot.get("after", 0)
        if before == 0:
            return {"collapsed": False, "before_count": before, "after_count": after, "drop_pct": 0.0}
        drop_pct = (before - after) / before if after < before else 0.0
        collapsed = drop_pct > 0.5
        if collapsed:
            logger.warning(f"⚠️ Context collapse 检测: {before} → {after} (下降 {drop_pct:.1%})")
        return {"collapsed": collapsed, "before_count": before, "after_count": after, "drop_pct": drop_pct}

    def close(self) -> None:
        """关闭数据库连接。"""
        try:
            self.db.close()
        except Exception:
            pass
