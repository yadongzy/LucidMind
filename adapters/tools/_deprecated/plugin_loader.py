"""S21: 插件系统 — 从 plugins/ 目录动态加载第三方工具。

插件格式: plugins/xxx.py 中定义 TOOLS 列表和 execute(tool_name, params) 函数。
示例插件:
    TOOLS = [{"type":"function","function":{"name":"my_tool","description":"...","parameters":{...}}}]
    async def execute(tool_name, params): return {"success":True,"result":"...","error":None}
"""
import importlib.util
from pathlib import Path
from typing import Any

from ports.tool_port import ToolPort
from logs import get_logger

logger = get_logger("plugins")

PLUGINS_DIR = Path(__file__).parent.parent.parent / "plugins"


class PluginLoaderAdapter(ToolPort):
    """动态加载 plugins/ 目录下的工具插件。"""

    def __init__(self):
        self._plugins: dict[str, Any] = {}  # tool_name → module
        self._tools: list[dict] = []
        self._load_plugins()

    def _load_plugins(self):
        """扫描 plugins/ 目录，加载所有 .py 插件。"""
        PLUGINS_DIR.mkdir(parents=True, exist_ok=True)
        for f in PLUGINS_DIR.glob("*.py"):
            if f.name.startswith("_"):
                continue
            try:
                spec = importlib.util.spec_from_file_location(f.stem, f)
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                tools = getattr(mod, "TOOLS", [])
                for t in tools:
                    name = t["function"]["name"]
                    self._plugins[name] = mod
                    self._tools.append(t)
                    logger.info(f"插件加载: {f.name} → {name}")
            except Exception as e:
                logger.error(f"插件加载失败: {f.name} — {e}")

    def reload(self):
        """热重载所有插件。"""
        self._plugins.clear()
        self._tools.clear()
        self._load_plugins()

    def list_tools(self) -> list[dict[str, Any]]:
        mgr = {
            "type": "function",
            "function": {
                "name": "manage_plugins",
                "description": (
                    "管理插件系统。action: list(查看已加载插件), "
                    "reload(热重载所有插件), template(获取插件模板)"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": ["list", "reload", "template"],
                        },
                    },
                    "required": ["action"],
                },
            },
        }
        return self._tools + [mgr]

    async def execute(self, tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
        if tool_name == "manage_plugins":
            return await self._manage(params)
        mod = self._plugins.get(tool_name)
        if not mod:
            return {"success": False, "result": None, "error": f"未知插件工具: {tool_name}"}
        try:
            fn = getattr(mod, "execute", None)
            if not fn:
                return {"success": False, "result": None, "error": f"插件 {tool_name} 缺少 execute 函数"}
            import asyncio
            if asyncio.iscoroutinefunction(fn):
                return await fn(tool_name, params)
            return fn(tool_name, params)
        except Exception as e:
            logger.error(f"插件执行失败: {tool_name} — {e}")
            return {"success": False, "result": None, "error": str(e)}

    async def _manage(self, params: dict) -> dict[str, Any]:
        action = params.get("action", "")
        if action == "list":
            plugins = [f"{name} ({getattr(mod, '__file__', '?')})"
                       for name, mod in self._plugins.items()]
            return {"success": True, "result":
                    f"已加载 {len(plugins)} 个插件工具:\n" +
                    ("\n".join(f"- {p}" for p in plugins) or "(无)") +
                    f"\n\n插件目录: {PLUGINS_DIR}"}
        if action == "reload":
            old_count = len(self._plugins)
            self.reload()
            new_count = len(self._plugins)
            logger.info(f"插件热重载: {old_count} → {new_count}")
            return {"success": True, "result":
                    f"插件已重载: {old_count} → {new_count} 个工具"}
        if action == "template":
            tmpl = (
                f'# 插件文件保存到: {PLUGINS_DIR}/your_tool.py\n'
                'TOOLS = [{\n'
                '    "type": "function",\n'
                '    "function": {\n'
                '        "name": "your_tool_name",\n'
                '        "description": "工具描述",\n'
                '        "parameters": {\n'
                '            "type": "object",\n'
                '            "properties": {"input": {"type": "string"}},\n'
                '            "required": ["input"]\n'
                '        }\n'
                '    }\n'
                '}]\n\n'
                'async def execute(tool_name, params):\n'
                '    return {"success": True, "result": "done", "error": None}\n'
            )
            return {"success": True, "result": tmpl}
        return {"success": False, "error": f"未知动作: {action}"}
