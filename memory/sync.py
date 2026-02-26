"""Memory Sync Manager — 会话→记忆自动同步（对标 OpenClaw sync-session-files.ts）。

管理会话结束时自动提取关键信息存入记忆，以及增量同步阈值检查。
"""

import time
from typing import Any

from memory.types import MemoryConfig
from logs import get_logger

logger = get_logger("memory.sync")


class MemorySyncManager:
    """管理会话 → 记忆的自动同步。"""

    def __init__(self, store: Any, config: MemoryConfig,
                 embed_fn: Any = None):
        """
        Args:
            store: MemoryStore 实例
            config: MemoryConfig 配置
            embed_fn: 可选的 embedding 函数 (text) -> list[float]
        """
        self.store = store
        self.config = config
        self.embed_fn = embed_fn
        self._session_msg_counts: dict[str, int] = {}
        self._session_byte_counts: dict[str, int] = {}
        self._last_sync: dict[str, float] = {}

    def on_session_start(self, session_id: str) -> None:
        """会话开始时初始化计数器。"""
        self._session_msg_counts[session_id] = 0
        self._session_byte_counts[session_id] = 0
        self._last_sync[session_id] = time.time()
        logger.debug(f"会话开始: {session_id}")

    def track_message(self, session_id: str, message: dict) -> None:
        """追踪单条消息，更新增量计数。"""
        content = message.get("content", "")
        self._session_msg_counts[session_id] = self._session_msg_counts.get(session_id, 0) + 1
        self._session_byte_counts[session_id] = self._session_byte_counts.get(session_id, 0) + len(content.encode("utf-8"))

    def should_sync(self, session_id: str) -> bool:
        """检查会话变化是否达到同步阈值。"""
        msgs = self._session_msg_counts.get(session_id, 0)
        return msgs >= self.config.sync_delta_messages

    async def on_session_end(self, session_id: str, messages: list[dict],
                             llm: Any = None) -> int:
        """会话结束时，提取关键信息存入记忆。

        Returns:
            存入的记忆条数
        """
        if not messages:
            self._cleanup(session_id)
            return 0

        # 提取用户消息和助手回复
        user_msgs = [m["content"] for m in messages if m.get("role") == "user" and m.get("content")]
        asst_msgs = [m["content"] for m in messages if m.get("role") == "assistant" and m.get("content")]

        if not user_msgs:
            self._cleanup(session_id)
            return 0

        count = 0

        # 1. 存储会话摘要
        summary = await self._summarize_session(messages, llm)
        if summary:
            embedding = None
            if self.embed_fn:
                try:
                    embedding = await self.embed_fn(summary) if _is_coroutine(self.embed_fn) else self.embed_fn(summary)
                except Exception as e:
                    logger.warning(f"embedding 失败: {e}")
            self.store.add(
                collection="sessions",
                content=summary,
                embedding=embedding,
                metadata={"session_id": session_id, "msg_count": len(messages)},
            )
            count += 1
            logger.info(f"会话摘要已存储: {session_id} ({len(summary)} chars)")

        self._cleanup(session_id)
        return count

    async def _summarize_session(self, messages: list[dict], llm: Any = None) -> str:
        """使用 LLM 总结会话，无 LLM 时回退到截取。"""
        # 构建对话文本
        parts = []
        for msg in messages[-20:]:  # 最多取最近 20 条
            role = msg.get("role", "")
            content = msg.get("content", "")
            if content and role in ("user", "assistant"):
                parts.append(f"{role}: {content[:200]}")
        dialogue = "\n".join(parts)

        if llm and len(dialogue) > 50:
            try:
                resp = await llm.chat([
                    {"role": "system", "content": "用一段话（50-150字）总结这段对话的关键信息，包括用户意图、完成的操作、重要结论。只输出总结，不要前缀。"},
                    {"role": "user", "content": dialogue[:3000]},
                ])
                summary = resp.get("content", "").strip()
                if summary and len(summary) > 20:
                    return summary
            except Exception as e:
                logger.warning(f"LLM 摘要失败: {e}")

        # 回退: 截取用户消息
        user_parts = [m["content"][:100] for m in messages if m.get("role") == "user" and m.get("content")][-3:]
        return f"会话要点: {'; '.join(user_parts)}" if user_parts else ""

    def _cleanup(self, session_id: str) -> None:
        """清理会话追踪数据。"""
        self._session_msg_counts.pop(session_id, None)
        self._session_byte_counts.pop(session_id, None)
        self._last_sync.pop(session_id, None)


