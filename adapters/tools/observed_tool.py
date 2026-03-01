"""Observed Tool Adapter — 装饰器模式，为工具调用添加观察记录。

包装任意 ToolPort 实现，在执行前后自动调用 ToolObserver.record()。
不修改 brain.py，不修改原工具逻辑。

使用方式（api/startup.py 或 cli.py）:
    tool_adapter = ObservedToolAdapter(original_tool, observer=learning_adapter._tool_observer)
"""

import time
from typing import Any

from ports.tool_port import ToolPort
from memory.tool_observer import ToolObserver
from logs import get_logger

logger = get_logger("tools.observed")


class ObservedToolAdapter(ToolPort):
    """在原有工具执行基础上自动记录观察数据的装饰器。"""

    def __init__(self, inner: ToolPort, observer: ToolObserver | None = None):
        self._inner = inner
        self._observer = observer
        self._current_session_id = ""

    def set_session_id(self, session_id: str) -> None:
        """设置当前会话 ID（用于观察记录关联）。"""
        self._current_session_id = session_id

    async def execute(self, tool_name: str, params: dict[str, Any],
                      session_id: str = "", **kwargs) -> dict[str, Any]:
        """执行工具并记录观察。"""
        sid = session_id or self._current_session_id
        start = time.monotonic()
        try:
            result = await self._inner.execute(tool_name, params,
                                                session_id=session_id, **kwargs)
            elapsed_ms = (time.monotonic() - start) * 1000
            success = result.get("success", True) if isinstance(result, dict) else True

            if self._observer:
                self._observer.record(
                    tool_name=tool_name,
                    input_args=params,
                    output=str(result.get("result", ""))[:200] if isinstance(result, dict) else str(result)[:200],
                    success=success,
                    duration_ms=elapsed_ms,
                    session_id=sid,
                )

            return result
        except Exception as e:
            elapsed_ms = (time.monotonic() - start) * 1000
            if self._observer:
                self._observer.record(
                    tool_name=tool_name,
                    input_args=params,
                    output=str(e)[:200],
                    success=False,
                    duration_ms=elapsed_ms,
                    session_id=sid,
                )
            raise

    def get_tools(self) -> list[dict]:
        """透传内部工具列表。"""
        return self._inner.get_tools()

    def __getattr__(self, name: str) -> Any:
        """透传所有其他属性到内部适配器。"""
        return getattr(self._inner, name)
