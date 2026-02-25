"""定时任务 — 统一 Cron 调度器（API + SchedulerAdapter 单一数据源）。

用户可通过 API 或 Brain 工具注册/查看/删除定时任务。
任务存储在 data/cron.json，服务器启动时加载。
"""

import asyncio
import json
import time
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from logs import get_logger

logger = get_logger("cron")

router = APIRouter()

_CRON_FILE = Path(__file__).parent.parent / "data" / "cron.json"
_jobs: list[dict[str, Any]] = []
_running = False
_ws_channel = None  # WebSocket channel for push notifications

_SCHEDULE_MAP = {"hourly": 3600, "daily": 86400, "weekly": 604800, "monthly": 2592000}


def set_ws_channel(ch):
    """由 main.py 注入 WebSocket channel。"""
    global _ws_channel
    _ws_channel = ch


def _parse_interval(schedule: str | None, interval_seconds: int | None) -> int:
    """将 schedule 字符串或 interval_seconds 统一为秒数。"""
    if interval_seconds and interval_seconds > 0:
        return interval_seconds
    if schedule:
        secs = _SCHEDULE_MAP.get(schedule.lower())
        if secs:
            return secs
        # 尝试解析 "every 5 minutes" 等格式
        import re
        m = re.match(r"every\s+(\d+)\s*(second|minute|hour|day)", schedule.lower())
        if m:
            val, unit = int(m.group(1)), m.group(2)
            mult = {"second": 1, "minute": 60, "hour": 3600, "day": 86400}
            return val * mult.get(unit, 60)
    return 0


class CronJobRequest(BaseModel):
    description: str
    interval_seconds: int = 0  # 执行间隔（秒），与 schedule 二选一
    schedule: str = ""  # 频率字符串: hourly/daily/weekly/monthly 或 cron 表达式
    command: str = ""  # 要执行的消息（发给 Brain）
    job_type: str = "every"  # every / at / cron
    trigger_at: str = ""  # at 类型专用


def _load_jobs():
    global _jobs
    if _CRON_FILE.exists():
        try:
            _jobs = json.loads(_CRON_FILE.read_text(encoding="utf-8"))
            logger.info(f"加载 {len(_jobs)} 个定时任务")
        except (json.JSONDecodeError, OSError) as e:
            logger.error(f"加载定时任务失败: {e}")
            _jobs = []


