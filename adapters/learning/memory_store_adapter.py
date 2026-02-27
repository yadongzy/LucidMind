"""MemoryStore Learning Adapter — 使用 MemoryStore 实现 LearningPort。

Phase 8.2: 将 brain_learning.py 的学习管道从 JSON 文件切换到 SQLite + ACE Bullet 结构。
实现 LearningPort 接口，可直接替换 JSONLessonsAdapter 注入 Brain。

ACE 核心特性:
- helpful_count / harmful_count 反馈计数器
- 混合搜索 (FTS5 + 向量)
- 确定性 delta 合并
- 向后兼容 JSONLessonsAdapter 的 mark_applied / update_effectiveness
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ports.learning_port import LearningPort
from memory.store import MemoryStore
from memory.types import MemoryConfig
from memory.config import load_config
from adapters.memory.vector_store import get_vector_store
from logs import get_logger

logger = get_logger("learning.memory_store")

_DATA_DIR = Path(__file__).parent.parent.parent / "data"
_DEFAULT_DB_PATH = _DATA_DIR / "memory" / "main.sqlite"

# 分类规则（复用 json_lessons 的逻辑）
_CAT_RULES = [
    ("platform", ["windows", "macos", "linux", "darwin", "平台", "操作系统"]),
    ("tool_usage", ["工具", "tool", "run_command", "read_file", "write_file"]),
    ("error_fix", ["失败", "错误", "error", "fail", "bug", "修复", "重试"]),
    ("method", ["方法", "步骤", "原则", "策略", "方法论"]),
    ("user_pref", ["用户", "偏好", "习惯", "风格", "user"]),
]

# tier → collection 映射
_TIER_TO_COLLECTION = {
    "strategy": "facts",
    "fact": "facts",
    "temp": "lessons",
    "general": "lessons",
}


def _auto_category(trigger: str, lesson: str) -> str:
    """根据 trigger+lesson 内容关键词自动分类。"""
    text = (trigger + " " + lesson).lower()
    for cat, keywords in _CAT_RULES:
        if any(kw in text for kw in keywords):
            return cat
    return "general"


def _classify_tier(experience: dict) -> str:
    """简化版 tier 分类。"""
    source = experience.get("source", "")
    if source in ("teaching", "correction"):
        return "strategy"
    lesson = experience.get("lesson", "")
    if any(kw in lesson for kw in ["总是", "永远", "规则", "原则", "never", "always"]):
        return "strategy"
    return "general"


class MemoryStoreLearningAdapter(LearningPort):
    """基于 MemoryStore 的学习适配器 — ACE Bullet 结构。

    直接实现 LearningPort，可作为 JSONLessonsAdapter 的替代品注入 Brain。
    """

    def __init__(self, db_path: Path | None = None, config: MemoryConfig | None = None):
        self.config = config or load_config()
        self.db_path = db_path or _DEFAULT_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.store = MemoryStore(self.db_path, embedding_dim=self.config.embedding_dim)
        self._vec_store = get_vector_store()
        logger.info(f"MemoryStoreLearningAdapter 初始化: {self.db_path} (条目={self.store.count()}, vec={self._vec_store.is_available()})")

    async def learn(self, experience: dict[str, Any]) -> None:
        """记录一条经验到 MemoryStore，使用 ACE Bullet 结构。"""
        trigger = experience.get("trigger", experience.get("type", ""))
        lesson = experience.get("lesson", experience.get("input", ""))
        if not trigger or not lesson:
            logger.warning("learn() 收到空 trigger 或 lesson，跳过")
            return

        tier = experience.get("tier") or _classify_tier(experience)
        collection = _TIER_TO_COLLECTION.get(tier, "lessons")
        category = experience.get("category") or _auto_category(trigger, lesson)
        source = experience.get("source", "unknown")
        session_id = experience.get("source_session", "")

        # ACE Bullet metadata
        metadata = {
            "trigger": trigger[:200],
            "category": category,
            "tier": tier,
            "source": source,
            "source_session": session_id,
            "source_sessions": [session_id] if session_id else [],
            "helpful_count": 0,
            "harmful_count": 0,
            "applied_count": 0,
            "effectiveness": None,
        }

        # ISS-017: 生成向量嵌入用于语义检索
        content_text = f"{trigger}: {lesson}"
        embedding = self._vec_store.embed(content_text) if self._vec_store.is_available() else None

        # 使用 merge_deltas 实现去重 + 合并
        deltas = [{"content": content_text, "metadata": metadata, "embedding": embedding}]
        result = self.store.merge_deltas(deltas, collection=collection, dedup_threshold=0.85)

        if result["merged"] > 0:
            logger.info(f"经验合并: trigger='{trigger[:50]}' → {collection}")
        elif result["appended"] > 0:
            logger.info(f"新经验: tier={tier}, trigger='{trigger[:50]}' → {collection}")

    async def get_lessons(self, context: str, limit: int = 3) -> list[dict[str, Any]]:
        """混合检索经验: FTS5 + 向量 + ACE 反馈加权。"""
        if not context:
            all_items = self.store.get_all(limit=limit)
            return [self._to_lesson_dict(r) for r in all_items]

        # 向量嵌入（ISS-017: 接入 Ollama embedding）
        query_embedding = self._vec_store.embed(context) if self._vec_store.is_available() else None

        # 混合搜索（跨 lessons + facts + skills 集合）
        results = self.store.search_hybrid(
            query_text=context,
            query_embedding=query_embedding,
            collection=None,  # 跨集合搜索
            vector_weight=self.config.vector_weight,
            text_weight=self.config.text_weight,
            limit=limit * 3,
            min_score=0.0,  # 不过滤，让下面的加权处理
        )

        # ACE 反馈加权: helpful_count 提升分数，harmful_count 降低
        for r in results:
            helpful = r.metadata.get("helpful_count", 0)
            harmful = r.metadata.get("harmful_count", 0)
            feedback_bonus = (helpful - harmful) * 0.05
            r.score = max(0.0, r.score + feedback_bonus)
            # 应用次数衰减
            applied = r.metadata.get("applied_count", 0)
            if applied > 10:
                r.score *= 0.8

        # 排序并截取
        results.sort(key=lambda r: r.score, reverse=True)
        lessons = [self._to_lesson_dict(r) for r in results[:limit]]

        if lessons:
            tiers = [l.get("tier", "?") for l in lessons]
            logger.info(f"检索到 {len(lessons)} 条经验 tiers={tiers} (context='{context[:50]}')")
        return lessons

    async def mark_applied(self, lesson_id: str) -> None:
        """标记经验已被应用 (applied_count++)。"""
        row = self.store.db.execute(
            "SELECT metadata_json FROM memories WHERE id=?", (lesson_id,)
        ).fetchone()
        if not row:
            return
        meta = json.loads(row["metadata_json"])
        meta["applied_count"] = meta.get("applied_count", 0) + 1
        self.store.update(lesson_id, metadata=meta)

    async def update_effectiveness(self, lesson_id: str, effective: bool) -> None:
        """更新经验有效性 — 同时更新 ACE helpful/harmful 计数器。"""
        if effective:
            self.store.increment_feedback(lesson_id, "helpful")
        else:
            self.store.increment_feedback(lesson_id, "harmful")

        # 同时维护传统 effectiveness 字段（兼容性）
        row = self.store.db.execute(
            "SELECT metadata_json FROM memories WHERE id=?", (lesson_id,)
        ).fetchone()
        if not row:
            return
        meta = json.loads(row["metadata_json"])
        current = meta.get("effectiveness")
        if current is None:
            meta["effectiveness"] = 1.0 if effective else 0.0
        else:
            alpha = 0.3
            meta["effectiveness"] = current * (1 - alpha) + (1.0 if effective else 0.0) * alpha
        self.store.update(lesson_id, metadata=meta)
        logger.info(f"更新有效性: id={lesson_id}, effective={effective}, score={meta['effectiveness']:.2f}")

    def _to_lesson_dict(self, result) -> dict[str, Any]:
        """将 MemoryResult 转换为传统 lesson dict 格式（兼容 brain_learning.py）。"""
        meta = result.metadata or {}
        return {
            "id": result.id,
            "trigger": meta.get("trigger", ""),
            "lesson": result.content,
            "category": meta.get("category", "general"),
            "source": meta.get("source", "unknown"),
            "source_session": meta.get("source_session", ""),
            "tier": meta.get("tier", "general"),
            "applied_count": meta.get("applied_count", 0),
            "effectiveness": meta.get("effectiveness"),
            "helpful_count": meta.get("helpful_count", 0),
            "harmful_count": meta.get("harmful_count", 0),
            "created_at": result.created_at,
            "updated_at": result.updated_at,
        }

    def close(self) -> None:
        """关闭底层 MemoryStore。"""
        self.store.close()
