"""JSON Lessons Adapter — 经验学习的 JSON 文件实现。

S8: 从用户纠正中学习，结构化存储，有效性追踪，自动淘汰。
超越 OpenClaw 的维度：主动学习 / 有效性追踪 / 经验淘汰 / 透明 / 结构化。
"""

import json
import os
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ports.learning_port import LearningPort
from adapters.learning.memory_curator import (
    should_add_lesson, classify_tier, curate, get_half_life_days,
)
from logs import get_logger

logger = get_logger("learning")

MAX_LESSONS = 200
_CURATE_INTERVAL = 3600  # 每小时触发一次curate检查

_CAT_RULES = [
    ("platform", ["windows", "macos", "linux", "darwin", "平台", "操作系统", "命令对照"]),
    ("tool_usage", ["工具", "tool", "introspect", "run_command", "read_file", "write_file", "gui_window", "scheduler"]),
    ("error_fix", ["失败", "错误", "error", "fail", "bug", "修复", "重试", "超时"]),
    ("method", ["方法", "步骤", "原则", "策略", "方法论", "5步法", "排错"]),
    ("user_pref", ["用户", "偏好", "习惯", "风格", "user"]),
]


def _auto_category(trigger: str, lesson: str) -> str:
    """根据 trigger+lesson 内容关键词自动分类。"""
    text = (trigger + " " + lesson).lower()
    for cat, keywords in _CAT_RULES:
        if any(kw in text for kw in keywords):
            return cat
    return "general"


class JSONLessonsAdapter(LearningPort):
    """JSON 文件经验存储。每条经验有 trigger/lesson/effectiveness 追踪。"""

    def __init__(self, data_dir: str | None = None):
        self.data_dir = Path(data_dir or os.path.join(os.path.dirname(__file__), "..", "..", "data"))
        self.lessons_file = self.data_dir / "lessons.json"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._lessons: list[dict[str, Any]] = self._load()
        self._last_curate_time: float = 0.0
        # 启动时执行一次经验管理
        self._auto_curate()
        logger.info(f"初始化: data_dir={self.data_dir}, 已有经验={len(self._lessons)}条")

    def _load(self) -> list[dict[str, Any]]:
        if not self.lessons_file.exists():
            return []
        try:
            data = json.loads(self.lessons_file.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"经验文件加载失败: {e}")
            return []

    def _save(self) -> None:
        try:
            fd, tmp = tempfile.mkstemp(dir=str(self.data_dir), suffix=".tmp")
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(self._lessons, f, ensure_ascii=False, indent=2)
            os.replace(tmp, str(self.lessons_file))
        except OSError as e:
            logger.error(f"经验文件保存失败: {e}")

    async def learn(self, experience: dict[str, Any]) -> None:
        """记录一条经验。自动去重、合并相似、淘汰低效。"""
        trigger = experience.get("trigger", experience.get("type", ""))
        lesson = experience.get("lesson", experience.get("input", ""))
        if not trigger or not lesson:
            logger.warning("learn() 收到空 trigger 或 lesson，跳过")
            return

        # 去重：相同 trigger 的经验合并
        for existing in self._lessons:
            if existing.get("trigger") == trigger:
                existing["lesson"] = lesson
                existing["updated_at"] = datetime.now(timezone.utc).isoformat()
                existing["applied_count"] = 0
                existing["effectiveness"] = None
                logger.info(f"经验合并: trigger='{trigger[:50]}', 更新 lesson")
                self._save()
                return

        entry = {
            "id": f"lesson_{uuid.uuid4().hex[:8]}",
            "trigger": trigger,
            "lesson": lesson,
            "category": _auto_category(trigger, lesson),
            "source": experience.get("source", "unknown"),
            "source_session": experience.get("source_session", ""),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "applied_count": 0,
            "effectiveness": None,
            "tier": classify_tier(experience),
        }
        # P1: 选择性添加门控（论文: add-all比不添加更差）
        if not should_add_lesson(entry, self._lessons):
            return
        self._lessons.append(entry)
        logger.info(f"新经验: id={entry['id']}, tier={entry['tier']}, trigger='{trigger[:50]}'")

        # 经验管理：超过上限或定期触发curate
        if len(self._lessons) > MAX_LESSONS:
            self._auto_curate()

        self._save()

    async def get_lessons(self, context: str, limit: int = 3) -> list[dict[str, Any]]:
        """混合检索经验：BM25 + 时间衰减 + 有效性加权 + MMR 去重。"""
        if not self._lessons:
            return []
        if not context:
            return self._lessons[:limit]

        # 定期触发curate
        self._auto_curate()

        from adapters.memory.retrieval import hybrid_search
        # P3: 分层衰减 — strategy永不衰减，temp快速衰减
        # 对不同tier的经验分组检索，使用各自的半衰期
        all_results: list[dict[str, Any]] = []
        tier_groups: dict[str, list[dict[str, Any]]] = {}
        for lesson in self._lessons:
            tier = lesson.get("tier") or classify_tier(lesson)
            tier_groups.setdefault(tier, []).append(lesson)
        for tier, group in tier_groups.items():
            half_life = get_half_life_days(tier)
            results = hybrid_search(
                query=context, items=group, text_fields=["trigger", "lesson"],
                limit=limit * 2, time_field="created_at",
                half_life_days=half_life, mmr_lambda=0.7,
            )
            all_results.extend(results)

        # 有效性加权 + 应用次数衰减
        for r in all_results:
            eff = r.get("effectiveness")
            if eff is not None:
                r["_score"] = r.get("_score", 0) * max(0.1, eff)
            applied = r.get("applied_count", 0)
            if applied > 10:
                r["_score"] = r.get("_score", 0) * 0.8

        all_results.sort(key=lambda x: x.get("_score", 0), reverse=True)
        cleaned = [{k: v for k, v in r.items() if not k.startswith("_")} for r in all_results[:limit]]
        if cleaned:
            tiers = [c.get('tier', '?') for c in cleaned]
            logger.info(f"检索到 {len(cleaned)} 条经验 tiers={tiers} (context='{context[:50]}')")
        return cleaned

    def _auto_curate(self) -> None:
        """自动经验管理：调用curator的组合删除策略。"""
        import time as _time
        now = _time.time()
        if now - self._last_curate_time < _CURATE_INTERVAL and len(self._lessons) <= MAX_LESSONS:
            return
        self._last_curate_time = now
        if len(self._lessons) < 10:
            return
        self._lessons, stats = curate(self._lessons, now)
        if stats["removed"] > 0:
            self._save()
            logger.info(f"经验管理: {stats}")

    async def mark_applied(self, lesson_id: str) -> None:
        """标记经验已被应用（applied_count++）。"""
        for lesson in self._lessons:
            if lesson.get("id") == lesson_id:
                lesson["applied_count"] = lesson.get("applied_count", 0) + 1
                self._save()
                return

    async def update_effectiveness(self, lesson_id: str, effective: bool) -> None:
        """更新经验有效性。effective=True 提升分数，False 降低。"""
        for lesson in self._lessons:
            if lesson.get("id") == lesson_id:
                current = lesson.get("effectiveness")
                if current is None:
                    lesson["effectiveness"] = 1.0 if effective else 0.0
                else:
                    # 指数移动平均
                    alpha = 0.3
                    lesson["effectiveness"] = current * (1 - alpha) + (1.0 if effective else 0.0) * alpha
                logger.info(f"更新有效性: id={lesson_id}, effective={effective}, score={lesson['effectiveness']:.2f}")
                self._save()
                return
