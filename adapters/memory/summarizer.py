"""S43: 长期记忆摘要 — 旧对话自动压缩为知识条目。

当会话消息超过阈值时，用 LLM 将旧消息压缩为摘要，
保留关键知识点，释放上下文窗口空间。

不修改 brain.py（规则 06），由 BrainDaemon 定期调用。
"""
import json
import time
from pathlib import Path
from typing import Any

from logs import get_logger

logger = get_logger("summarizer")

_SUMMARY_DIR = Path(__file__).parent.parent.parent / "data" / "summaries"
_SUMMARY_DIR.mkdir(parents=True, exist_ok=True)

_COMPRESS_THRESHOLD = 40  # 超过此条数触发压缩
_KEEP_RECENT = 15         # 保留最近N条不压缩


async def summarize_messages(messages: list[dict], llm) -> str | None:
    """用 LLM 将一组消息压缩为摘要。"""
    if not messages or not llm:
        return None
    text_parts = []
    for m in messages[:30]:
        role = m.get("role", "?")
        content = (m.get("content") or "")[:200]
        if content:
            text_parts.append(f"{role}: {content}")
    if not text_parts:
        return None

    prompt = f"""将以下对话压缩为简洁的知识摘要。
保留：用户偏好、关键决策、重要事实、学到的经验。
丢弃：寒暄、重复内容、过程性细节。
输出纯文本摘要，不超过200字。

对话内容:
{chr(10).join(text_parts)}"""

    try:
        import asyncio
        resp = await asyncio.wait_for(
            llm.chat([{"role": "user", "content": prompt}], tools=None),
            timeout=10.0
        )
        content = resp.get("content", "").strip()
        import re
        content = re.sub(r"<think>.*?</think>\s*", "", content, flags=re.DOTALL).strip()
        if content and len(content) > 20:
            logger.info(f"摘要生成: {len(messages)}条→{len(content)}字")
            return content[:500]
    except Exception as e:
        logger.warning(f"摘要生成失败: {e}")
    return None


async def compress_session(session_id: str, messages: list[dict],
                           llm, memory_adapter=None) -> dict:
    """压缩一个会话的旧消息。

    Returns: {"compressed": int, "summary": str, "remaining": int}
    """
    if len(messages) < _COMPRESS_THRESHOLD:
        return {"compressed": 0, "summary": "", "remaining": len(messages)}

    old_msgs = messages[:-_KEEP_RECENT]
    recent_msgs = messages[-_KEEP_RECENT:]

    summary = await summarize_messages(old_msgs, llm)
    if not summary:
        return {"compressed": 0, "summary": "", "remaining": len(messages)}

    # 保存摘要到文件
    summary_entry = {
        "session_id": session_id,
        "timestamp": time.time(),
        "compressed_count": len(old_msgs),
        "summary": summary,
    }
    summary_file = _SUMMARY_DIR / f"{session_id}_summaries.json"
    existing = []
    if summary_file.exists():
        try:
            existing = json.loads(summary_file.read_text(encoding="utf-8"))
        except Exception:
            existing = []
    existing.append(summary_entry)
    if len(existing) > 50:
        existing = existing[-50:]
    summary_file.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")

    # 将摘要注入为系统消息 + 保留最近消息
    compressed = [{"role": "system", "content": f"[历史摘要] {summary}"}] + recent_msgs

    # 更新会话文件
    if memory_adapter and hasattr(memory_adapter, 'sessions_dir'):
        sess_file = memory_adapter.sessions_dir / f"{session_id}.json"
        try:
            sess_file.write_text(json.dumps(compressed, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            logger.warning(f"会话文件更新失败: {e}")

    logger.info(f"会话压缩: {session_id} {len(old_msgs)}条→摘要 (保留{len(recent_msgs)}条)")
    return {"compressed": len(old_msgs), "summary": summary, "remaining": len(compressed)}


def get_summaries(session_id: str) -> list[dict]:
    """获取会话的历史摘要。"""
    summary_file = _SUMMARY_DIR / f"{session_id}_summaries.json"
    if not summary_file.exists():
        return []
    try:
        return json.loads(summary_file.read_text(encoding="utf-8"))
    except Exception:
        return []
