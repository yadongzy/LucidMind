"""Memory Chunking — 文本分块（对标 OpenClaw compaction.ts chunking）。

将长文本切成重叠块，用于 embedding 存储。
默认: 400 tokens/chunk, 80 tokens overlap。
"""

from logs import get_logger

logger = get_logger("memory.chunking")

# 粗略估算: 1 token ≈ 1.5 中文字符 ≈ 4 英文字符
_CHARS_PER_TOKEN_CN = 1.5
_CHARS_PER_TOKEN_EN = 4.0


def _estimate_tokens(text: str) -> int:
    """粗略估算 token 数。"""
    cn_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
    en_chars = len(text) - cn_chars
    return int(cn_chars / _CHARS_PER_TOKEN_CN + en_chars / _CHARS_PER_TOKEN_EN)


def _tokens_to_chars(tokens: int, text: str) -> int:
    """根据文本语言比例，估算 token 对应的字符数。"""
    if not text:
        return 0
    cn_ratio = sum(1 for c in text if '\u4e00' <= c <= '\u9fff') / max(len(text), 1)
    avg_chars = cn_ratio * _CHARS_PER_TOKEN_CN + (1 - cn_ratio) * _CHARS_PER_TOKEN_EN
    return int(tokens * avg_chars)


def chunk_text(text: str, max_tokens: int = 400, overlap: int = 80) -> list[str]:
    """将长文本切成重叠块。

    Args:
        text: 原始文本
        max_tokens: 每块最大 token 数
        overlap: 块间重叠 token 数

    Returns:
        文本块列表（每块 ≤ max_tokens）
    """
    if not text or not text.strip():
        return []

    total_tokens = _estimate_tokens(text)
    if total_tokens <= max_tokens:
        return [text.strip()]

    max_chars = _tokens_to_chars(max_tokens, text)
    overlap_chars = _tokens_to_chars(overlap, text)
    step = max(1, max_chars - overlap_chars)

    chunks = []
    start = 0
    while start < len(text):
        end = min(start + max_chars, len(text))
        # 尝试在句子/段落边界切分
        chunk = text[start:end]
        if end < len(text):
            # 向前找最近的句子结束符
            for sep in ['\n\n', '\n', '。', '！', '？', '. ', '! ', '? ', '; ', '；']:
                last_sep = chunk.rfind(sep)
                if last_sep > len(chunk) // 2:  # 至少保留一半
                    chunk = chunk[:last_sep + len(sep)]
                    end = start + len(chunk)
                    break

        stripped = chunk.strip()
        if stripped:
            chunks.append(stripped)

        if end >= len(text):
            break
        start = end - overlap_chars
        if start <= 0 and end > 0:
            start = step  # 防止死循环

    return chunks


def chunk_messages(messages: list[dict], max_tokens: int = 400,
                   overlap: int = 80) -> list[str]:
    """将对话消息列表转换为文本块。

    先将消息合并为文本，再按 chunk_text 切分。
    """
    parts = []
    for msg in messages:
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        if content:
            parts.append(f"[{role}]: {content}")
    text = "\n".join(parts)
    return chunk_text(text, max_tokens, overlap)
