"""任务调度器工具函数 — 从 task_dispatcher.py 拆分（规则03: ≤300行）。

包含: 存储层、动态间隔、卡住检测、清理、淘汰、每日状态、队列状态。
"""
import json
import os
from datetime import datetime, date
from pathlib import Path

from logs import get_logger

logger = get_logger("dispatcher")

_DATA = Path(__file__).parent / "data"
_QUEUE_FILE = _DATA / "task_queue.json"
STUCK_TIMEOUT_S = 300
MAX_TASK_QUEUE = 50
MAX_MEMO = 200
_PRIORITY_ORDER = {
    "P0": 0, "P1": 1, "P2": 2, "P3": 3,
    "L0": 4, "L1": 5, "L2": 6, "L3": 7,
}


def _atomic_save(path: Path, data: dict):
    """原子写入JSON文件。"""
    _DATA.mkdir(exist_ok=True)
    tmp = path.parent / f"{path.name}.{os.getpid()}.tmp"
    try:
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(str(tmp), str(path))
    except Exception:
        if tmp.exists():
            tmp.unlink(missing_ok=True)
        raise


def load_store() -> dict:
    """加载任务队列文件。"""
    if _QUEUE_FILE.exists():
        try:
            data = json.loads(_QUEUE_FILE.read_text("utf-8"))
            if isinstance(data, dict) and "tasks" in data:
                return data
            logger.warning(f"队列文件格式错误(type={type(data).__name__})，重建")
        except Exception as e:
            logger.warning(f"队列文件损坏，重建: {e}")
    return {"version": 1, "tasks": [], "daily_state": {}, "memo": []}


def save_store(store: dict):
    """保存任务队列文件（原子写入）。"""
    _atomic_save(_QUEUE_FILE, store)


def release_stuck_tasks() -> int:
    """释放超时的running任务。"""
    store = load_store()
    released = 0
    now = datetime.now()
    for t in store["tasks"]:
        if t["status"] != "running" or not t.get("running_at"):
            continue
        try:
            started = datetime.fromisoformat(t["running_at"])
            elapsed = (now - started).total_seconds()
        except (ValueError, TypeError):
            elapsed = STUCK_TIMEOUT_S + 1
        if elapsed > t.get("timeout_s", STUCK_TIMEOUT_S):
            t["retries"] = t.get("retries", 0) + 1
            t["running_at"] = None
            t["last_error"] = f"超时{elapsed:.0f}s，强制释放"
            if t["retries"] >= t.get("max_retries", 3):
                t["status"] = "escalated"
                logger.warning(f"⏰ 超时上报: {t['id']} elapsed={elapsed:.0f}s")
            else:
                t["status"] = "ready"
                logger.info(f"⏰ 超时释放: {t['id']} elapsed={elapsed:.0f}s")
            released += 1
    if released > 0:
        save_store(store)
    return released


def compute_interval() -> int:
    """根据队列状态计算下一轮循环间隔。"""
    store = load_store()
    active = [t for t in store.get("tasks", []) if t["status"] in ("ready", "blocked")]
    priorities = {t["priority"] for t in active}
    if "P0" in priorities: return 10
    if priorities & {"P1", "P2"}: return 30
    if "P3" in priorities: return 60
    if priorities & {"L0", "L1", "L2", "L3"}: return 120
    return 60


def cleanup_completed(max_keep: int = 10):
    """清理已完成/已上报/失败任务，只保留最近max_keep条。"""
    store = load_store()
    active = [t for t in store.get("tasks", []) if t["status"] in ("ready", "running", "blocked")]
    done = [t for t in store.get("tasks", []) if t["status"] not in ("ready", "running", "blocked")]
    done.sort(key=lambda t: t.get("completed_at") or t.get("created_at", ""), reverse=True)
    removed = max(0, len(done) - max_keep)
    store["tasks"] = active + done[:max_keep]
    if removed > 0:
        save_store(store)
        logger.info(f"🧹 清理{removed}条已完成任务，保留{len(store['tasks'])}条")