def _save_jobs():
    try:
        _CRON_FILE.parent.mkdir(parents=True, exist_ok=True)
        _CRON_FILE.write_text(json.dumps(_jobs, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as e:
        logger.error(f"保存定时任务失败: {e}")


def add_job(description: str, command: str, interval_seconds: int = 0,
            schedule: str = "", name: str = "",
            trigger_at: str = "", job_type: str = "every") -> dict:
    """统一入口：创建定时任务（API 和 SchedulerAdapter 共用）。
    
    job_type:
        - 'every': 间隔重复（默认）
        - 'at': 一次性定时（到 trigger_at 时间触发一次后禁用）
    """
    if job_type == "at":
        if not trigger_at:
            raise ValueError("at 类型任务需要 trigger_at 参数")
        if not command:
            raise ValueError("command is required")
        job = {
            "id": uuid.uuid4().hex[:8],
            "name": name or description[:30],
            "description": description,
            "type": "at",
            "trigger_at": trigger_at,
            "command": command,
            "created_at": time.time(),
            "last_run": None,
            "run_count": 0,
            "enabled": True,
            "status": "waiting",
        }
    elif job_type == "cron":
        if not schedule:
            raise ValueError("cron 类型需要 schedule 参数（cron 表达式，如 '0 9 * * *'）")
        if not command:
            raise ValueError("command is required")
        # 验证 cron 表达式
        try:
            from croniter import croniter
            croniter(schedule)
        except Exception as e:
            raise ValueError(f"无效的 cron 表达式: {schedule} — {e}")
        job = {
            "id": uuid.uuid4().hex[:8],
            "name": name or description[:30],
            "description": description,
            "type": "cron",
            "schedule": schedule,
            "command": command,
            "created_at": time.time(),
            "last_run": None,
            "run_count": 0,
            "enabled": True,
        }
    else:
        resolved = _parse_interval(schedule, interval_seconds)
        if resolved < 60:
            raise ValueError("最小间隔 60 秒")
        if not command:
            raise ValueError("command is required")
        job = {
            "id": uuid.uuid4().hex[:8],
            "name": name or description[:30],
            "description": description,
            "type": "every",
            "interval_seconds": resolved,
            "schedule": schedule or f"every {resolved}s",
            "command": command,
            "created_at": time.time(),
            "last_run": None,
            "run_count": 0,
            "enabled": True,
        }
    _jobs.append(job)
    _save_jobs()
    logger.info(f"创建定时任务: {job['id']} — {description} (type={job_type})")
    # WebSocket 推送通知前端
    if _ws_channel:
        try:
            asyncio.ensure_future(_ws_channel.broadcast(json.dumps({
                "type": "cron_updated", "event": "created", "job": job,
            })))
        except Exception:
            pass
    return job


def remove_job_by_name(name: str) -> int:
    """按 name 删除任务（SchedulerAdapter 用）。返回删除数量。"""
    global _jobs
    before = len(_jobs)
    _jobs = [j for j in _jobs if j.get("name") != name]
    removed = before - len(_jobs)
    if removed:
        _save_jobs()
        logger.info(f"删除定时任务(name={name}): {removed}个")
    return removed


def get_jobs() -> list[dict]:
    """获取所有任务（SchedulerAdapter 用）。"""
    _load_jobs()
    return list(_jobs)


@router.post("/api/cron")
async def create_cron_job(req: CronJobRequest):
    """创建定时任务。"""
    try:
        job = add_job(req.description, req.command, req.interval_seconds, req.schedule,
                      trigger_at=req.trigger_at, job_type=req.job_type)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return job


@router.get("/api/cron")
async def list_cron_jobs():
    """列出所有定时任务。"""
    _load_jobs()
    return {"jobs": _jobs, "count": len(_jobs)}


@router.delete("/api/cron/{job_id}")
async def delete_cron_job(job_id: str):
    """删除定时任务（按 id 或 name）。"""
    global _jobs
    before = len(_jobs)
    _jobs = [j for j in _jobs if j.get("id") != job_id and j.get("name") != job_id]
    if len(_jobs) == before:
        raise HTTPException(404, "Job not found")
    _save_jobs()
    logger.info(f"删除定时任务: {job_id}")
    return {"status": "deleted", "id": job_id}


# Cron 回调注册（由 main.py 在启动时设置）
_on_cron_message = None


def set_cron_callback(callback):
    """注册 cron 消息回调。"""
    global _on_cron_message
    _on_cron_message = callback


async def _run_missed_jobs():
    """重启补偿：扫描过期未触发的 at 任务，立即触发。"""
    from datetime import datetime
    now = time.time()
    missed = 0
    for job in _jobs:
        if not job.get("enabled") or job.get("type") != "at":
            continue
        trigger_at = job.get("trigger_at", "")
        if not trigger_at:
            continue
        try:
            trigger_time = datetime.fromisoformat(trigger_at).timestamp()
        except (ValueError, TypeError):
            continue
        if now >= trigger_time:
            job["last_run"] = now
            job["run_count"] = job.get("run_count", 0) + 1
            job["enabled"] = False
            job["status"] = "fired"
            missed += 1
            logger.info(f"Cron[补偿] 触发遗漏任务: {job.get('id')} — {job.get('description', '')}")
            try:
                import task_dispatcher as td
                td.enqueue(
                    content=f"[定时任务触发] {job.get('command', job.get('description', ''))}",
                    task_type="task", priority="P1", source="cron",
                )
            except Exception as e:
                logger.error(f"Cron[补偿] 入队失败: {e}")
            if _ws_channel:
                try:
                    remind_msg = job.get("command", job.get("description", "提醒"))
                    await _ws_channel.broadcast(json.dumps({
                        "type": "response",
                        "data": f"⏰ **提醒到了！**（重启补偿） {remind_msg}",
                    }))
                except Exception:
                    pass
    if missed:
        _save_jobs()
        logger.info(f"Cron 重启补偿: 触发 {missed} 个遗漏任务")


async def start_cron_scheduler():
    """启动 cron 调度循环（支持 every + at 两种类型）。"""
    global _running
    _load_jobs()
    _running = True
    # 重启补偿：执行因停机遗漏的任务
    await _run_missed_jobs()
    logger.info("Cron 调度器已启动")
    while _running:
        now = time.time()
        dirty = False
        for job in _jobs:
            if not job.get("enabled"):
                continue
            job_type = job.get("type", "every")

            # === at 类型：一次性定时任务 ===
            if job_type == "at":
                trigger_at = job.get("trigger_at", "")
                if not trigger_at:
                    continue
                from datetime import datetime
                try:
                    trigger_time = datetime.fromisoformat(trigger_at).timestamp()
                except (ValueError, TypeError):
                    continue
                if now >= trigger_time:
                    job["last_run"] = now
                    job["run_count"] = job.get("run_count", 0) + 1
                    job["enabled"] = False
                    job["status"] = "fired"
                    job["fired_at"] = now
                    dirty = True
                    job_id = job.get("id", "?")
                    logger.info(f"Cron[at] 触发: {job_id} — {job.get('description', '')}")
                    # 入队 task_dispatcher
                    try:
                        import task_dispatcher as td
                        td.enqueue(
                            content=f"[定时任务触发] {job.get('command', job.get('description', ''))}",
                            task_type="task", priority="P1", source="cron",
                        )
                    except Exception as e:
                        logger.error(f"Cron[at] 入队失败: {job_id} — {e}")
                    # WebSocket 通知：推送事件 + 用户可见提醒消息
                    if _ws_channel:
                        try:
                            await _ws_channel.broadcast(json.dumps({
                                "type": "cron_updated", "event": "fired", "job": job,
                            }))
                            # 直接推送一条对话消息，让用户在聊天窗口看到提醒
                            remind_msg = job.get("command", job.get("description", "提醒"))
                            await _ws_channel.broadcast(json.dumps({
                                "type": "response",
                                "data": f"⏰ **提醒到了！** {remind_msg}",
                            }))
                        except Exception:
                            pass
                continue

            # === cron 表达式类型 ===
            if job_type == "cron":
                cron_expr = job.get("schedule", "")
                if not cron_expr:
                    continue
                try:
                    from datetime import datetime
                    from croniter import croniter
                    last_run = job.get("last_run")
                    base = datetime.fromtimestamp(last_run) if last_run else datetime.fromtimestamp(job.get("created_at", now))
                    cron = croniter(cron_expr, base)
                    next_run = cron.get_next(datetime).timestamp()
                    if now >= next_run:
                        job["last_run"] = now
                        job["run_count"] = job.get("run_count", 0) + 1
                        dirty = True
                        job_id = job.get("id", "?")
                        logger.info(f"Cron[expr] 触发: {job_id} — {job.get('description', '')}")
                        if _on_cron_message:
                            try:
                                sid = f"cron_{job_id}"
                                await _on_cron_message(job["command"], sid)
                            except Exception as e:
                                logger.error(f"Cron[expr] 执行失败: {job_id} — {e}")
                except Exception as e:
                    logger.debug(f"Cron[expr] 计算失败: {job.get('id')} — {e}")
                continue

            # === every 类型：间隔重复任务 ===
            interval = _parse_interval(job.get("schedule"), job.get("interval_seconds"))
            if interval <= 0:
                continue
            last = job.get("last_run") or 0
            if now - last >= interval:
                job["last_run"] = now
                job["run_count"] = job.get("run_count", 0) + 1
                dirty = True
                job_id = job.get("id", "?")
                logger.info(f"Cron[every] 触发: {job_id} — {job.get('description', '')}")
                if _on_cron_message:
                    try:
                        sid = f"cron_{job_id}"
                        await _on_cron_message(job["command"], sid)
                    except Exception as e:
                        logger.error(f"Cron 执行失败: {job_id} — {e}")
        if dirty:
            _save_jobs()
        await asyncio.sleep(5)  # 5秒检查一次
