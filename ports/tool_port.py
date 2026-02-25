"""Tool Port — 执行工具的接口."""

from abc import ABC, abstractmethod
from typing import Any


class ToolPort(ABC):
    """工具执行端口。Brain 通过此接口调用任何工具。"""

    @abstractmethod
    async def execute(self, tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
        """执行指定工具。

        Args:
            tool_name: 工具名称
            params: 工具参数

        Returns:
            {"success": bool, "result": Any, "error": str | None}
        """
        ...

    @abstractmethod
    def list_tools(self) -> list[dict[str, Any]]:
        """列出所有可用工具及其定义（供 LLM 使用）。"""
        ...
