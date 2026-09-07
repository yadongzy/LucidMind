"""Fast Path 分类器 — 简单对话跳过元认知+经验检索+学习检测。

性能优化核心：减少不必要的 LLM 调用次数。
- 简单问候/闲聊 → 0 次额外 LLM 调用（跳过元认知+经验检索+学习检测）
- 知识问答      → 0 次额外 LLM 调用（跳过元认知+学习检测，经验检索用缓存）
- 工具调用型    → 完整链路（元认知+经验检索+学习检测）
"""

import re
from brain_config import (
    GREETING_PATTERNS as _GREETING_PATTERNS,
    TRIVIAL_PATTERNS as _TRIVIAL_PATTERNS,
    TOOL_TRIGGER_KEYWORDS as _TOOL_TRIGGER_KEYWORDS,
    CORRECTION_KEYWORDS as _CORRECTION_KEYWORDS,
    COMPLEX_KEYWORDS,
)


class FastPathResult:
    """快速路径分类结果。"""
    __slots__ = ("category", "skip_metacog", "skip_lessons", "skip_learn_detect", "skip_tools")

    def __init__(self, category: str, skip_metacog: bool = False,
                 skip_lessons: bool = False, skip_learn_detect: bool = False,
                 skip_tools: bool = False):
        self.category = category
        self.skip_metacog = skip_metacog
        self.skip_lessons = skip_lessons
        self.skip_learn_detect = skip_learn_detect
        self.skip_tools = skip_tools

    def __repr__(self):
        skips = []
        if self.skip_metacog: skips.append("metacog")
        if self.skip_lessons: skips.append("lessons")
        if self.skip_learn_detect: skips.append("learn")
        if self.skip_tools: skips.append("tools")
        return f"FastPath({self.category}, skip=[{','.join(skips)}])"


def classify(user_input: str, history_len: int = 0) -> FastPathResult:
    """对用户输入进行快速路径分类（<1ms，纯规则，无 LLM 调用）。

    Returns:
        FastPathResult with category and skip flags.

    Categories:
        - greeting:  简单问候 → 跳过一切
        - trivial:   简短确认/感谢 → 跳过一切
        - correction: 纠正/教学 → 跳过元认知+经验，保留学习检测
        - knowledge: 知识问答 → 跳过元认知，保留经验检索
        - tool_use:  需要工具 → 完整链路
        - complex:   复杂任务 → 完整链路
    """
    stripped = user_input.strip()
    lowered = stripped.lower()

    # 0. 空输入
    if not stripped:
        return FastPathResult("trivial", skip_metacog=True, skip_lessons=True, skip_learn_detect=True, skip_tools=True)

    # 1. 工具触发 — 最高优先级（即使短输入也优先识别工具意图）
    if any(kw in lowered for kw in _TOOL_TRIGGER_KEYWORDS):
        return FastPathResult("tool_use", skip_metacog=False, skip_lessons=False, skip_learn_detect=False)

    # 2. 极短输入 — 问候或确认
    if len(stripped) <= 15:
        # 纯表情/标点
        if re.match(r'^[\s\W]+$', stripped):
            return FastPathResult("trivial", skip_metacog=True, skip_lessons=True, skip_learn_detect=True, skip_tools=True)
        if lowered in _GREETING_PATTERNS or any(lowered.startswith(g) for g in _GREETING_PATTERNS if len(g) >= 2):
            return FastPathResult("greeting", skip_metacog=True, skip_lessons=True, skip_learn_detect=True, skip_tools=True)
        if lowered in _TRIVIAL_PATTERNS:
            return FastPathResult("trivial", skip_metacog=True, skip_lessons=True, skip_learn_detect=True, skip_tools=True)

    # 3. 纠正/教学 — 需要学习检测，但不需要元认知和经验
    if any(kw in lowered for kw in _CORRECTION_KEYWORDS):
        return FastPathResult("correction", skip_metacog=True, skip_lessons=True, skip_learn_detect=False)

    # 4. 复杂任务 — 完整链路
    if len(stripped) > 200 or any(kw in lowered for kw in COMPLEX_KEYWORDS):
        return FastPathResult("complex", skip_metacog=False, skip_lessons=False, skip_learn_detect=False)

    # 5. 中等长度无工具关键词 — 知识问答型，跳过元认知
    if len(stripped) <= 80:
        return FastPathResult("knowledge", skip_metacog=True, skip_lessons=False, skip_learn_detect=True)

    # 6. 默认 — 较长的知识/创作类，跳过元认知
    return FastPathResult("knowledge", skip_metacog=True, skip_lessons=False, skip_learn_detect=False)
