"""工具分组 — 按场景选工具集。

设计文档（任务逻辑.md §6.6）定义了4种场景的工具集：
- self_check: introspect, read_file（自检场景，不需要危险工具）
- task: 全部工具（执行任务场景）
- learn: introspect, read_file, teaching, web_search（学习场景）
- repair: introspect, run_command, write_file, read_file（修复场景）

不修改 brain.py / ports/（规则 01, 06）。
由 brain_daemon.py 在不同场景下调用，过滤工具列表。
"""

from typing import Any

from ports.tool_port import ToolPort
from logs import get_logger

logger = get_logger("tools")

# 场景 → 允许的工具名集合（None = 全部工具）
TOOL_GROUPS: dict[str, set[str] | None] = {
    "self_check": {
        "introspect", "read_file", "search_files",
    },
    "task": None,  # 全部工具
    "learn": {
        "introspect", "read_file", "teaching",
        "web_search", "search_files",
    },
    "repair": {
        "introspect", "run_command", "write_file",
        "read_file", "search_files",
    },
}


def filter_tools(all_tools: list[dict], scope: str) -> list[dict]:
    """按场景过滤工具列表。

    Args:
        all_tools: CompositeToolAdapter.list_tools() 的完整列表
        scope: 场景名（self_check / task / learn / repair）

    Returns:
        过滤后的工具定义列表
    """
    allowed = TOOL_GROUPS.get(scope)
    if allowed is None:
        return all_tools  # task 场景：全部工具

    filtered = [
        t for t in all_tools
        if t.get("function", {}).get("name") in allowed
    ]
    logger.debug(
        f"工具分组[{scope}]: {len(all_tools)}→{len(filtered)} "
        f"({', '.join(t['function']['name'] for t in filtered)})"
    )
    return filtered


class ScopedToolProxy(ToolPort):
    """轻量代理：list_tools() 按场景过滤，execute() 委托给原始适配器。

    用于 Daemon 在不同场景下临时限制大脑可用的工具集，
    不修改 brain.py 或 ToolPort 接口（规则 01, 06）。
    """

    def __init__(self, original: ToolPort, scope: str):
        self._original = original
        self._scope = scope

    def list_tools(self) -> list[dict[str, Any]]:
        return filter_tools(self._original.list_tools(), self._scope)

    async def execute(self, tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
        return await self._original.execute(tool_name, params)
