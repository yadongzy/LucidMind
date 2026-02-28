"""Skills Hub — PluginHub 搜索与安装。

拆分自 skills/__init__.py，管理远程/本地插件索引和安装流程。
"""

import json
import pathlib
import urllib.request

from logs import get_logger
from skills.registry import _SKILLS_DIR, _validate_plugin_name

logger = get_logger("skills.hub")

_PLUGIN_HUB_URL = "https://raw.githubusercontent.com/lucidmind-plugins/registry/main/registry.json"
_LOCAL_REGISTRY_PATH = pathlib.Path(__file__).parent.parent / "registry.json"
_registry_cache: list[dict] = []
_registry_cache_time: float = 0


def refresh_hub_registry() -> list[dict]:
    """从远程拉取 PluginHub 插件索引，远程不可用时回退到本地 registry.json。"""
    import time
    global _registry_cache, _registry_cache_time
    # 5分钟缓存
    if _registry_cache and (time.time() - _registry_cache_time) < 300:
        return _registry_cache
    # 1. 尝试远程
    try:
        req = urllib.request.Request(_PLUGIN_HUB_URL, headers={"User-Agent": "LucidMind/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            _registry_cache = data.get("plugins", [])
            _registry_cache_time = time.time()
            logger.info(f"📦 PluginHub 索引已更新(远程): {len(_registry_cache)} 个插件")
            return _registry_cache
    except Exception as e:
        logger.warning(f"📦 PluginHub 远程索引拉取失败: {e}，尝试本地回退")
    # 2. 回退到本地 registry.json
    if _LOCAL_REGISTRY_PATH.exists():
        try:
            data = json.loads(_LOCAL_REGISTRY_PATH.read_text("utf-8"))
            _registry_cache = data.get("plugins", [])
            _registry_cache_time = time.time()
            logger.info(f"📦 PluginHub 索引已加载(本地): {len(_registry_cache)} 个插件")
        except Exception as e:
            logger.warning(f"📦 PluginHub 本地索引解析失败: {e}")
    return _registry_cache


def search_hub(query: str) -> list[dict]:
    """搜索 PluginHub（按名称、工具名、关键词匹配）。"""
    hub = refresh_hub_registry()
    q = query.lower()
    results = []
    for p in hub:
        text = f"{p.get('name','')} {' '.join(p.get('tools',[]))} {' '.join(p.get('keywords',[]))} {p.get('description','')}".lower()
        if q in text:
            results.append(p)
    return results


def install_from_hub(name: str) -> dict:
    """从 PluginHub 安装插件到 skills/ 目录。

    优先检查本地是否已存在（已有则直接启用+热加载），否则从远程下载。
    """
    if not _validate_plugin_name(name):
        return {"success": False, "error": f"插件名不合法(仅允许 a-z0-9_- 且长度≤1-64): {name}"}
    hub = refresh_hub_registry()
    plugin_info = next((p for p in hub if p.get("name") == name), None)
    if not plugin_info:
        return {"success": False, "error": f"PluginHub 中未找到插件: {name}"}

    target_dir = _SKILLS_DIR / name

    # 1. 本地已存在 → 安全扫描 + 启用+热加载
    if (target_dir / "manifest.json").exists() and (target_dir / "main.py").exists():
        # 安全扫描
        from skills.skill_scanner import scan_skill_directory
        scan = scan_skill_directory(target_dir)
        if scan["block"]:
            logger.warning(f"🚫 插件 {name} 安全扫描未通过，拒绝启用: {scan['summary']}")
            return {"success": False, "error": f"安全扫描未通过: {scan['summary']}", "scan": scan}
        # 确保 manifest 中 enabled=true
        try:
            manifest = json.loads((target_dir / "manifest.json").read_text("utf-8"))
            if not manifest.get("enabled", True):
                manifest["enabled"] = True
                (target_dir / "manifest.json").write_text(
                    json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass
        from skills.reload import hot_reload, _mark_new_skill_sensitive, _auto_generate_mcp_server
        reload_result = hot_reload()
        _mark_new_skill_sensitive(manifest.get("tools", []))
        _auto_generate_mcp_server(name)
        logger.info(f"📦 插件已启用(本地已有): {name} | {scan['summary']}")
        return {"success": True, "result": f"插件 {name} 已启用(本地已有)，热加载完成: {reload_result}", "scan": scan}

    # 2. 本地不存在 → 从远程下载
    download_url = plugin_info.get("download_url", "")
    if not download_url:
        return {"success": False, "error": f"插件 {name} 没有下载地址且本地不存在"}

    target_dir.mkdir(parents=True, exist_ok=True)

    try:
        for fname in ["manifest.json", "main.py"]:
            url = f"{download_url.rstrip('/')}/{fname}"
            req = urllib.request.Request(url, headers={"User-Agent": "LucidMind/1.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                content = resp.read().decode("utf-8")
                (target_dir / fname).write_text(content, encoding="utf-8")

        # 安全扫描（下载后、热加载前）
        from skills.skill_scanner import scan_skill_directory
        scan = scan_skill_directory(target_dir)
        if scan["block"]:
            import shutil
            shutil.rmtree(target_dir, ignore_errors=True)
            logger.warning(f"🚫 插件 {name} 安全扫描未通过，已删除: {scan['summary']}")
            return {"success": False, "error": f"安全扫描未通过，已拒绝安装: {scan['summary']}", "scan": scan}

        # 标记为 sandboxed（子进程隔离）+ SENSITIVE（首次确认）
        try:
            _m = json.loads((target_dir / "manifest.json").read_text("utf-8"))
            _m["trust_level"] = "sandboxed"
            (target_dir / "manifest.json").write_text(
                json.dumps(_m, ensure_ascii=False, indent=2), encoding="utf-8")
            from skills.reload import _mark_new_skill_sensitive
            _mark_new_skill_sensitive(_m.get("tools", []))
        except Exception:
            pass
        from skills.reload import hot_reload, _auto_generate_mcp_server
        _auto_generate_mcp_server(name)
        reload_result = hot_reload()
        logger.info(f"📦 插件已安装: {name} → {target_dir} | {scan['summary']}")
        return {"success": True, "result": f"插件 {name} 已安装到 {target_dir}，热加载完成: {reload_result}", "scan": scan}
    except Exception as e:
        return {"success": False, "error": f"安装失败: {e}"}
