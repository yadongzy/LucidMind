"""Diagnostics API — 诊断事件查询与摘要。"""

from fastapi import APIRouter
import time

router = APIRouter(prefix="/api/diagnostics", tags=["diagnostics"])


@router.get("")
async def query_events(category: str = "", status: str = "", minutes: int = 60, limit: int = 50):
    """查询诊断事件。"""
    from diagnostics import get_collector
    since = time.time() - minutes * 60 if minutes > 0 else None
    events = get_collector().query(
        category=category or None,
        status=status or None,
        since=since,
        limit=limit,
    )
    return {"events": events, "total": len(events)}


@router.get("/summary")
async def summary(hours: int = 24):
    """诊断摘要（各类别的成功率、P50/P95 耗时等）。"""
    from diagnostics import get_collector
    since = time.time() - hours * 3600 if hours > 0 else None
    return get_collector().summary(since=since)


@router.get("/timeline")
async def timeline(minutes: int = 60):
    """时间线视图数据（按分钟聚合）。"""
    from diagnostics import get_collector
    since = time.time() - minutes * 60
    events = get_collector().query(since=since, limit=1000)
    # 按分钟聚合
    buckets: dict[int, dict] = {}
    for e in events:
        minute = int(e["timestamp"] // 60) * 60
        b = buckets.setdefault(minute, {"timestamp": minute, "total": 0, "success": 0, "failure": 0})
        b["total"] += 1
        if e["status"] == "success":
            b["success"] += 1
        elif e["status"] in ("failure", "timeout", "error"):
            b["failure"] += 1
    return {"buckets": sorted(buckets.values(), key=lambda x: x["timestamp"])}
