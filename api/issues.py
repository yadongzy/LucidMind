"""Issues API — 自愈问题查询、手动修复、关闭。"""

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/issues", tags=["issues"])


@router.get("")
async def list_issues(status: str = ""):
    """查询问题列表。status 可选: open / verifying / closed，留空返回全部。"""
    from issue_tracker import _load_issues
    issues = _load_issues()
    if status:
        issues = [i for i in issues if i.get("status") == status]
    return {"issues": issues, "total": len(issues)}


@router.get("/open")
async def list_open():
    """仅返回 open 状态的问题。"""
    from issue_tracker import get_open_issues
    issues = get_open_issues()
    return {"issues": issues, "total": len(issues)}


@router.get("/stats")
async def issue_stats():
    """问题统计：各状态数量 + 修复成功率。"""
    from issue_tracker import _load_issues
    issues = _load_issues()
    counts = {"open": 0, "verifying": 0, "closed": 0}
    repaired = 0
    for i in issues:
        s = i.get("status", "open")
        counts[s] = counts.get(s, 0) + 1
        if s == "closed" and i.get("resolution") not in (None, "max_retry_exceeded"):
            repaired += 1
    total_resolved = counts["closed"]
    rate = round(repaired / total_resolved * 100, 1) if total_resolved > 0 else 0
    return {"counts": counts, "repair_success_rate": rate, "total": len(issues)}


@router.post("/{issue_id}/repair")
async def repair_issue(issue_id: int):
    """手动触发单条问题的修复。"""
    from issue_tracker import _load_issues
    issues = _load_issues()
    target = next((i for i in issues if i["id"] == issue_id), None)
    if not target:
        raise HTTPException(status_code=404, detail="Issue not found")
    if target["status"] == "closed":
        raise HTTPException(status_code=400, detail="Issue already closed")
    try:
        from api.brain_init import daemon
        if daemon and hasattr(daemon, '_repair_engine'):
            report = await daemon._repair_engine.repair_all()
            return {"status": "ok", "report": report}
        return {"status": "error", "message": "修复引擎不可用"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.post("/{issue_id}/close")
async def close_issue_api(issue_id: int):
    """手动关闭问题（误报或已自行解决）。"""
    from issue_tracker import close_issue, _load_issues
    issues = _load_issues()
    target = next((i for i in issues if i["id"] == issue_id), None)
    if not target:
        raise HTTPException(status_code=404, detail="Issue not found")
    close_issue(issue_id, resolution="manual_closed")
    return {"status": "ok", "message": f"Issue {issue_id} closed"}
