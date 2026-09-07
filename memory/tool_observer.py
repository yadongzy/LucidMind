"""Tool Observer — 工具级观察采集（对标 claude-mem observation handler）。

记录每次工具调用的结构化数据:
- tool_name: 工具名称
- input_summary: 输入参数摘要
- output_summary: 输出结果摘要
- success: 是否成功
- duration_ms: 耗时（毫秒）

存储到 MemoryStore 的 "observations" 集合，用于:
1. 工具使用模式分析（哪些工具常用/常失败）
2. 辅助经验提取（reflect_on_session 可参考）
3. 上下文丰富（检索时提供工具使用历史）
"""

import json
import time
from datetime import datetime, timezone
from typing import Any

from logs import get_logger

logger = get_logger("memory.tool_observer")

# 输出摘要最大长度
_MAX_SUMMARY_LEN = 200


def _summarize(text: str, max_len: int = _MAX_SUMMARY_LEN) -> str:
    """截断文本为摘要。"""
    if not text:
        return ""
    text = str(text).strip()
    if len(text) <= max_len:
        return text
    return text[:max_len - 3] + "..."


class ToolObserver:
    """工具调用观察记录器。

    使用方式:
        observer = ToolObserver(store)
        observer.record(tool_name, input_args, output, success, duration_ms, session_id)
    """

    def __init__(self, store=None, max_observations_per_session: int = 50):
        self._store = store
        self._max_per_session = max_observations_per_session
        self._session_counts: dict[str, int] = {}

    def record(self, tool_name: str, input_args: dict | str | None,
               output: str | None, success: bool, duration_ms: float = 0.0,
               session_id: str = "") -> str | None:
        """记录一次工具调用观察。

        Args:
            tool_name: 工具名称
            input_args: 输入参数
            output: 输出结果
            success: 是否成功
            duration_ms: 耗时毫秒
            session_id: 会话 ID

        Returns:
            记忆 ID，失败返回 None
        """
        if not self._store:
            return None

        # 限流: 每会话最多记录 N 条
        count = self._session_counts.get(session_id, 0)
        if count >= self._max_per_session:
            return None
        self._session_counts[session_id] = count + 1

        # 格式化输入摘要
        if isinstance(input_args, dict):
            input_summary = _summarize(json.dumps(input_args, ensure_ascii=False))
        else:
            input_summary = _summarize(str(input_args) if input_args else "")

        output_summary = _summarize(str(output) if output else "")

        # 构建结构化内容
        status = "✅" if success else "❌"
        content = (
            f"[Tool] {tool_name} {status} "
            f"({duration_ms:.0f}ms)\n"
            f"Input: {input_summary}\n"
            f"Output: {output_summary}"
        )

        metadata = {
            "tool_name": tool_name,
            "success": success,
            "duration_ms": round(duration_ms, 1),
            "session_id": session_id,
            "category": "tool_observation",
            "helpful_count": 0,
            "harmful_count": 0,
        }

        try:
            mid = self._store.add("observations", content,
                                  metadata=metadata, skip_noise_filter=True)
            if mid:
                logger.debug(f"工具观察记录: {tool_name} {status} ({duration_ms:.0f}ms)")
            return mid
        except Exception as e:
            logger.warning(f"工具观察记录失败: {e}")
            return None

    def get_tool_stats(self, tool_name: str | None = None,
                       limit: int = 20) -> list[dict[str, Any]]:
        """获取工具使用统计。

        Args:
            tool_name: 指定工具名，None 返回所有
            limit: 最大返回数

        Returns:
            观察记录列表
        """
        if not self._store:
            return []

        observations = self._store.get_all(collection="observations", limit=500)
        results = []
        for obs in observations:
            meta = obs.metadata or {}
            if tool_name and meta.get("tool_name") != tool_name:
                continue
            results.append({
                "id": obs.id,
                "tool_name": meta.get("tool_name", ""),
                "success": meta.get("success", True),
                "duration_ms": meta.get("duration_ms", 0),
                "session_id": meta.get("session_id", ""),
                "content": obs.content,
                "created_at": obs.created_at,
            })

        return results[:limit]

    def get_failure_patterns(self, min_failures: int = 2) -> dict[str, int]:
        """获取失败频率高的工具，用于学习优化。

        Returns:
            {tool_name: failure_count} 字典
        """
        if not self._store:
            return {}

        observations = self._store.get_all(collection="observations", limit=500)
        failures: dict[str, int] = {}
        for obs in observations:
            meta = obs.metadata or {}
            if not meta.get("success", True):
                name = meta.get("tool_name", "unknown")
                failures[name] = failures.get(name, 0) + 1

        return {k: v for k, v in failures.items() if v >= min_failures}

    def clear_session(self, session_id: str) -> None:
        """清理会话计数器。"""
        self._session_counts.pop(session_id, None)
