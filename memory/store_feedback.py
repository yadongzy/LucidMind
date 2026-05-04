"""Memory Store Feedback Mixin — ACE Bullet 反馈与 Delta 合并。

从 store.py 拆分，包含:
- increment_feedback / get_feedback_score (Phase 8.1)
- merge_deltas / _find_semantic_duplicate / _text_similarity / _prune_harmful (Phase 8.4)
- check_collapse (Phase 8.5)
- backup_jsonl / backfill_embeddings (P0 维护)
"""

import json
from datetime import datetime, timezone
from pathlib import Path

from memory.types import MemoryResult
from logs import get_logger

logger = get_logger("memory.store")


class StoreFeedbackMixin:
    """ACE 反馈 + Delta 合并 + 维护方法集。由 MemoryStore 混入使用。"""

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
                self.add(collection, content, embedding=embedding, metadata=meta,
                         skip_noise_filter=True)
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

    # ── 自动备份 (P0) ──────────────────────────────────────────────

    def backup_jsonl(self, backup_dir: Path | str | None = None,
                     max_backups: int = 7) -> Path | None:
        """将所有记忆导出为 JSONL 备份文件。

        Args:
            backup_dir: 备份目录，默认为 db_path 同级的 backups/
            max_backups: 保留最近 N 个备份文件

        Returns:
            备份文件路径，失败返回 None
        """
        backup_dir = Path(backup_dir) if backup_dir else self.db_path.parent / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        backup_file = backup_dir / f"memory_backup_{timestamp}.jsonl"

        try:
            rows = self.db.execute(
                "SELECT id, collection, content, metadata_json, created_at, updated_at FROM memories"
            ).fetchall()

            with open(backup_file, "w", encoding="utf-8") as f:
                for row in rows:
                    record = {
                        "id": row["id"],
                        "collection": row["collection"],
                        "content": row["content"],
                        "metadata": json.loads(row["metadata_json"]),
                        "created_at": row["created_at"],
                        "updated_at": row["updated_at"],
                    }
                    f.write(json.dumps(record, ensure_ascii=False) + "\n")

            logger.info(f"备份完成: {backup_file} ({len(rows)} 条记忆)")

            # 清理旧备份
            existing = sorted(backup_dir.glob("memory_backup_*.jsonl"))
            if len(existing) > max_backups:
                for old in existing[:-max_backups]:
                    old.unlink()
                    logger.debug(f"清理旧备份: {old.name}")

            return backup_file
        except Exception as e:
            logger.error(f"备份失败: {e}")
            return None

    def backfill_embeddings(self, batch_size: int = 10) -> int:
        """渐进回填缺失的向量 embedding（每次只处理 batch_size 条，适合 cron 调用）。

        Returns:
            本次回填的条数
        """
        if not self._vec_enabled or not self._embed_fn:
            return 0
        try:
            import struct
            existing = set(r[0] for r in self.db.execute("SELECT id FROM memory_vectors").fetchall())
            missing = self.db.execute(
                "SELECT id, content FROM memories ORDER BY created_at DESC"
            ).fetchall()
            filled = 0
            for row in missing:
                if row["id"] in existing:
                    continue
                vec = self._embed_fn(row["content"][:512])
                if vec:
                    blob = struct.pack(f"{len(vec)}f", *vec)
                    self.db.execute("INSERT INTO memory_vectors (id, embedding) VALUES (?,?)",
                                   (row["id"], blob))
                    filled += 1
                if filled >= batch_size:
                    break
            if filled:
                self.db.commit()
                logger.info(f"向量回填: {filled} 条 (剩余 {len(missing) - len(existing) - filled})")
            return filled
        except Exception as e:
            logger.warning(f"向量回填失败: {e}")
            return 0