def _is_coroutine(fn) -> bool:
    """检查函数是否为协程。"""
    import asyncio
    return asyncio.iscoroutinefunction(fn)


# ── ACE Reflector (Phase 8.3) ──────────────────────────────────

_REFLECTOR_SYSTEM = (
    "你是一个经验提炼专家。你的任务是从对话和工具执行轨迹中提取可复用的策略和教训。\n"
    "每条策略必须是具体的、可操作的，而非泛泛的建议。\n"
    "输出格式: 每行一条策略，用 `- ` 开头。不要输出编号或其他格式。\n"
    "只输出策略列表，不要输出前言、总结或解释。"
)

_REFINE_SYSTEM = (
    "你是一个策略优化专家。审查以下策略列表，执行以下操作:\n"
    "1. 删除重复或过于笼统的策略\n"
    "2. 让每条策略更具体、更可操作\n"
    "3. 合并相似策略\n"
    "输出格式: 每行一条策略，用 `- ` 开头。只输出优化后的列表。"
)


async def reflect_on_session(messages: list[dict], tool_results: list[dict] | None = None,
                              llm: Any = None, max_refine_rounds: int = 3) -> list[dict]:
    """ACE Reflector: 从执行轨迹中提炼结构化 delta bullets。

    三步流程:
    1. 从对话+工具结果中提取初始策略
    2. 多轮 refinement 精炼
    3. 输出结构化 delta bullets

    Args:
        messages: 对话消息列表
        tool_results: 工具执行结果列表 [{"tool": str, "success": bool, "result": str, "error": str}]
        llm: LLM 实例（可选，无则回退规则提取）
        max_refine_rounds: 最大精炼轮数

    Returns:
        list of delta bullets: [{"content": str, "collection": str, "metadata": dict}]
    """
    if not messages:
        return []

    # Step 1: 提取初始策略
    raw_lessons = []
    if llm:
        raw_lessons = await _llm_extract(messages, tool_results, llm)
    if not raw_lessons:
        raw_lessons = _rule_based_extract(messages, tool_results)
    if not raw_lessons:
        return []

    # Step 2: 多轮 refinement
    if llm and len(raw_lessons) >= 3:
        raw_lessons = await _multi_round_refine(raw_lessons, llm, max_refine_rounds)

    # Step 3: 构建结构化 delta bullets
    deltas = []
    for lesson in raw_lessons:
        lesson = lesson.strip()
        if len(lesson) < 5:
            continue
        collection = _classify_collection(lesson, tool_results)
        deltas.append({
            "content": lesson,
            "collection": collection,
            "metadata": {
                "source": "reflector",
                "helpful_count": 1,
                "harmful_count": 0,
            },
        })

    logger.info(f"ACE Reflector: 从 {len(messages)} 条消息中提取 {len(deltas)} 条策略")
    return deltas


