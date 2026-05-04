"""Memory Store Ranking Mixin — 搜索结果排序管线。

从 store.py 拆分，包含 Multi-Stage Retrieval Pipeline 的排序方法:
- RRF 融合
- 新鲜度加成
- 重要性权重
- 长度归一化
- 时间衰减
- MMR 多样性去重
"""

import math
from datetime import datetime, timezone

from memory.types import MemoryResult


class StoreRankingMixin:
    """搜索排序管线方法集。由 MemoryStore 混入使用。"""

    # 管线参数
    _RECENCY_HALF_LIFE_DAYS = 14    # 新鲜度加成半衰期
    _RECENCY_WEIGHT = 0.10          # 新鲜度加成权重上限
    _TIME_DECAY_HALF_LIFE_DAYS = 60 # 时间衰减半衰期
    _LENGTH_NORM_ANCHOR = 500       # 长度归一化锚点（字符数）
    _HARD_MIN_SCORE = 0.20          # 最终硬过滤阈值
    _MMR_SIMILARITY_THRESHOLD = 0.85 # MMR 去重相似度阈值
    _EVERGREEN_COLLECTIONS = frozenset({"facts", "skills"})  # 常青集合: 不受时间衰减

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

        Evergreen 豁免: facts/skills 集合不受时间衰减（对标 OpenClaw temporal-decay.ts 的
        isEvergreenMemoryPath）。这些集合存储持久知识，无论多久都应该被检索到。
        """
        half_life = self._TIME_DECAY_HALF_LIFE_DAYS
        if half_life <= 0:
            return results

        now = datetime.now(timezone.utc)

        for r in results:
            if r.collection in self._EVERGREEN_COLLECTIONS:
                continue  # Evergreen: 不衰减
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
