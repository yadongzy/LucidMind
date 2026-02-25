"""Composite Tool Adapter — 聚合多个 ToolPort 实现。

Brain 只认识一个 ToolPort。本适配器将多个工具适配器合并为一个，
Brain 不需要知道背后有几个适配器。符合第一条（架构）和第六条（扩展）。
"""

from typing import Any

from ports.tool_port import ToolPort
from logs import get_logger

logger = get_logger("tools")


class CompositeToolAdapter(ToolPort):
    """聚合多个 ToolPort，对外暴露统一接口。"""

    def __init__(self, adapters: list[ToolPort] | None = None):
        self._adapters: list[ToolPort] = adapters or []
        self._builtin_tools: list[ToolPort] = list(self._adapters)  # 记住内建工具
        self._tool_map: dict[str, ToolPort] = {}
        self._rebuild_map()

    def _refresh(self) -> None:
        """热加载后刷新工具映射。"""
        self._rebuild_map()

    def add(self, adapter: ToolPort) -> None:
        """注册一个新的工具适配器。"""
        self._adapters.append(adapter)
        self._rebuild_map()

    def _rebuild_map(self) -> None:
        """重建 tool_name → adapter 映射。"""
        self._tool_map.clear()
        for adapter in self._adapters:
            for tool_def in adapter.list_tools():
                name = tool_def["function"]["name"]
                if name in self._tool_map:
                    logger.warning(f"工具名冲突: {name}，后注册的覆盖前者")
                self._tool_map[name] = adapter
        logger.info(f"工具注册完成: {list(self._tool_map.keys())}")

    def list_tools(self) -> list[dict[str, Any]]:
        """返回所有适配器的工具定义。"""
        tools = []
        for adapter in self._adapters:
            tools.extend(adapter.list_tools())
        return tools

    def list_tools_for_scope(self, scope: str) -> list[dict[str, Any]]:
        """按场景返回过滤后的工具列表（工具分组，任务逻辑.md §6.6）。"""
        from tool_groups import filter_tools
        return filter_tools(self.list_tools(), scope)

    async def execute(self, tool_name: str, params: dict[str, Any],
                      session_id: str = "") -> dict[str, Any]:
        """路由到对应的适配器执行。"""
        adapter = self._tool_map.get(tool_name)
        if not adapter:
            return {"success": False, "result": None, "error": f"未知工具: {tool_name}"}
        return await adapter.execute(tool_name, params)