async def _llm_extract(messages: list[dict], tool_results: list[dict] | None,
                        llm: Any) -> list[str]:
    """用 LLM 从对话轨迹中提取策略。"""
    # 构建对话摘要
    parts = []
    for msg in messages[-30:]:
        role = msg.get("role", "")
        content = msg.get("content", "")
        if content and role in ("user", "assistant"):
            parts.append(f"[{role}] {content[:300]}")

    # 构建工具执行摘要
    tool_summary = ""
    if tool_results:
        tool_parts = []
        for tr in tool_results[-10:]:
            status = "✅" if tr.get("success") else "❌"
            tool_parts.append(f"{status} {tr.get('tool', '?')}: {tr.get('result', tr.get('error', ''))[:100]}")
        tool_summary = "\n工具执行记录:\n" + "\n".join(tool_parts)

    dialogue = "\n".join(parts[-20:])
    prompt = f"对话轨迹:\n{dialogue[:4000]}\n{tool_summary}\n\n请提取可复用的具体策略和教训:"

    try:
        resp = await llm.chat([
            {"role": "system", "content": _REFLECTOR_SYSTEM},
            {"role": "user", "content": prompt},
        ])
        text = resp.get("content", "")
        return _parse_bullet_list(text)
    except Exception as e:
        logger.warning(f"ACE Reflector LLM 提取失败: {e}")
        return []


async def _multi_round_refine(lessons: list[str], llm: Any, max_rounds: int) -> list[str]:
    """多轮 refinement 精炼策略列表。"""
    current = lessons
    for round_idx in range(max_rounds):
        if len(current) < 2:
            break
        bullet_text = "\n".join(f"- {l}" for l in current)
        try:
            resp = await llm.chat([
                {"role": "system", "content": _REFINE_SYSTEM},
                {"role": "user", "content": f"当前策略列表:\n{bullet_text}"},
            ])
            refined = _parse_bullet_list(resp.get("content", ""))
            if not refined or len(refined) < 1:
                break
            # 如果没有变化则停止
            if set(refined) == set(current):
                break
            current = refined
            logger.debug(f"ACE Reflector refine round {round_idx+1}: {len(current)} 条策略")
        except Exception as e:
            logger.warning(f"ACE Reflector refine round {round_idx+1} 失败: {e}")
            break
    return current


def _rule_based_extract(messages: list[dict], tool_results: list[dict] | None) -> list[str]:
    """无 LLM 时的规则提取: 从工具失败和用户纠正中提取教训。"""
    lessons = []

    # 从工具失败中提取
    if tool_results:
        for tr in tool_results:
            if not tr.get("success") and tr.get("error"):
                tool = tr.get("tool", "unknown")
                error = tr.get("error", "")[:100]
                lessons.append(f"工具 {tool} 执行失败: {error}。下次使用前应检查参数。")

    # 从用户纠正中提取
    correction_kw = ["不对", "错了", "应该是", "不是这样", "wrong", "incorrect", "actually"]
    for i, msg in enumerate(messages):
        if msg.get("role") != "user":
            continue
        content = msg.get("content", "")
        if any(kw in content.lower() for kw in correction_kw):
            # 找到前一条助手回复
            prev_asst = ""
            for j in range(i-1, -1, -1):
                if messages[j].get("role") == "assistant":
                    prev_asst = messages[j].get("content", "")[:100]
                    break
            if prev_asst:
                lessons.append(f"用户纠正: 之前回答「{prev_asst[:60]}」有误，正确做法: {content[:120]}")

    return lessons


def _classify_collection(lesson: str, tool_results: list[dict] | None) -> str:
    """根据内容分类到对应的 collection。"""
    lesson_lower = lesson.lower()
    # 工具相关 → skills
    tool_kw = ["工具", "tool", "执行", "调用", "参数", "命令"]
    if any(kw in lesson_lower for kw in tool_kw):
        return "skills"
    # 用户偏好 → facts
    pref_kw = ["用户喜欢", "用户偏好", "用户习惯", "总是", "从不", "prefer"]
    if any(kw in lesson_lower for kw in pref_kw):
        return "facts"
    # 默认 → lessons
    return "lessons"


def _parse_bullet_list(text: str) -> list[str]:
    """从 LLM 输出中解析 bullet 列表。"""
    lines = text.strip().split("\n")
    result = []
    for line in lines:
        line = line.strip()
        if line.startswith("- "):
            line = line[2:].strip()
        elif line.startswith("* "):
            line = line[2:].strip()
        elif line and line[0].isdigit() and ". " in line[:5]:
            line = line.split(". ", 1)[1].strip()
        else:
            continue
        if len(line) >= 5:
            result.append(line)
    return result
