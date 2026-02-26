"""Security API — 工具安全审批配置管理。"""

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/api/security", tags=["security"])

_guard = None


def init(guard):
    global _guard
    _guard = guard


class ToggleRequest(BaseModel):
    enabled: bool


class ToolClassifyRequest(BaseModel):
    tool_name: str
    level: str  # "dangerous" | "safe" | "reset"


@router.get("/config")
async def get_config():
    return _guard.get_config()


@router.post("/toggle")
async def toggle_safety(req: ToggleRequest):
    _guard.set_enabled(req.enabled)
    return {"status": "ok", "enabled": req.enabled}


@router.get("/dangerous-tools")
async def dangerous_tools():
    return {"tools": _guard.get_all_dangerous()}


@router.post("/classify")
async def classify_tool(req: ToolClassifyRequest):
    if req.level == "dangerous":
        _guard.add_dangerous(req.tool_name)
    elif req.level == "safe":
        _guard.add_safe(req.tool_name)
    elif req.level == "reset":
        _guard.reset_tool(req.tool_name)
    else:
        return {"status": "error", "message": f"未知级别: {req.level}"}
    return {"status": "ok", "tool": req.tool_name, "level": req.level}


@router.post("/approve")
async def approve_tool(request_id: str, approved: bool, reason: str = ""):
    """处理前端发来的审批响应。"""
    ok = _guard.handle_approval_response(request_id, approved, reason)
    return {"status": "ok" if ok else "not_found", "request_id": request_id}


@router.post("/scan/{plugin_name}")
async def scan_plugin(plugin_name: str):
    """手动触发对已安装插件的安全扫描。"""
    from fastapi import HTTPException
    from skills import _validate_plugin_name
    import pathlib
    if not _validate_plugin_name(plugin_name):
        raise HTTPException(status_code=400, detail=f"插件名不合法: {plugin_name}")
    skill_dir = pathlib.Path(__file__).parent.parent / "skills" / plugin_name
    if not skill_dir.is_dir():
        raise HTTPException(status_code=404, detail=f"插件不存在: {plugin_name}")
    from skills.skill_scanner import scan_skill_directory
    result = scan_skill_directory(skill_dir)
    return result


@router.get("/scan-history")
async def scan_history(limit: int = 50):
    """查询扫描历史记录。"""
    from skills.skill_scanner import get_scan_history
    records = get_scan_history(limit=limit)
    return {"records": records, "total": len(records)}
