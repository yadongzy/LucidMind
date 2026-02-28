"""Skills Registry — 共享状态、验证、CRUD 操作。

拆分自 skills/__init__.py，管理插件注册表的核心状态。
"""

import json
import pathlib
import re

from logs import get_logger

logger = get_logger("skills.registry")

_SKILLS_DIR = pathlib.Path(__file__).parent

# 全局插件注册表：name → PluginInfo
_registry: dict[str, dict] = {}

_PLUGIN_NAME_RE = re.compile(r'^[a-z0-9][a-z0-9_-]{0,63}$')


def _validate_plugin_name(name: str) -> bool:
    """插件名安全验证：拒绝路径穿越、特殊字符、超长名称。"""
    if not name or not _PLUGIN_NAME_RE.match(name):
        return False
    # 双重保护：resolve 后确认仍在 skills 目录内
    target = (_SKILLS_DIR / name).resolve()
    if not str(target).startswith(str(_SKILLS_DIR.resolve())):
        return False
    return True


_BUILTIN_PLUGINS = frozenset({
    "bookmarks", "calculator", "clipboard", "code_runner", "daily_digest",
    "docker_ops", "email_sender", "git_helper", "github_ops", "identity",
    "knowledge_base", "notes", "project_context", "reminder", "weather",
    "web_monitor", "discovery_safety", "skill_creator", "skill_scanner",
})


def is_builtin(name: str) -> bool:
    """判断是否为内置插件。"""
    return name in _BUILTIN_PLUGINS


def get_registry() -> dict[str, dict]:
    """返回插件注册表（供API使用，排除adapter实例和大文本内容）。"""
    _STRIP_KEYS = {"adapters", "prompt_content"}
    result = {}
    for name, info in _registry.items():
        safe = {k: v for k, v in info.items() if k not in _STRIP_KEYS}
        result[name] = safe
    return result


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
