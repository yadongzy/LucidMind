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

    # 1. 扫描子目录（新格式：含 manifest.json）
    for sub_dir in sorted(_SKILLS_DIR.iterdir()):
        if not sub_dir.is_dir() or sub_dir.name.startswith("_"):
            continue
        manifest_path = sub_dir / "manifest.json"
        if not manifest_path.exists():
            continue
        try:
            manifest = json.loads(manifest_path.read_text("utf-8"))
            name = manifest.get("name", sub_dir.name)
            if not manifest.get("enabled", True):
                logger.info(f"⏸️  插件已禁用: {name}")
                _registry[name] = {**manifest, "status": "disabled", "adapters": []}
                continue
            # 平台检查
            plats = manifest.get("platform", [])
            if plats and current_platform not in [p.lower() for p in plats]:
                logger.info(f"⏭️  插件跳过(平台不匹配): {name} 需要 {plats}")
                _registry[name] = {**manifest, "status": "platform_skip", "adapters": []}
                continue
            entry = manifest.get("entry", "main.py")
            entry_path = sub_dir / entry
            if not entry_path.exists():
                logger.warning(f"❌ 插件入口不存在: {name}/{entry}")
                continue
            module_name = f"skills.{sub_dir.name}.{entry_path.stem}"
            adapters = _load_adapter_from_file(entry_path, module_name)
            all_adapters.extend(adapters)
            tools = []
            for a in adapters:
                tools.extend(t["function"]["name"] for t in a.list_tools())
            _registry[name] = {**manifest, "status": "loaded", "tools_actual": tools, "adapters": adapters}
            logger.info(f"✅ 加载插件: {name} v{manifest.get('version', '?')} → {', '.join(tools)}")
        except Exception as e:
            logger.warning(f"❌ 加载插件失败: {sub_dir.name} — {e}")

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


# --- PluginHub 自动搜索安装 ---

import urllib.request

_PLUGIN_HUB_URL = "https://raw.githubusercontent.com/lucidmind-plugins/registry/main/registry.json"
_registry_cache: list[dict] = []
_registry_cache_time: float = 0


def refresh_hub_registry() -> list[dict]:
    """从远程拉取 PluginHub 插件索引。"""
    import time
    global _registry_cache, _registry_cache_time
    # 5分钟缓存
    if _registry_cache and (time.time() - _registry_cache_time) < 300:
        return _registry_cache
    try:
        req = urllib.request.Request(_PLUGIN_HUB_URL, headers={"User-Agent": "LucidMind/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            _registry_cache = data.get("plugins", [])
            _registry_cache_time = time.time()
            logger.info(f"📦 PluginHub 索引已更新: {len(_registry_cache)} 个插件")
    except Exception as e:
        logger.warning(f"📦 PluginHub 索引拉取失败: {e}")
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
    """从 PluginHub 下载并安装插件到 skills/ 目录。"""
    hub = refresh_hub_registry()
    plugin_info = next((p for p in hub if p.get("name") == name), None)
    if not plugin_info:
        return {"success": False, "error": f"PluginHub 中未找到插件: {name}"}

    download_url = plugin_info.get("download_url", "")
    if not download_url:
        return {"success": False, "error": f"插件 {name} 没有下载地址"}

    target_dir = _SKILLS_DIR / name
    target_dir.mkdir(parents=True, exist_ok=True)

    try:
        # 下载 manifest.json
        for fname in ["manifest.json", "main.py"]:
            url = f"{download_url.rstrip('/')}/{fname}"
            req = urllib.request.Request(url, headers={"User-Agent": "LucidMind/1.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                content = resp.read().decode("utf-8")
                (target_dir / fname).write_text(content, encoding="utf-8")

        logger.info(f"📦 插件已安装: {name} → {target_dir}")
        return {"success": True, "result": f"插件 {name} 已安装到 {target_dir}"}
    except Exception as e:
        return {"success": False, "error": f"安装失败: {e}"}
