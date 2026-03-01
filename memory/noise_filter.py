"""Noise Filter — 记忆存储前的噪声过滤（对标 memory-lancedb-pro noise-filter.ts）。

三类过滤:
1. Agent 拒绝/免责 — "I cannot", "I don't have access" 等无实质内容
2. 元问题/寒暄 — "你好", "谢谢", "how are you" 等无需记忆
3. 错误日志噪声 — "Ralph 循环", "尝试了 N 次均失败" 等原始错误堆栈

同时提供自适应检索跳过: 判断查询是否无需检索记忆。
"""

import re
from logs import get_logger

logger = get_logger("memory.noise_filter")

# ── 1. Agent 拒绝/免责 (不应存为记忆) ──────────────────────────

_DENIAL_PATTERNS = [
    re.compile(r"(?i)I (?:cannot|can't|don't|do not) (?:access|help|provide|do that)"),
    re.compile(r"(?i)I'm (?:sorry|unable|not able)"),
    re.compile(r"(?i)(?:as an? )?AI (?:assistant|language model)"),
    re.compile(r"(?i)I don't have (?:access|the ability|permission)"),
    re.compile(r"(?i)beyond (?:my|the) (?:scope|capabilities)"),
    re.compile(r"我(?:无法|不能|没有权限|做不到)"),
    re.compile(r"(?:作为|身为)(?:一个)?AI"),
]

# ── 2. 寒暄/元问题 (不应存为记忆) ──────────────────────────────

_BOILERPLATE_PATTERNS = [
    re.compile(r"^(?:你好|hi|hello|hey|嗨|哈喽)\s*[!！.。]?\s*$", re.IGNORECASE),
    re.compile(r"^(?:谢谢|thanks?|thank you|多谢|感谢)\s*[!！.。]?\s*$", re.IGNORECASE),
    re.compile(r"^(?:好的?|ok(?:ay)?|sure|got it|明白|了解|知道了)\s*[!！.。]?\s*$", re.IGNORECASE),
    re.compile(r"^(?:再见|bye|goodbye|拜拜)\s*[!！.。]?\s*$", re.IGNORECASE),
    re.compile(r"(?i)^how (?:are you|do you do|is it going)"),
    re.compile(r"^(?:嗯+|哦+|啊+|呃+)\s*[!！.。]?\s*$"),
]

# ── 3. 错误日志噪声 (不应存为教训) ──────────────────────────────

_ERROR_NOISE_PATTERNS = [
    re.compile(r"Ralph 循环.*尝试了 \d+ 次均失败"),
    re.compile(r"(?i)client error .* for url .*"),
    re.compile(r"(?i)timeout \d+ms exceeded"),
    re.compile(r"(?i)(?:connection|ssl|http) (?:error|refused|timeout|reset)"),
    re.compile(r"(?i)traceback \(most recent call last\)"),
    re.compile(r"(?i)^error:?\s+"),
    re.compile(r"执行超时[。.]?\s*$"),
    re.compile(r"got an unexpected keyword argument"),
    re.compile(r"'(?:str|int|NoneType)' object (?:has no attribute|is not)"),
]

# ── 4. 自适应跳过模式 (查询无需检索记忆) ────────────────────────

_SKIP_RETRIEVAL_PATTERNS = [
    # 问候
    re.compile(r"^(?:你好|hi|hello|hey|嗨|哈喽)[!！.。]?\s*$", re.IGNORECASE),
    # 简单肯定/否定
    re.compile(r"^(?:好的?|ok|yes|no|是|不|对|嗯|行)\s*[!！.。]?\s*$", re.IGNORECASE),
    # 感谢/告别
    re.compile(r"^(?:谢谢|thanks?|bye|再见|拜拜)\s*[!！.。]?\s*$", re.IGNORECASE),
    # 纯命令 (无语义内容)
    re.compile(r"^(?:继续|continue|go|开始|start|停|stop|取消|cancel)\s*[!！.。]?\s*$", re.IGNORECASE),
]

_FORCE_RETRIEVAL_PATTERNS = [
    re.compile(r"(?i)(?:remember|recall|记得|之前|上次|以前|曾经)"),
    re.compile(r"(?i)(?:你知道|do you know|have you learned)"),
    re.compile(r"(?i)(?:偏好|preference|习惯|喜欢|不喜欢)"),
]


def _effective_length(text: str) -> int:
    """计算有效长度: CJK 字符每个算 2 个有效字符。"""
    count = 0
    for ch in text:
        if '\u4e00' <= ch <= '\u9fff' or '\u3400' <= ch <= '\u4dbf':
            count += 2
        else:
            count += 1
    return count


def is_noise(content: str) -> bool:
    """判断内容是否为噪声，不应存入记忆。

    Args:
        content: 待检查的记忆内容

    Returns:
        True 表示是噪声，应该过滤掉
    """
    if not content or len(content.strip()) < 2:
        return True

    text = content.strip()

    # 太短的内容没有记忆价值 (CJK 感知: 每个 CJK 字算 2)
    if _effective_length(text) < 5:
        return True

    # 检查 agent 拒绝
    for pat in _DENIAL_PATTERNS:
        if pat.search(text):
            logger.debug(f"噪声过滤 [denial]: {text[:60]}")
            return True

    # 检查寒暄
    for pat in _BOILERPLATE_PATTERNS:
        if pat.search(text):
            logger.debug(f"噪声过滤 [boilerplate]: {text[:60]}")
            return True

    # 检查错误日志噪声
    for pat in _ERROR_NOISE_PATTERNS:
        if pat.search(text):
            logger.debug(f"噪声过滤 [error_noise]: {text[:60]}")
            return True

    return False


def should_skip_retrieval(query: str) -> bool:
    """判断查询是否无需检索记忆（自适应跳过）。

    Args:
        query: 用户查询文本

    Returns:
        True 表示应跳过检索
    """
    if not query or len(query.strip()) < 2:
        return True

    text = query.strip()

    # 强制检索: 包含记忆关键词时永远检索
    for pat in _FORCE_RETRIEVAL_PATTERNS:
        if pat.search(text):
            return False

    # 跳过: 简单问候/命令
    for pat in _SKIP_RETRIEVAL_PATTERNS:
        if pat.search(text):
            logger.debug(f"跳过检索 [skip]: {text[:60]}")
            return True

    return False
