"""Memory Compressor — 对话语义压缩（无需 LLM 调用）。

将 N 条对话消息压缩为 1 条精炼记忆，实现 10:1 压缩比。

压缩策略:
1. 提取用户意图（第一条 user 消息）
2. 提取解决方案（最后一条 assistant 消息的关键动作）
3. 提取结果（成功/失败标记）
4. 生成压缩模板: "{日期}: {主题} — {方案}。{结果}。"

目标: ≤150 字符/条，同时保留核心语义。
"""

from __future__ import annotations

import re
import time
from datetime import datetime, timezone
from typing import Any

from logs import get_logger

logger = get_logger("memory.compressor")

# 最大压缩结果长度
MAX_COMPRESSED_LENGTH = 200

# 成功/失败标记关键词
_SUCCESS_MARKERS = [
    "成功", "完成", "通过", "已修复", "已实现", "OK", "done", "pass",
    "✅", "✓", "解决了", "搞定", "没问题",
]
_FAILURE_MARKERS = [
    "失败", "错误", "不行", "报错", "超时", "还是", "仍然",
    "❌", "✗", "无法", "不能", "没有成功",
]


def compress_conversation(messages: list[dict[str, Any]],
                          session_id: str = "",
                          timestamp: float | None = None) -> dict[str, Any] | None:
    """将一组对话消息压缩为一条精炼记忆。

    Args:
        messages: 对话消息列表 [{"role": str, "content": str}, ...]
        session_id: 会话 ID（可选，用于来源追踪）
        timestamp: 时间戳（可选，默认当前时间）

    Returns:
        压缩后的记忆条目 dict，或 None（如果消息太少/无意义）
    """
    if not messages or len(messages) < 2:
        return None

    # 提取用户消息和助手消息
    user_msgs = [m for m in messages if m.get("role") == "user"]
    assistant_msgs = [m for m in messages if m.get("role") == "assistant"]

    if not user_msgs:
        return None

    # 1. 提取主题（第一条用户消息）
    topic = _extract_topic(user_msgs[0].get("content", ""))
    if not topic:
        return None

    # 2. 提取方案（最后一条助手消息的核心动作）
    solution = ""
    if assistant_msgs:
        solution = _extract_solution(assistant_msgs[-1].get("content", ""))

    # 3. 判断结果
    outcome = _detect_outcome(messages)

    # 4. 生成压缩记忆
    ts = timestamp or time.time()
    date_str = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")

    parts = [f"{date_str}: {topic}"]
    if solution:
        parts.append(f"方案: {solution}")
    if outcome:
        parts.append(outcome)

    compressed_content = " — ".join(parts)

    # 截断到最大长度
    if len(compressed_content) > MAX_COMPRESSED_LENGTH:
        compressed_content = compressed_content[:MAX_COMPRESSED_LENGTH - 3] + "..."

    result = {
        "key": topic,
        "value": compressed_content,
        "category": "compressed_session",
        "metadata": {
            "source_session": session_id,
            "message_count": len(messages),
            "compression_ratio": round(len(messages) / 1, 1),
            "outcome": outcome,
            "compressed_at": time.time(),
        },
    }

    logger.info(
        f"压缩: {len(messages)} 条消息 → 1 条记忆 "
        f"({len(compressed_content)} 字符): {compressed_content[:60]}..."
    )
    return result


def compress_batch(messages: list[dict[str, Any]],
                   chunk_size: int = 10,
                   session_id: str = "") -> list[dict[str, Any]]:
    """批量压缩: 将长对话按 chunk_size 分段压缩。

    Args:
        messages: 完整对话消息列表
        chunk_size: 每段消息数
        session_id: 会话 ID

    Returns:
        压缩后的记忆列表
    """
    if len(messages) < chunk_size:
        result = compress_conversation(messages, session_id)
        return [result] if result else []

    compressed = []
    for i in range(0, len(messages), chunk_size):
        chunk = messages[i:i + chunk_size]
        result = compress_conversation(
            chunk, session_id,
            timestamp=time.time() - (len(messages) - i)  # 按时间排序
        )
        if result:
            compressed.append(result)

    logger.info(f"批量压缩: {len(messages)} 条 → {len(compressed)} 条记忆")
    return compressed


def _extract_topic(text: str) -> str:
    """从用户消息中提取主题（≤30字符）。"""
    if not text:
        return ""
    # 去除多余空白
    text = text.strip()
    # 取第一句话
    for sep in ["。", "？", "！", "\n", ". ", "? ", "! "]:
        if sep in text:
            text = text[:text.index(sep)]
            break
    # 截断
    if len(text) > 30:
        text = text[:30]
    # 去除开头的序号/编号
    text = re.sub(r'^[\d]+[.、,，)\]】]\s*', '', text)
    return text.strip()


def _extract_solution(text: str) -> str:
    """从助手回复中提取核心方案（≤50字符）。"""
    if not text:
        return ""
    text = text.strip()

    # 尝试找到关键动作词
    action_patterns = [
        r'(?:已|我)(创建|修改|添加|删除|修复|优化|实现|配置|升级|重构)了?\s*(.{5,40})',
        r'(使用|采用|通过)\s*(.{5,40}?)(?:来|进行|实现)',
        r'(?:方案|解决|做法)[：:]\s*(.{5,50})',
    ]
    for pat in action_patterns:
        m = re.search(pat, text)
        if m:
            groups = m.groups()
            result = "".join(g for g in groups if g)
            return result[:50] if len(result) > 50 else result

    # 回退: 取第一句非空行的前50字符
    for line in text.split("\n"):
        line = line.strip()
        if line and len(line) > 5 and not line.startswith("#"):
            return line[:50]

    return text[:50]


def _detect_outcome(messages: list[dict[str, Any]]) -> str:
    """检测对话结果（成功/失败/进行中）。"""
    # 检查最后几条消息
    last_texts = " ".join(
        m.get("content", "") for m in messages[-3:]
    ).lower()

    for marker in _SUCCESS_MARKERS:
        if marker.lower() in last_texts:
            return "结果: 成功"

    for marker in _FAILURE_MARKERS:
        if marker.lower() in last_texts:
            return "结果: 失败"

    return ""
