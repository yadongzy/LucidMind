"""数据可视化 API — 记忆 + 经验 + A/B测试。"""
from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api", tags=["data"])

# 延迟绑定：由 main.py 注入
_memory_adapter = None
_learning_adapter = None
_brain_ref = None


def init(memory, learning, brain=None):
    global _memory_adapter, _learning_adapter, _brain_ref
    _memory_adapter, _learning_adapter = memory, learning
    _brain_ref = brain


@router.get("/reminders")
async def get_reminders():
    """获取待触发的提醒列表。"""
    try:
        from skills.reminder.main import _reminders
        from datetime import datetime
        pending = [r for r in _reminders if not r.get("fired")]
        return {"reminders": pending, "count": len(pending)}
    except Exception:
        return {"reminders": [], "count": 0}


@router.get("/memory/journal")
async def get_journal():
    """获取今日日记和最近日记列表。"""
    try:
        from memory_journal import get_today_journal, get_recent_journals
        return {
            "today": get_today_journal(),
            "recent": get_recent_journals(7),
        }
    except Exception as e:
        return {"today": "", "recent": [], "error": str(e)}


@router.get("/memory/{session_id}")
async def get_memory(session_id: str):
    """记忆可视化 — 查看会话历史。"""
    msgs = await _memory_adapter.get_context(session_id)
    return {"session_id": session_id, "messages": msgs or []}


@router.get("/lessons")
async def get_lessons():
    """经验可视化 — 查看已学习的经验。"""
    if hasattr(_learning_adapter, '_lessons'):
        lessons = _learning_adapter._lessons
    elif hasattr(_learning_adapter, 'store'):
        rows = _learning_adapter.store.get_all(limit=200)
        lessons = [_learning_adapter._to_lesson_dict(r) for r in rows]
    else:
        lessons = []
    return {"lessons": lessons, "count": len(lessons)}


@router.get("/dispatcher/tasks")
async def get_dispatcher_tasks():
    """任务调度器队列 — 轻量级：只返回活跃任务+最近10条历史。"""
    try:
        from task_dispatcher import get_queue_status
        return get_queue_status()
    except Exception as e:
        return {"tasks": [], "total": 0, "error": str(e)}


def _resolve_user_profile_path():
    """优先 identity/USER.md，兼容旧 user_profile.md。"""
    from pathlib import Path
    user_path = Path(__file__).parent.parent / "identity" / "USER.md"
    if user_path.exists():
        return user_path
    legacy = Path(__file__).parent.parent / "user_profile.md"
    if legacy.exists():
        return legacy
    return user_path  # 默认写入新路径


_USER_PROFILE_TEMPLATE = """# 用户画像

> 大脑通过对话学习填充此文件，你也可以手动编辑。

## 基本信息
- **称呼**: （你希望大脑怎么称呼你）
- **语言偏好**: 中文
- **时区**: UTC+8

## 工作与兴趣
- （你的职业或领域）
- （你的兴趣爱好）

## 沟通偏好
- （你喜欢简洁回复还是详细解释）
- （其他沟通习惯）

## 常用工具与习惯
- （你常用的软件、编辑器等）

---
_大脑会在对话中自动学习你的偏好并更新此文件。你也可以随时手动编辑。_
"""

@router.get("/user-profile")
async def get_user_profile():
    """读取用户画像文件。"""
    profile_path = _resolve_user_profile_path()
    if not profile_path.exists():
        return {"content": _USER_PROFILE_TEMPLATE, "exists": False, "is_template": True}
    content = profile_path.read_text(encoding="utf-8")
    if not content.strip():
        return {"content": _USER_PROFILE_TEMPLATE, "exists": True, "is_template": True}
    return {"content": content, "exists": True}


@router.put("/user-profile")
async def update_user_profile(body: dict):
    """保存用户画像文件。"""
    profile_path = _resolve_user_profile_path()
    content = body.get("content", "")
    profile_path.parent.mkdir(parents=True, exist_ok=True)
    profile_path.write_text(content, encoding="utf-8")
    return {"status": "saved", "length": len(content)}


@router.get("/identity/{filename}")
async def get_identity_file(filename: str):
    """读取身份文件（只读展示）。"""
    from pathlib import Path
    allowed = {"CORE.md", "SOUL.md", "BOOTSTRAP.md"}
    if filename not in allowed:
        raise HTTPException(status_code=400, detail=f"不支持: {filename}")
    path = Path(__file__).parent.parent / "identity" / filename
    if not path.exists():
        return {"content": "", "exists": False}
    return {"content": path.read_text(encoding="utf-8"), "exists": True, "file": filename}


