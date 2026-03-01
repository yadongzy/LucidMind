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
        self._safety_guard = None
        self._rebuild_map()

    def set_safety_guard(self, guard) -> None:
        """注入 ToolSafetyGuard，execute() 将在路由前调用 guard.check()。"""
        self._safety_guard = guard

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
        """路由到对应的适配器执行（经过安全审批 + 诊断记录 + 懒加载）。"""
        import time as _time
        _t0 = _time.time()
        adapter = self._tool_map.get(tool_name)
        if not adapter:
            # 懒加载 fallback：检查 loader 注册表中是否有未加载的匹配插件
            adapter = self._try_lazy_load(tool_name)
        if not adapter:
            self._record_diagnostic(tool_name, "failure", 0, "未知工具", session_id=session_id)
            return {"success": False, "result": None, "error": f"未知工具: {tool_name}"}
        # Safety by Default: 执行前经过 ToolSafetyGuard 审批
        if self._safety_guard:
            try:
                check = await self._safety_guard.check(session_id, tool_name, params)
                if not check.get("approved"):
                    reason = check.get("reason", "用户拒绝或审批超时")
                    logger.warning(f"工具被安全审批拦截: {tool_name} — {reason}")
                    self._record_diagnostic(tool_name, "blocked", (_time.time() - _t0) * 1000, reason, session_id=session_id)
                    return {"success": False, "result": None, "error": f"安全审批未通过: {reason}", "blocked": True}
            except Exception as e:
                logger.error(f"安全审批异常(放行): {tool_name} — {e}")
        result = await adapter.execute(tool_name, params)
        duration = (_time.time() - _t0) * 1000
        status = "success" if result.get("success") else "failure"
        error = result.get("error") if not result.get("success") else None
        self._record_diagnostic(tool_name, status, duration, error, session_id=session_id)
        return result

    def _try_lazy_load(self, tool_name: str):
        """尝试从 loader 注册表中找到并加载包含该工具的插件。"""
        try:
            from skills.loader import find_plugin_by_tool, layer3_full_load, get_meta_registry
            plugin_name = find_plugin_by_tool(tool_name)
            if not plugin_name:
                return None
            meta_reg = get_meta_registry()
            meta = meta_reg.get(plugin_name)
            if not meta or meta.status not in ("registered",):
                return None
            adapters = layer3_full_load(plugin_name)
            if adapters:
                for a in adapters:
                    if a not in self._adapters:
                        self._adapters.append(a)
                self._rebuild_map()
                return self._tool_map.get(tool_name)
        except Exception as e:
            logger.debug(f"懒加载失败 [{tool_name}]: {e}")
        return None

    @staticmethod
    def _record_diagnostic(tool_name: str, status: str, duration_ms: float,
                           error: str | None = None, session_id: str = "") -> None:
        """记录工具调用诊断事件（失败不影响主流程）。"""
        try:
            from diagnostics import record_event
            record_event(
                category="tool_call", action="execute", status=status,
                duration_ms=duration_ms, input_summary=f"tool={tool_name}",
                output_summary=status, error=error,
                metadata={"tool_name": tool_name, "session_id": session_id},
                level="warning" if status != "success" else "info",
            )
        except Exception:
            pass
