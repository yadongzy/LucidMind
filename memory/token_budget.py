"""Token Budget — 记忆注入的 token 预算控制。

每轮对话注入 prompt 的记忆内容有严格 token 上限，防止:
1. Token 膨胀导致速度下降
2. 成本不可控
3. 无关记忆挤占有效上下文

架构:
- TOTAL_BUDGET: 每轮记忆总预算 (≤2000 token)
- WORKING_BUDGET: 工作记忆（会话摘要）预算
- CORE_BUDGET: 核心记忆（Letta Blocks）预算
- ARCHIVAL_BUDGET: 归档检索预算
"""

from __future__ import annotations

from logs import get_logger

logger = get_logger("memory.token_budget")

# ── Token 预算常量 ───────────────────────────────────────────
TOTAL_BUDGET = 2000          # 每轮记忆注入总预算
WORKING_BUDGET = 800         # Level 0: 工作记忆（会话摘要）
CORE_BUDGET = 600            # Level 1: 核心记忆（Letta Blocks）
ARCHIVAL_BUDGET = 600        # Level 2: 归档检索

# 单条记忆最大 token
MAX_SINGLE_MEMORY_TOKENS = 200

# 检索结果最大条数（硬上限）
MAX_RETRIEVAL_COUNT = 4


def estimate_tokens(text: str) -> int:
    """快速估算文本 token 数。

    规则:
    - CJK 字符: 每字 ≈ 1.5 token
    - ASCII 字符: 每 4 字符 ≈ 1 token
    - 保守估计（宁可多算不少算）
    """
    if not text:
        return 0
    cjk_count = 0
    ascii_count = 0
    for ch in text:
        if '\u4e00' <= ch <= '\u9fff' or '\u3400' <= ch <= '\u4dbf' or '\u3000' <= ch <= '\u303f':
            cjk_count += 1
        else:
            ascii_count += 1
    return int(cjk_count * 1.5 + ascii_count / 3.5)


def trim_to_budget(items: list[dict], budget: int = ARCHIVAL_BUDGET,
                   content_key: str = "value") -> list[dict]:
    """截断检索结果使其不超过 token 预算。

    Args:
        items: 检索到的记忆列表，每项包含 content_key 字段
        budget: token 预算上限
        content_key: 内容字段名（"value" 或 "content"）

    Returns:
        截断后的记忆列表（保持原始顺序，只保留预算内的）
    """
    if not items:
        return []

    result = []
    used = 0

    for item in items:
        content = item.get(content_key, "") or ""
        tokens = estimate_tokens(content)

        # 单条超限: 截断内容
        if tokens > MAX_SINGLE_MEMORY_TOKENS:
            # 按比例截断
            ratio = MAX_SINGLE_MEMORY_TOKENS / tokens
            max_chars = int(len(content) * ratio * 0.9)  # 留 10% 余量
            content = content[:max_chars] + "..."
            tokens = MAX_SINGLE_MEMORY_TOKENS
            item = {**item, content_key: content}

        if used + tokens > budget:
            # 超预算: 如果至少已有 1 条结果则停止
            if result:
                break
            # 第一条就超预算: 强制截断保留
            max_chars = int(len(content) * (budget / tokens) * 0.9)
            item = {**item, content_key: content[:max_chars] + "..."}
            result.append(item)
            break

        result.append(item)
        used += tokens

    if len(result) < len(items):
        logger.debug(
            f"Token budget: {len(items)} → {len(result)} items "
            f"(budget={budget}, used={used})"
        )

    return result


def trim_memories_to_budget(memories: list[dict], budget: int = ARCHIVAL_BUDGET) -> list[dict]:
    """专门处理 recall() 返回的记忆列表。

    记忆格式: {"key": str, "value": str, "category": str, ...}
    """
    return trim_to_budget(memories, budget=budget, content_key="value")


def trim_blocks_to_budget(blocks_text: str, budget: int = CORE_BUDGET) -> str:
    """截断 Letta Blocks 注入文本使其不超预算。"""
    tokens = estimate_tokens(blocks_text)
    if tokens <= budget:
        return blocks_text

    # 按比例截断
    ratio = budget / tokens
    max_chars = int(len(blocks_text) * ratio * 0.9)
    trimmed = blocks_text[:max_chars] + "\n[...核心记忆已截断以控制 token 预算]"
    logger.info(f"Blocks trimmed: {tokens} → ~{budget} tokens")
    return trimmed


def get_budget_report(working_tokens: int = 0, core_tokens: int = 0,
                      archival_tokens: int = 0) -> dict:
    """生成当前 token 使用报告。"""
    total = working_tokens + core_tokens + archival_tokens
    return {
        "total_used": total,
        "total_budget": TOTAL_BUDGET,
        "utilization": round(total / TOTAL_BUDGET, 2) if TOTAL_BUDGET > 0 else 0,
        "working": {"used": working_tokens, "budget": WORKING_BUDGET},
        "core": {"used": core_tokens, "budget": CORE_BUDGET},
        "archival": {"used": archival_tokens, "budget": ARCHIVAL_BUDGET},
        "over_budget": total > TOTAL_BUDGET,
    }
