"""Brain 性能工具 — 模块级纯函数，不依赖 Brain 实例。

提供上下文窗口管理、查询复杂度评估、动态工具轮次、工具结果压缩。
从 brain.py 中拆出以遵守规则03行数限制。
"""

# ── 上下文窗口 ───────────────────────────────────────

from brain_config import (
    MIN_TOOL_ROUNDS as _MIN_TOOL_ROUNDS,
    DEFAULT_TOOL_ROUNDS as _DEFAULT_TOOL_ROUNDS,
    MAX_TOOL_ROUNDS as _MAX_TOOL_ROUNDS,
    TOOL_RESULT_MAX_CHARS,
    COMPLEXITY_SEARCH_KEYWORDS, COMPLEXITY_MULTI_STEP_KEYWORDS,
)


# ── 查询复杂度 ─────────────────────────────────────

def estimate_query_complexity(user_input: str, tools: list | None) -> str:
    """估算查询复杂度：simple/medium/complex。"""
    length = len(user_input)
    has_search_keywords = any(k in user_input for k in COMPLEXITY_SEARCH_KEYWORDS)
    has_multi_step = any(k in user_input for k in COMPLEXITY_MULTI_STEP_KEYWORDS)
    if length > 200 or (has_search_keywords and has_multi_step):
        return "complex"
    if length > 50 or has_search_keywords or has_multi_step:
        return "medium"
    return "simple"


def dynamic_max_tool_rounds(user_input: str, tools: list | None) -> int:
    """根据查询复杂度动态决定最大工具轮次。"""
    complexity = estimate_query_complexity(user_input, tools)
    rounds = {
        "simple": _MIN_TOOL_ROUNDS,
        "medium": _DEFAULT_TOOL_ROUNDS,
        "complex": _MAX_TOOL_ROUNDS,
    }
    return rounds.get(complexity, _DEFAULT_TOOL_ROUNDS)


# ── 工具结果压缩 ───────────────────────────────────

def compress_tool_result(result_text: str, max_chars: int = TOOL_RESULT_MAX_CHARS) -> str:
    """即时压缩单个工具结果，保留首尾关键信息。"""
    if len(result_text) <= max_chars:
        return result_text
    head = max_chars * 2 // 3
    tail = max_chars // 3
    return (
        result_text[:head]
        + f"\n...(已压缩，原长{len(result_text)}字符)...\n"
        + result_text[-tail:]
    )