@router.post("/dispatcher/tasks")
async def create_dispatcher_task(body: dict):
    """手动创建任务。"""
    try:
        import task_dispatcher as td
        content = body.get("content", "").strip()
        if not content:
            raise HTTPException(status_code=400, detail="content is required")
        priority = body.get("priority", "P2")
        task = td.enqueue(content, task_type="task", priority=priority, source="user")
        return {"status": "created", "task": task}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/lessons/{index}")
async def delete_lesson(index: int):
    """删除单条经验。"""
    try:
        if hasattr(_learning_adapter, '_lessons'):
            lessons = _learning_adapter._lessons
            if 0 <= index < len(lessons):
                lessons.pop(index)
                if hasattr(_learning_adapter, '_save'):
                    _learning_adapter._save()
                elif hasattr(_learning_adapter, 'save'):
                    _learning_adapter.save()
                return {"status": "deleted", "index": index}
            raise HTTPException(status_code=404, detail=f"Index {index} out of range (0-{len(lessons)-1})")
        elif hasattr(_learning_adapter, 'store'):
            rows = _learning_adapter.store.get_all(limit=500)
            if 0 <= index < len(rows):
                _learning_adapter.store.delete(rows[index].id)
                return {"status": "deleted", "index": index}
            raise HTTPException(status_code=404, detail=f"Index {index} out of range (0-{len(rows)-1})")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/memory/{session_id}/{index}")
async def delete_memory_item(session_id: str, index: int):
    """删除单条会话记忆。"""
    try:
        msgs = await _memory_adapter.get_context(session_id)
        if msgs and 0 <= index < len(msgs):
            msgs.pop(index)
            if hasattr(_memory_adapter, '_store'):
                _memory_adapter._store[session_id] = msgs
                if hasattr(_memory_adapter, '_save'):
                    _memory_adapter._save()
            return {"status": "deleted", "index": index, "remaining": len(msgs)}
        raise HTTPException(status_code=404, detail=f"Index {index} out of range")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/dispatcher/tasks/{task_id}/retry")
async def retry_dispatcher_task(task_id: str):
    """重试单个任务（将状态重置为 ready）。"""
    try:
        from task_dispatcher_utils import load_store, save_store
        store = load_store()
        for t in store.get("tasks", []):
            if t.get("id") == task_id:
                if t["status"] in ("completed", "running"):
                    raise HTTPException(status_code=400, detail=f"任务状态 {t['status']} 不可重试")
                t["status"] = "ready"
                t["running_at"] = None
                t["last_error"] = None
                t["retries"] = 0
                save_store(store)
                return {"status": "retried", "id": task_id}
        raise HTTPException(status_code=404, detail="Task not found")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/dispatcher/tasks/{task_id}")
async def delete_dispatcher_task(task_id: str):
    """删除单个任务。"""
    try:
        from task_dispatcher_utils import load_store, save_store
        store = load_store()
        tasks = store.get("tasks", [])
        before = len(tasks)
        store["tasks"] = [t for t in tasks if t.get("id") != task_id]
        if len(store["tasks"]) == before:
            raise HTTPException(status_code=404, detail="Task not found")
        save_store(store)
        return {"status": "deleted", "id": task_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/ab-test")
async def get_ab_test():
    """A/B测试统计 — 对比经验注入开/关的回答质量。"""
    if not _brain_ref:
        raise HTTPException(status_code=503, detail="Brain not initialized")
    stats = _brain_ref._ab_stats

    def _summarize(records: list) -> dict:
        if not records:
            return {"count": 0, "avg_elapsed": 0, "avg_tokens": 0, "avg_response_len": 0}
        n = len(records)
        return {
            "count": n,
            "avg_elapsed": round(sum(r["elapsed"] for r in records) / n, 2),
            "avg_tokens": round(sum(r["tokens"] for r in records) / n),
            "avg_response_len": round(sum(r["response_len"] for r in records) / n),
        }

    return {
        "lessons_enabled": _brain_ref.lessons_enabled,
        "with_lessons": _summarize(stats["with_lessons"]),
        "without_lessons": _summarize(stats["without_lessons"]),
        "raw": {k: v[-10:] for k, v in stats.items()},
    }


@router.put("/ab-test")
async def set_ab_test(body: dict):
    """A/B测试开关 — 切换经验注入。"""
    if not _brain_ref:
        raise HTTPException(status_code=503, detail="Brain not initialized")
    enabled = body.get("lessons_enabled")
    if enabled is not None:
        _brain_ref.lessons_enabled = bool(enabled)
    if body.get("reset"):
        _brain_ref._ab_stats = {"with_lessons": [], "without_lessons": []}
    return {"lessons_enabled": _brain_ref.lessons_enabled, "stats_reset": bool(body.get("reset"))}
