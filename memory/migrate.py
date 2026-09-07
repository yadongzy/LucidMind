"""Memory Migration — 从 lessons.json 迁移到 SQLite MemoryStore。"""

import json
from pathlib import Path
from typing import Any

from memory.store import MemoryStore
from logs import get_logger

logger = get_logger("memory.migrate")

_DATA_DIR = Path(__file__).parent.parent / "data"


def migrate_lessons_to_store(store: MemoryStore,
                              lessons_path: Path | None = None,
                              embed_fn: Any = None) -> dict:
    """将 lessons.json 中的经验迁移到 MemoryStore。

    Args:
        store: 目标 MemoryStore
        lessons_path: lessons.json 路径（默认 data/lessons.json）
        embed_fn: 可选的同步 embedding 函数

    Returns:
        {"migrated": int, "skipped": int, "errors": int}
    """
    if lessons_path is None:
        lessons_path = _DATA_DIR / "lessons.json"

    if not lessons_path.exists():
        logger.info("lessons.json 不存在，无需迁移")
        return {"migrated": 0, "skipped": 0, "errors": 0}

    try:
        lessons = json.loads(lessons_path.read_text("utf-8"))
        if not isinstance(lessons, list):
            return {"migrated": 0, "skipped": 0, "errors": 0}
    except Exception as e:
        logger.error(f"读取 lessons.json 失败: {e}")
        return {"migrated": 0, "skipped": 0, "errors": 1}

    # 检查是否已迁移过
    existing_count = store.count(collection="lessons")
    if existing_count >= len(lessons):
        logger.info(f"已有 {existing_count} 条记忆 >= lessons.json 的 {len(lessons)} 条，跳过迁移")
        return {"migrated": 0, "skipped": len(lessons), "errors": 0}

    migrated = 0
    skipped = 0
    errors = 0

    for lesson in lessons:
        trigger = lesson.get("trigger", "")
        lesson_text = lesson.get("lesson", "")
        if not trigger and not lesson_text:
            skipped += 1
            continue

        content = f"触发: {trigger}\n教训: {lesson_text}"
        collection = "facts" if lesson.get("tier") == "strategy" else "lessons"

        metadata = {
            "original_id": lesson.get("id", ""),
            "source": lesson.get("source", "unknown"),
            "category": lesson.get("category", "general"),
            "tier": lesson.get("tier", "temp"),
            "effectiveness": lesson.get("effectiveness"),
            "applied_count": lesson.get("applied_count", 0),
            "source_session": lesson.get("source_session", ""),
        }

        try:
            embedding = None
            if embed_fn:
                try:
                    embedding = embed_fn(content)
                except Exception:
                    pass
            store.add(
                collection=collection,
                content=content,
                embedding=embedding,
                metadata=metadata,
            )
            migrated += 1
        except Exception as e:
            logger.warning(f"迁移失败: {lesson.get('id', '?')} — {e}")
            errors += 1

    logger.info(f"迁移完成: migrated={migrated}, skipped={skipped}, errors={errors}")
    return {"migrated": migrated, "skipped": skipped, "errors": errors}
