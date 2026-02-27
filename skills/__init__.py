"""Skills Plugin System — 标准化插件协议。

## 插件目录结构（推荐）：
    skills/my_plugin/
        manifest.json    # 插件描述（name, version, tools, enabled...）
        main.py          # 入口文件，导出 XxxAdapter 类

## 旧格式兼容：
    skills/my_tool.py    # 单文件插件（无manifest）

manifest.json 示例:
    {
      "name": "clipboard",
      "version": "1.0.0",
      "description": "系统剪贴板读写",
      "entry": "main.py",
      "tools": ["clipboard_read", "clipboard_write"],
      "platform": ["darwin"],
      "dependencies": [],
      "enabled": true
    }
"""

import importlib
import importlib.util
import json
import pathlib
import platform
from typing import Any

from logs import get_logger

logger = get_logger("skills")

_SKILLS_DIR = pathlib.Path(__file__).parent

# 全局插件注册表：name → PluginInfo
_registry: dict[str, dict] = {}

_PLUGIN_NAME_RE = __import__('re').compile(r'^[a-z0-9][a-z0-9_-]{0,63}$')


def _validate_plugin_name(name: str) -> bool:
    """插件名安全验证：拒绝路径穿越、特殊字符、超长名称。"""
    if not name or not _PLUGIN_NAME_RE.match(name):
        return False
    # 双重保护：resolve 后确认仍在 skills 目录内
    target = (_SKILLS_DIR / name).resolve()
    if not str(target).startswith(str(_SKILLS_DIR.resolve())):
        return False
    return True


def _load_adapter_from_file(py_path: pathlib.Path, module_name: str) -> list[Any]:
    """从Python文件加载所有 Adapter 类实例。"""
    adapters = []
    spec = importlib.util.spec_from_file_location(module_name, py_path)
    if not spec or not spec.loader:
        return adapters
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    for attr_name in dir(mod):
        if attr_name.endswith("Adapter") and attr_name != "ToolPort":
            cls = getattr(mod, attr_name)
            if hasattr(cls, "list_tools") and hasattr(cls, "execute"):
                adapters.append(cls())
    return adapters


