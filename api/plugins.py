"""插件管理 API — 列表/启用/禁用/热加载/PluginHub搜索安装。"""

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/plugins", tags=["plugins"])


@router.get("")
async def list_plugins():
    """列出所有已注册的插件。"""
    from skills import get_registry, is_builtin
    registry = get_registry()
    plugins = []
    for name, info in registry.items():
        plugins.append({
            "name": info.get("name", name),
            "version": info.get("version", "0.0.0"),
            "description": info.get("description", ""),
            "status": info.get("status", "unknown"),
            "enabled": info.get("enabled", True),
            "tools": info.get("tools_actual", info.get("tools", [])),
            "platform": info.get("platform", []),
            "legacy": info.get("legacy", False),
            "builtin": is_builtin(info.get("name", name)),
        })
    return {"plugins": plugins, "total": len(plugins)}


@router.get("/{name}")
async def get_plugin(name: str):
    """获取单个插件详情。"""
    from skills import get_registry
    registry = get_registry()
    if name not in registry:
        raise HTTPException(status_code=404, detail=f"插件不存在: {name}")
    info = registry[name]
    return {
        "name": info.get("name", name),
        "version": info.get("version", "0.0.0"),
        "description": info.get("description", ""),
        "author": info.get("author", ""),
        "status": info.get("status", "unknown"),
        "enabled": info.get("enabled", True),
        "tools": info.get("tools_actual", info.get("tools", [])),
        "platform": info.get("platform", []),
        "dependencies": info.get("dependencies", []),
        "hooks": info.get("hooks", {}),
        "legacy": info.get("legacy", False),
    }


@router.put("/{name}/toggle")
async def toggle_plugin(name: str, body: dict):
    """启用/禁用插件（立即生效：修改manifest + 自动热加载）。"""
    from skills import set_plugin_enabled, hot_reload
    enabled = body.get("enabled", True)
    ok = set_plugin_enabled(name, enabled)
    if not ok:
        raise HTTPException(status_code=404, detail=f"插件不存在或不支持切换: {name}")
    # 自动热加载，让变更立即生效
    hot_reload()
    action = "启用" if enabled else "禁用"
    return {"status": "ok", "message": f"插件 {name} 已{action}（已立即生效）"}


@router.delete("/{name}")
async def delete_plugin(name: str):
    """删除非内置插件（删除目录 + 自动热加载）。"""
    from skills import delete_plugin as _delete, hot_reload, is_builtin
    if is_builtin(name):
        raise HTTPException(status_code=403, detail=f"内置插件不可删除: {name}")
    result = _delete(name)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "删除失败"))
    hot_reload()
    return {"status": "ok", "message": f"插件 {name} 已删除"}


@router.post("/reload")
async def reload_plugins():
    """热加载：重新扫描 skills/ 目录，不重启服务器。"""
    from skills import hot_reload
    result = hot_reload()
    return {"status": "ok", **result}


@router.get("/hub/search")
async def search_hub(q: str = ""):
    """搜索 PluginHub 插件。"""
    from skills import search_hub as _search
    if not q:
        from skills import refresh_hub_registry
        results = refresh_hub_registry()
    else:
        results = _search(q)
    return {"results": results, "total": len(results)}


@router.post("/hub/install")
async def install_from_hub(body: dict):
    """从 PluginHub 安装插件并热加载。"""
    from skills import install_from_hub as _install, _validate_plugin_name
    name = body.get("name", "")
    if not name:
        raise HTTPException(status_code=400, detail="请提供插件名称")
    if not _validate_plugin_name(name):
        raise HTTPException(status_code=400, detail=f"插件名不合法: {name}")
    result = _install(name)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "安装失败"))
    return {"status": "ok", "message": result.get("result", f"插件 {name} 安装成功")}
