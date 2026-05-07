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

# ── 5. 意图感知检索配置 ──────────────────────────────────────────

_INTENT_PATTERNS = {
    "recall_explicit": [
        re.compile(r"(?:记得|之前|上次|以前|曾经|回忆|你说过|我们讨论过)"),
        re.compile(r"(?i)(?:remember|recall|last time|before|earlier|you said)"),
    ],
    "coding_task": [
        re.compile(r"(?:写代码|修改|重构|bug|修复|实现|添加功能|代码)"),
        re.compile(r"(?i)(?:code|implement|refactor|fix|debug|function|class|module)"),
        re.compile(r"(?:文件|目录|路径|导入|import|配置)"),
    ],
    "preference": [
        re.compile(r"(?:偏好|喜欢|不喜欢|习惯|风格|设置)"),
        re.compile(r"(?i)(?:prefer|like|dislike|style|setting|config)"),
    ],
    "project_query": [
        re.compile(r"(?:项目|架构|依赖|模块|组件|结构)"),
        re.compile(r"(?i)(?:project|architecture|dependency|module|component)"),
    ],
}


def classify_retrieval_intent(query: str) -> dict:
    """多级意图分类，返回检索策略。

    Returns:
        {
            "intent": str,           # 意图类型
            "should_retrieve": bool, # 是否需要检索
            "limit": int,            # 检索条数上限
            "collections": list,     # 限定的集合列表 (空=全部)
            "boost_exact": bool,     # 是否加权精确匹配
        }
    """
    if not query or len(query.strip()) < 2:
        return {"intent": "empty", "should_retrieve": False,
                "limit": 0, "collections": [], "boost_exact": False}

    text = query.strip()

    # 1. 跳过检索的情况
    if should_skip_retrieval(text):
        return {"intent": "greeting", "should_retrieve": False,
                "limit": 0, "collections": [], "boost_exact": False}

    # 2. 强制检索的情况
    for pat in _FORCE_RETRIEVAL_PATTERNS:
        if pat.search(text):
            return {"intent": "recall_explicit", "should_retrieve": True,
                    "limit": 6, "collections": [], "boost_exact": True}

    # 3. 意图分类
    for intent_name, patterns in _INTENT_PATTERNS.items():
        for pat in patterns:
            if pat.search(text):
                if intent_name == "recall_explicit":
                    return {"intent": intent_name, "should_retrieve": True,
                            "limit": 6, "collections": [], "boost_exact": True}
                elif intent_name == "coding_task":
                    return {"intent": intent_name, "should_retrieve": True,
                            "limit": 3, "collections": ["facts", "lessons"],
                            "boost_exact": False}
                elif intent_name == "preference":
                    return {"intent": intent_name, "should_retrieve": True,
                            "limit": 2, "collections": ["preference", "facts"],
                            "boost_exact": False}
                elif intent_name == "project_query":
                    return {"intent": intent_name, "should_retrieve": True,
                            "limit": 4, "collections": ["facts", "skills"],
                            "boost_exact": False}

    # 4. 默认: 轻量检索
    return {"intent": "general", "should_retrieve": True,
            "limit": 3, "collections": [], "boost_exact": False}


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
