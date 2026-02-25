"""插件管理 API — 列表/启用/禁用/热加载/PluginHub搜索安装。"""

from fastapi import APIRouter

router = APIRouter(prefix="/api/plugins", tags=["plugins"])


@router.get("")
async def list_plugins():
    """列出所有已注册的插件。"""
    from skills import get_registry
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
        })
    return {"plugins": plugins, "total": len(plugins)}


@router.get("/{name}")
async def get_plugin(name: str):
    """获取单个插件详情。"""
    from skills import get_registry
    registry = get_registry()
    if name not in registry:
        return {"error": f"插件不存在: {name}"}
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
    """启用/禁用插件（需重启生效）。"""
    from skills import set_plugin_enabled
    enabled = body.get("enabled", True)
    ok = set_plugin_enabled(name, enabled)
    if not ok:
        return {"error": f"插件不存在或不支持切换: {name}"}
    action = "启用" if enabled else "禁用"
    return {"status": "ok", "message": f"插件 {name} 已{action}（重启后生效）"}


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
    from skills import install_from_hub as _install
    name = body.get("name", "")
    if not name:
        return {"error": "请提供插件名称"}
    return _install(name)
