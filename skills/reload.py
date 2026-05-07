"""Skills Reload — 热加载 + MCP 生成 + 安全标记。

拆分自 skills/__init__.py，管理插件的运行时更新。
"""

import sys

from logs import get_logger
from skills.registry import _registry

logger = get_logger("skills.reload")

# --- 热加载 ---

_tool_adapter_ref = None  # 由 api/main.py 注入 CompositeToolAdapter 引用


def set_tool_adapter_ref(adapter):
    """注入 CompositeToolAdapter 引用，用于热加载时更新。"""
    global _tool_adapter_ref
    _tool_adapter_ref = adapter


def hot_reload() -> dict:
    """热加载：重新扫描 skills/ 目录，更新工具列表（不重启服务器）。"""
    # 清除已加载的 skills 子模块缓存（保留框架模块，只清除实际插件模块）
    _FRAMEWORK = frozenset({
        "skills", "skills.registry", "skills.discovery", "skills.reload",
        "skills.hub", "skills.token_budget", "skills.loader",
        "skills.skill_scanner", "skills.skill_creator", "skills.mcp_wrapper",
        "skills.discovery_safety",
    })
    to_remove = [k for k in sys.modules if k.startswith("skills.") and k not in _FRAMEWORK]
    for k in to_remove:
        del sys.modules[k]
    # 重新发现
    from skills.discovery import discover_skills
    new_adapters = discover_skills()
    # 如果有 CompositeToolAdapter 引用，更新其 adapters 列表
    if _tool_adapter_ref and hasattr(_tool_adapter_ref, '_adapters'):
        # 保留内建工具（非 skills 的），替换 skills 部分
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
