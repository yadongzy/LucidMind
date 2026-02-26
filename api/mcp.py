"""MCP 管理 API — 服务器配置/连接/断开/工具列表。"""

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/mcp", tags=["mcp"])

_mcp_client = None
_tool_adapter = None


def init(mcp_client, tool_adapter):
    """由 main.py 调用，注入 MCP 客户端和工具适配器引用。"""
    global _mcp_client, _tool_adapter
    _mcp_client = mcp_client
    _tool_adapter = tool_adapter


@router.get("/servers")
async def list_servers():
    """列出所有 MCP Server 配置及状态。"""
    if not _mcp_client:
        return {"servers": [], "total": 0}
    servers = _mcp_client.get_servers()
    return {"servers": servers, "total": len(servers)}


@router.post("/servers")
async def add_server(body: dict):
    """添加一个 MCP Server 配置。"""
    if not _mcp_client:
        raise HTTPException(status_code=500, detail="MCP 客户端未初始化")
    name = body.get("name", "")
    if not name:
        raise HTTPException(status_code=400, detail="name 不能为空")
    transport = body.get("transport", "stdio")
    # Safety by Default: 安全验证
    from adapters.tools.mcp_client import validate_server_config
    valid, reason = validate_server_config(body)
    if not valid:
        raise HTTPException(status_code=400, detail=reason)
    _mcp_client.add_server(body)
    return {"status": "ok", "message": f"MCP Server {name} 已添加"}


@router.put("/servers/{name}")
async def update_server(name: str, body: dict):
    """更新 MCP Server 配置（env、enabled 等字段）。"""
    if not _mcp_client:
        raise HTTPException(status_code=500, detail="MCP 客户端未初始化")
    srv = next((s for s in _mcp_client._servers if s.get("name") == name), None)
    if not srv:
        raise HTTPException(status_code=404, detail=f"未找到: {name}")
    if "env" in body:
        srv["env"] = {**(srv.get("env") or {}), **body["env"]}
    if "enabled" in body:
        srv["enabled"] = bool(body["enabled"])
    _mcp_client.save_config()
    return {"status": "ok", "message": f"MCP Server {name} 已更新", "server": srv}


@router.delete("/servers/{name}")
async def remove_server(name: str):
    """移除一个 MCP Server 配置。"""
    if not _mcp_client:
        raise HTTPException(status_code=500, detail="MCP 客户端未初始化")
    ok = _mcp_client.remove_server(name)
    if not ok:
        raise HTTPException(status_code=404, detail=f"未找到: {name}")
    return {"status": "ok", "message": f"MCP Server {name} 已移除"}


@router.post("/discover")
async def discover():
    """重新发现所有 MCP Server 的工具。"""
    if not _mcp_client:
        raise HTTPException(status_code=500, detail="MCP 客户端未初始化")
    count = await _mcp_client.discover()
    if _tool_adapter:
        _tool_adapter._rebuild_map()
    return {"status": "ok", "tools_discovered": count}


@router.get("/health")
async def health_check():
    """B5: 检查所有 MCP Server 连接健康状态。"""
    if not _mcp_client:
        return {"servers": {}, "healthy": False}
    results = await _mcp_client.health_check()
    all_healthy = all(v.get("status") in ("healthy", "disabled") for v in results.values())
    return {"servers": results, "healthy": all_healthy}


@router.get("/tools")
async def list_mcp_tools():
    """列出所有 MCP 工具。"""
    if not _mcp_client:
        return {"tools": [], "total": 0}
    tools = _mcp_client.list_tools()
    result = []
    for t in tools:
        func = t.get("function", {})
        result.append({
            "name": func.get("name", ""),
            "description": func.get("description", ""),
        })
    return {"tools": result, "total": len(result)}