def discover_skills() -> list[Any]:
    """扫描 skills/ 目录，加载所有插件（manifest目录 + 旧格式单文件）。"""
    global _registry
    _registry = {}
    all_adapters = []
    current_platform = platform.system().lower()

    import time as _time
    # 1. 扫描子目录（新格式：含 manifest.json）
    for sub_dir in sorted(_SKILLS_DIR.iterdir()):
        if not sub_dir.is_dir() or sub_dir.name.startswith("_"):
            continue
        manifest_path = sub_dir / "manifest.json"
        if not manifest_path.exists():
            continue
        try:
            # Safety by Default: 加载前安全检查
            from skills.discovery_safety import check_plugin_safety
            safety = check_plugin_safety(sub_dir)
            if safety["blocked"]:
                logger.warning(f"🛡️ 插件安全阻断: {sub_dir.name} — {safety['blocked_reason']}")
                _registry[sub_dir.name] = {"name": sub_dir.name, "status": "security_blocked",
                                           "security": safety, "adapters": []}
                continue

            manifest = json.loads(manifest_path.read_text("utf-8"))
            name = manifest.get("name", sub_dir.name)
            if not manifest.get("enabled", True):
                logger.info(f"⏸️  插件已禁用: {name}")
                _registry[name] = {**manifest, "status": "disabled", "adapters": [], "security": safety}
                continue
            # 平台检查（"all" 匹配所有平台）
            plats = manifest.get("platform", [])
            if isinstance(plats, str):
                plats = [plats]
            if plats and "all" not in [p.lower() for p in plats] and current_platform not in [p.lower() for p in plats]:
                logger.info(f"⏭️  插件跳过(平台不匹配): {name} 需要 {plats}")
                _registry[name] = {**manifest, "status": "platform_skip", "adapters": []}
                continue
            entry = manifest.get("entry", "main.py")
            entry_path = sub_dir / entry
            if not entry_path.exists():
                logger.warning(f"❌ 插件入口不存在: {name}/{entry}")
                continue
            trust_level = manifest.get("trust_level", "audited")
            if trust_level == "sandboxed":
                # Level 2: 子进程隔离执行
                from adapters.tools.subprocess_skill import SubprocessSkillAdapter
                adapter = SubprocessSkillAdapter(sub_dir, manifest)
                adapters = [adapter]
                tools = manifest.get("tools", [])
                mode = "🔒subprocess"
            else:
                # Level 0/1: 进程内执行
                module_name = f"skills.{sub_dir.name}.{entry_path.stem}"
                adapters = _load_adapter_from_file(entry_path, module_name)
                tools = []
                for a in adapters:
                    tools.extend(t["function"]["name"] for t in a.list_tools())
                mode = "⚡in-process"
            all_adapters.extend(adapters)
            _registry[name] = {**manifest, "status": "loaded", "tools_actual": tools,
                               "adapters": adapters, "security": safety, "trust_level": trust_level}
            logger.info(f"✅ 加载插件: {name} v{manifest.get('version', '?')} [{mode}] → {', '.join(tools)}")
            try:
                from diagnostics import record_event
                record_event("plugin_load", "discover", "success", 0, input_summary=f"plugin={name}", output_summary=f"tools={','.join(tools)}")
            except Exception:
                pass
        except Exception as e:
            logger.warning(f"❌ 加载插件失败: {sub_dir.name} — {e}")
            try:
                from diagnostics import record_event
                record_event("plugin_load", "discover", "failure", 0, input_summary=f"plugin={sub_dir.name}", error=str(e)[:200])
            except Exception:
                pass

    # 2. 扫描单文件（旧格式兼容）
    for py_file in sorted(_SKILLS_DIR.glob("*.py")):
        if py_file.name.startswith("_"):
            continue
        name = py_file.stem
        if name in _registry:
            continue
        try:
            module_name = f"skills.{name}"
            adapters = _load_adapter_from_file(py_file, module_name)
            all_adapters.extend(adapters)
            tools = []
            for a in adapters:
                tools.extend(t["function"]["name"] for t in a.list_tools())
            _registry[name] = {
                "name": name, "version": "0.0.0", "description": f"旧格式插件: {name}",
                "status": "loaded", "tools_actual": tools, "adapters": adapters, "enabled": True,
                "legacy": True,
            }
            logger.info(f"✅ 加载技能(旧格式): {name} → {', '.join(tools)}")
        except Exception as e:
            logger.warning(f"❌ 加载技能失败: {py_file.name} — {e}")

    logger.info(f"🎯 共加载 {len(all_adapters)} 个插件适配器 ({len(_registry)} 个插件)")
    return all_adapters


def get_registry() -> dict[str, dict]:
    """返回插件注册表（供API使用，排除adapter实例）。"""
    result = {}
    for name, info in _registry.items():
        safe = {k: v for k, v in info.items() if k != "adapters"}
        result[name] = safe
    return result


_BUILTIN_PLUGINS = frozenset({
    "bookmarks", "calculator", "clipboard", "code_runner", "daily_digest",
    "docker_ops", "email_sender", "git_helper", "github_ops", "identity",
    "knowledge_base", "notes", "project_context", "reminder", "weather",
    "web_monitor", "discovery_safety", "skill_creator", "skill_scanner",
})


def is_builtin(name: str) -> bool:
    """判断是否为内置插件。"""
    return name in _BUILTIN_PLUGINS


def delete_plugin(name: str) -> dict:
    """删除非内置插件（删除目录 + 热加载）。"""
    import shutil
    if not _validate_plugin_name(name):
        return {"success": False, "error": f"插件名不合法: {name}"}
    if is_builtin(name):
        return {"success": False, "error": f"内置插件不可删除: {name}"}
    plugin_dir = _SKILLS_DIR / name
    if not plugin_dir.exists():
        # 也检查旧格式单文件
        py_file = _SKILLS_DIR / f"{name}.py"
        if py_file.exists():
            return {"success": False, "error": f"旧格式系统模块不可删除: {name}"}
        return {"success": False, "error": f"插件不存在: {name}"}
    try:
        shutil.rmtree(plugin_dir)
        logger.info(f"🗑️ 插件已删除: {name}")
        return {"success": True}
    except Exception as e:
        logger.error(f"删除插件失败: {name} — {e}")
        return {"success": False, "error": str(e)}


