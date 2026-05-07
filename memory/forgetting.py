"""Active Forgetting — 主动遗忘与冲突解决机制。

防止记忆污染的三道防线:
1. forget_stale() — 90天未检索标记 dormant，180天永久删除
2. resolve_conflict() — 同主题冲突检测，标记旧版本 superseded
3. merge_similar() — 同主题最多保留 3 条，合并其余

设计原则:
- 遗忘是主动的、有策略的，不是被动淘汰
- 冲突解决优先保留最新（keep_latest）
- 所有操作可审计（记录遗忘原因）
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Any, TYPE_CHECKING

from logs import get_logger

if TYPE_CHECKING:
    from memory.store import MemoryStore

logger = get_logger("memory.forgetting")

# ── 配置常量 ─────────────────────────────────────────────────
STALE_DAYS = 90              # 未被检索天数 → dormant
DORMANT_CLEANUP_DAYS = 180   # dormant 状态天数 → 永久删除
HARMFUL_THRESHOLD = 3        # harmful_count ≥ 此值 → 删除
MAX_SIMILAR_PER_TOPIC = 3    # 同主题最多保留条数
CONFLICT_SIMILARITY = 0.75   # 冲突检测相似度阈值


class ForgettingEngine:
    """主动遗忘引擎。定期运行清理记忆库。"""

    def __init__(self, store: "MemoryStore"):
        self.store = store
        self._stats = {"stale": 0, "harmful": 0, "merged": 0, "conflicts": 0}

    def run_full_cleanup(self, collection: str = "lessons") -> dict:
        """执行完整清理流程。

        Returns:
            {"stale_marked": int, "stale_deleted": int, "harmful_deleted": int,
             "conflicts_resolved": int, "merged": int}
        """
        results = {
            "stale_marked": 0,
            "stale_deleted": 0,
            "harmful_deleted": 0,
            "conflicts_resolved": 0,
            "merged": 0,
        }

        results["stale_marked"], results["stale_deleted"] = self.forget_stale(collection)
        results["harmful_deleted"] = self.forget_harmful(collection)
        results["conflicts_resolved"] = self.resolve_conflicts(collection)
        results["merged"] = self.merge_similar(collection)

        total = sum(results.values())
        if total > 0:
            logger.info(f"遗忘引擎清理完成: {results}")
        return results

    def forget_stale(self, collection: str = "lessons") -> tuple[int, int]:
        """标记/删除过期记忆。

        Returns:
            (marked_dormant, permanently_deleted)
        """
        now = datetime.now(timezone.utc)
        marked = 0
        deleted = 0

        try:
            rows = self.store.db.execute(
                "SELECT id, metadata_json, updated_at FROM memories WHERE collection=?",
                (collection,)
            ).fetchall()
        except Exception as e:
            logger.warning(f"forget_stale 查询失败: {e}")
            return 0, 0

        for row in rows:
            meta = json.loads(row["metadata_json"] or "{}")

            # 计算年龄
            age_days = self._calc_age_days(row["updated_at"], now)

            # 跳过常青记忆
            if meta.get("evergreen"):
                continue

            # 已标记 dormant 的检查是否该删除
            if meta.get("dormant"):
                dormant_since = meta.get("dormant_since", 0)
                dormant_days = (time.time() - dormant_since) / 86400 if dormant_since else age_days
                if dormant_days >= DORMANT_CLEANUP_DAYS:
                    self.store.delete(row["id"])
                    deleted += 1
                    logger.debug(f"永久删除 dormant 记忆: {row['id']}")
                continue

            # 检查是否该标记 dormant
            last_accessed = meta.get("last_accessed", 0)
            if last_accessed:
                access_age = (time.time() - last_accessed) / 86400
            else:
                access_age = age_days

            if access_age >= STALE_DAYS:
                meta["dormant"] = True
                meta["dormant_since"] = time.time()
                meta["dormant_reason"] = f"{int(access_age)}天未被检索"
                self.store.update(row["id"], metadata=meta)
                marked += 1

        return marked, deleted

    def forget_harmful(self, collection: str = "lessons") -> int:
        """删除 harmful 超标的记忆。"""
        deleted = 0
        try:
            rows = self.store.db.execute(
                "SELECT id, metadata_json FROM memories WHERE collection=?",
                (collection,)
            ).fetchall()
        except Exception:
            return 0

        for row in rows:
            meta = json.loads(row["metadata_json"] or "{}")
            harmful = meta.get("harmful_count", 0)
            helpful = meta.get("helpful_count", 0)
            if harmful >= HARMFUL_THRESHOLD and harmful > helpful:
                self.store.delete(row["id"])
                deleted += 1
                logger.info(f"删除有害记忆: {row['id']} (harmful={harmful})")

        return deleted

    def resolve_conflicts(self, collection: str = "lessons") -> int:
        """检测同主题冲突记忆，标记旧版本为 superseded。"""
        resolved = 0
        try:
            all_memories = self.store.get_all(collection=collection, limit=1000)
        except Exception:
            return 0

        if len(all_memories) < 2:
            return 0

        # 按内容分组检测冲突
        seen = []  # (id, content, updated_at)
        for mem in all_memories:
            for prev_id, prev_content, prev_updated in seen:
                sim = self.store._text_similarity(mem.content, prev_content)
                if CONFLICT_SIMILARITY <= sim < 0.85:
                    # 相似但不完全相同 → 可能是同主题的更新版本
                    # 保留更新的，标记旧的
                    mem_time = mem.updated_at or mem.created_at or ""
                    if mem_time > prev_updated:
                        # mem 更新 → 标记 prev 为 superseded
                        self._mark_superseded(prev_id, mem.id)
                    else:
                        self._mark_superseded(mem.id, prev_id)
                    resolved += 1
                    break
            seen.append((mem.id, mem.content, mem.updated_at or mem.created_at or ""))

        return resolved

    def merge_similar(self, collection: str = "lessons") -> int:
        """同主题超过 MAX_SIMILAR_PER_TOPIC 条时合并。"""
        merged = 0
        try:
            all_memories = self.store.get_all(collection=collection, limit=1000)
        except Exception:
            return 0

        if len(all_memories) <= MAX_SIMILAR_PER_TOPIC:
            return 0

        # 按相似度聚类
        clusters: list[list] = []
        for mem in all_memories:
            placed = False
            for cluster in clusters:
                rep = cluster[0]
                sim = self.store._text_similarity(mem.content, rep.content)
                if sim >= 0.7:
                    cluster.append(mem)
                    placed = True
                    break
            if not placed:
                clusters.append([mem])

        # 超限的聚类：保留最新的 N 条，删除其余
        for cluster in clusters:
            if len(cluster) <= MAX_SIMILAR_PER_TOPIC:
                continue
            # 按更新时间排序，保留最新
            cluster.sort(key=lambda m: m.updated_at or m.created_at or "", reverse=True)
            to_remove = cluster[MAX_SIMILAR_PER_TOPIC:]
            for mem in to_remove:
                self.store.delete(mem.id)
                merged += 1
                logger.debug(f"合并删除: {mem.id} (同主题超限)")

        return merged

    def _mark_superseded(self, old_id: str, new_id: str) -> None:
        """标记旧记忆为被取代。"""
        try:
            row = self.store.db.execute(
                "SELECT metadata_json FROM memories WHERE id=?", (old_id,)
            ).fetchone()
            if not row:
                return
            meta = json.loads(row["metadata_json"] or "{}")
            meta["superseded_by"] = new_id
            meta["superseded_at"] = time.time()
            self.store.update(old_id, metadata=meta)
            logger.debug(f"标记 superseded: {old_id} → {new_id}")
        except Exception as e:
            logger.debug(f"标记 superseded 失败: {e}")

    @staticmethod
    def _calc_age_days(updated_at: str, now: datetime) -> float:
        """计算记忆年龄（天数）。"""
        if not updated_at:
            return 30.0
        try:
            ts = datetime.fromisoformat(updated_at)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            return max(0.0, (now - ts).total_seconds() / 86400)
        except (ValueError, TypeError):
            return 30.0
