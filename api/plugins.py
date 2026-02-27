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
            "trust_level": info.get("trust_level", "audited"),
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
        "trust_level": info.get("trust_level", "audited"),
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


@router.put("/{name}/trust")
async def set_trust_level(name: str, body: dict):
    """设置插件信任等级（sandboxed ↔ audited），立即生效。"""
    import json
    from pathlib import Path
    from skills import get_registry, hot_reload
    registry = get_registry()
    if name not in registry:
        raise HTTPException(status_code=404, detail=f"插件不存在: {name}")
    level = body.get("trust_level", "")
    if level not in ("sandboxed", "audited"):
        raise HTTPException(status_code=400, detail=f"无效的信任等级: {level}（可选: sandboxed, audited）")
    # 修改 manifest.json
    skills_dir = Path(__file__).resolve().parent.parent / "skills" / name
    manifest_path = skills_dir / "manifest.json"
    if not manifest_path.exists():
        raise HTTPException(status_code=404, detail=f"插件 manifest 不存在: {name}")
    manifest = json.loads(manifest_path.read_text("utf-8"))
    old_level = manifest.get("trust_level", "audited")
    manifest["trust_level"] = level
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    hot_reload()
    return {"status": "ok", "message": f"插件 {name} 信任等级: {old_level} → {level}（已生效）"}


@router.post("/{name}/mcp-wrap")
async def wrap_as_mcp(name: str):
    """为指定插件生成 MCP Server wrapper 并注册。"""
    from skills.mcp_wrapper import register_mcp_server
    result = register_mcp_server(name)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "MCP 封装失败"))
    return {"status": "ok", "config": result.get("config")}


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