def auto_expire() -> list[str]:
    """自动淘汰：P0超24h报警，P3超7d自检，闲置超30d归档，重复失败丢弃。"""
    store = load_store()
    now = datetime.now()
    report = []
    for t in store.get("tasks", []):
        if t["status"] in ("completed", "failed", "escalated", "memo"):
            continue
        try:
            created = datetime.fromisoformat(t["created_at"])
            age_days = (now - created).days
            age_hours = (now - created).total_seconds() / 3600
        except (ValueError, TypeError):
            continue
        if t["status"] == "ready" and t.get("retries", 0) >= t.get("max_retries", 3):
            t["status"] = "failed"
            t["last_error"] = f"智能淘汰: 重试{t['retries']}次均失败"
            report.append(f"🗑️ 淘汰重复失败: {t['content'][:30]}")
            continue
        if t["status"] == "ready" and t.get("source") == "teacher" and age_hours > 12:
            t["status"] = "completed"; t["completed_at"] = now.isoformat()
            t["last_error"] = "智能淘汰: 超12小时未处理的教学消息"
            report.append(f"⏰ 淘汰过时教学: {t['content'][:30]}")
            continue
        if t["priority"] == "P0" and age_hours > 24 and t["status"] == "ready":
            t["status"] = "escalated"; t["last_error"] = "P0超24小时未完成，自动上报"
            report.append(f"🆘 P0超时上报: {t['content'][:30]}")
        elif t["priority"] == "P3" and age_days > 7 and t["status"] == "ready":
            t["last_error"] = "P3超7天未处理，待自检"
            report.append(f"⏳ P3超7天: {t['content'][:30]}")
        elif age_days > 30 and t["status"] == "ready":
            t["status"] = "memo"; store.setdefault("memo", []).append(t)
            report.append(f"📦 闲置30天归档: {t['content'][:30]}")
    store["tasks"] = [t for t in store["tasks"] if t["status"] != "memo"]
    if now.day == 1:
        memo = store.get("memo", [])
        before = len(memo)
        kept = [m for m in memo if _memo_age_ok(m, now)]
        if len(kept) < before:
            store["memo"] = kept
            report.append(f"🗑️ 月度清理: 删除{before - len(kept)}条超90天归档")
    if report:
        save_store(store)
        logger.info(f"⏰ 自动淘汰: {'; '.join(report[:5])}")
    return report


def _memo_age_ok(m: dict, now: datetime) -> bool:
    try:
        return (now - datetime.fromisoformat(m.get("created_at", ""))).days <= 90
    except (ValueError, TypeError):
        return True


def get_queue_status() -> dict:
    """获取队列状态摘要 + 轻量任务列表。"""
    store = load_store()
    tasks = store.get("tasks", [])
    status_counts = {}
    for t in tasks:
        status_counts[t["status"]] = status_counts.get(t["status"], 0) + 1
    light_tasks = [{k: v for k, v in t.items() if k != "content"} | {"content": (t.get("content") or "")[:500]} for t in tasks]
    return {"tasks": light_tasks, "total": len(tasks), "shown": len(light_tasks),
            "by_status": status_counts, "memo_count": len(store.get("memo", []))}


def get_daily_state() -> dict:
    return load_store().get("daily_state", {})

def set_daily_check_done():
    store = load_store()
    store.setdefault("daily_state", {})["last_daily_check"] = date.today().isoformat()
    save_store(store)

def is_daily_check_done() -> bool:
    return get_daily_state().get("last_daily_check") == date.today().isoformat()

def set_monthly_check_done():
    store = load_store()
    store.setdefault("daily_state", {})["last_monthly_check"] = date.today().strftime("%Y-%m")
    save_store(store)

def is_monthly_check_done() -> bool:
    return get_daily_state().get("last_monthly_check") == date.today().strftime("%Y-%m")