def set_plugin_enabled(name: str, enabled: bool) -> bool:
    """启用/禁用插件（修改manifest.json）。"""
    plugin_dir = _SKILLS_DIR / name
    manifest_path = plugin_dir / "manifest.json"
    if not manifest_path.exists():
        return False
    manifest = json.loads(manifest_path.read_text("utf-8"))
    manifest["enabled"] = enabled
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return True


# --- 热加载 ---

_tool_adapter_ref = None  # 由 api/main.py 注入 CompositeToolAdapter 引用


def set_tool_adapter_ref(adapter):
    """注入 CompositeToolAdapter 引用，用于热加载时更新。"""
    global _tool_adapter_ref
    _tool_adapter_ref = adapter


def hot_reload() -> dict:
    """热加载：重新扫描 skills/ 目录，更新工具列表（不重启服务器）。"""
    import sys
    # 清除已加载的 skills 子模块缓存
    to_remove = [k for k in sys.modules if k.startswith("skills.") and k != "skills"]
    for k in to_remove:
        del sys.modules[k]
    # 重新发现
    new_adapters = discover_skills()
    # 如果有 CompositeToolAdapter 引用，更新其 adapters 列表
    if _tool_adapter_ref and hasattr(_tool_adapter_ref, '_adapters'):
        # 保留内建工具（非 skills 的），替换 skills 部分
        builtin = [a for a in _tool_adapter_ref._adapters
                   if not any(a is ra for info in _registry.values() for ra in info.get("adapters", []))]
        # 不行，全部 discover 出来的都是新实例，用类型判断
        # 简单方案：直接用内建 + 新 skills
        from adapters.tools.composite import CompositeToolAdapter
        if hasattr(_tool_adapter_ref, '_builtin_tools'):
            _tool_adapter_ref._adapters = _tool_adapter_ref._builtin_tools + new_adapters
        else:
            _tool_adapter_ref._adapters = new_adapters
        # 重建工具缓存
        if hasattr(_tool_adapter_ref, '_refresh'):
            _tool_adapter_ref._refresh()
    total_tools = sum(len(info.get("tools_actual", [])) for info in _registry.values())
    logger.info(f"🔄 热加载完成: {len(_registry)} 个插件, {total_tools} 个工具")
    return {"plugins": len(_registry), "tools": total_tools, "adapters": len(new_adapters)}


def _auto_generate_mcp_server(skill_name: str) -> None:
    """为新安装/创建的 skill 自动生成 MCP Server wrapper（Phase 3）。"""
    try:
        from skills.mcp_wrapper import generate_mcp_server
        result = generate_mcp_server(skill_name)
        if result.get("success"):
            logger.info(f"🔌 MCP Server 已生成: {skill_name} → {result['path']}")
        else:
            logger.warning(f"MCP Server 生成失败 [{skill_name}]: {result.get('error')}")
    except Exception as e:
        logger.warning(f"MCP Server 生成异常 [{skill_name}]: {e}")


def _mark_new_skill_sensitive(tool_names: list[str]) -> None:
    """将新安装/创建的 skill 工具标记为 SENSITIVE（渐进信任 Phase 1）。"""
    if not tool_names:
        return
    try:
        from adapters.tools.tool_safety import get_safety_guard
        get_safety_guard().mark_skill_tools_sensitive(tool_names)
    except Exception as e:
        logger.warning(f"标记新 skill 工具为 SENSITIVE 失败: {e}")


# --- PluginHub 自动搜索安装 ---

import urllib.request

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
        return {"success": False, "error": f"插件名不合法(\u4ec5允许 a-z0-9_- 且长度\u22641-64): {name}"}
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
            _mark_new_skill_sensitive(_m.get("tools", []))
        except Exception:
            pass
        _auto_generate_mcp_server(name)
        reload_result = hot_reload()
        logger.info(f"📦 插件已安装: {name} → {target_dir} | {scan['summary']}")
        return {"success": True, "result": f"插件 {name} 已安装到 {target_dir}，热加载完成: {reload_result}", "scan": scan}
    except Exception as e:
        return {"success": False, "error": f"安装失败: {e}"}
