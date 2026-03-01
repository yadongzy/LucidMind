"""Two-Stage Memory Extractor — 两阶段提取+动作决策（对标 mem0 add()）。

Stage 1: 从对话中提取事实/偏好/教训（LLM 或规则回退）
Stage 2: 对每条提取结果，搜索已有记忆 → 决策 ADD / UPDATE / DELETE / SKIP

相比单阶段 Reflector:
- 去重更精准（对比已有记忆后决策，而非 bigram Jaccard）
- 支持 UPDATE（内容合并/更新，而非只 append）
- 支持 DELETE（用户明确否定已有记忆时主动清理）
"""

import json
from typing import Any

from logs import get_logger

logger = get_logger("memory.two_stage")

# ── Stage 1: 事实提取 Prompt ──────────────────────────────────

_EXTRACT_SYSTEM = (
    "你是一个信息提取专家。从对话中提取关键事实、用户偏好和教训。\n"
    "每条提取结果必须是独立的、自包含的一句话。\n"
    "分类: FACT(事实) / PREFERENCE(偏好) / LESSON(教训)\n"
    "输出 JSON 数组，每个元素: {\"type\": \"FACT|PREFERENCE|LESSON\", \"content\": \"...\"}\n"
    "只输出 JSON 数组，无前言。如果没有值得提取的内容，输出 []。"
)

# ── Stage 2: 动作决策 Prompt ──────────────────────────────────

_DECIDE_SYSTEM = (
    "你是一个记忆管理专家。对比新提取的信息和已有记忆，决定动作。\n"
    "动作类型:\n"
    "- ADD: 全新信息，不与任何已有记忆重复\n"
    "- UPDATE: 与某条已有记忆相关但有更新（返回 memory_id + 新内容）\n"
    "- DELETE: 用户明确否定了某条已有记忆（返回 memory_id）\n"
    "- SKIP: 已有记忆完全覆盖此信息，无需操作\n\n"
    "输出 JSON 数组，每个元素:\n"
    "{\"action\": \"ADD|UPDATE|DELETE|SKIP\", \"content\": \"...\", \"memory_id\": \"...或空\"}\n"
    "只输出 JSON 数组，无前言。"
)


class TwoStageExtractor:
    """两阶段记忆提取器。"""

    def __init__(self, store=None):
        self._store = store

    async def extract_and_decide(self, messages: list[dict],
                                  llm: Any = None,
                                  session_id: str = "") -> list[dict]:
        """执行完整的两阶段提取+决策流程。

        Args:
            messages: 对话消息列表
            llm: LLM 实例（可选）
            session_id: 会话 ID

        Returns:
            动作列表: [{"action": str, "content": str, "memory_id": str, "type": str}]
        """
        if not messages:
            return []

        # Stage 1: 提取
        extractions = await self._stage1_extract(messages, llm)
        if not extractions:
            return []

        logger.info(f"Stage 1 提取: {len(extractions)} 条信息")

        # Stage 2: 决策
        if llm and self._store:
            decisions = await self._stage2_decide(extractions, llm)
        else:
            # 无 LLM 时回退: 所有提取结果都 ADD
            decisions = [
                {"action": "ADD", "content": e["content"],
                 "type": e.get("type", "FACT"), "memory_id": ""}
                for e in extractions
            ]

        # 添加 session_id 到每个决策
        for d in decisions:
            d["session_id"] = session_id

        logger.info(f"Stage 2 决策: {_count_actions(decisions)}")
        return decisions

    async def apply_decisions(self, decisions: list[dict]) -> dict:
        """将决策应用到 MemoryStore。

        Returns:
            {"added": int, "updated": int, "deleted": int, "skipped": int}
        """
        if not self._store:
            return {"added": 0, "updated": 0, "deleted": 0, "skipped": 0}

        stats = {"added": 0, "updated": 0, "deleted": 0, "skipped": 0}

        for d in decisions:
            action = d.get("action", "SKIP")
            content = d.get("content", "")
            memory_id = d.get("memory_id", "")
            mem_type = d.get("type", "FACT")
            session_id = d.get("session_id", "")

            try:
                if action == "ADD" and content:
                    collection = _type_to_collection(mem_type)
                    category = _type_to_category(mem_type)
                    mid = self._store.add(
                        collection=collection,
                        content=content,
                        metadata={
                            "source": "two_stage_extractor",
                            "category": category,
                            "source_session": session_id,
                            "helpful_count": 1,
                            "harmful_count": 0,
                        },
                    )
                    if mid:
                        stats["added"] += 1

                elif action == "UPDATE" and memory_id and content:
                    ok = self._store.update(memory_id, content=content)
                    if ok:
                        self._store.increment_feedback(memory_id, "helpful")
                        stats["updated"] += 1
                    else:
                        # memory_id 不存在时回退为 ADD
                        collection = _type_to_collection(mem_type)
                        mid = self._store.add(collection=collection, content=content,
                                              metadata={"source": "two_stage_extractor",
                                                        "helpful_count": 1, "harmful_count": 0})
                        if mid:
                            stats["added"] += 1

                elif action == "DELETE" and memory_id:
                    ok = self._store.delete(memory_id)
                    if ok:
                        stats["deleted"] += 1

                else:
                    stats["skipped"] += 1

            except Exception as e:
                logger.warning(f"应用决策失败 [{action}]: {e}")
                stats["skipped"] += 1

        logger.info(f"两阶段提取结果: {stats}")
        return stats

    # ── Stage 1: 提取 ────────────────────────────────────────────

    async def _stage1_extract(self, messages: list[dict],
                               llm: Any = None) -> list[dict]:
        """Stage 1: 从对话中提取事实/偏好/教训。"""
        if llm:
            return await self._llm_extract(messages, llm)
        return self._rule_extract(messages)

    async def _llm_extract(self, messages: list[dict], llm: Any) -> list[dict]:
        """LLM 提取。"""
        parts = []
        for msg in messages[-30:]:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if content and role in ("user", "assistant"):
                parts.append(f"[{role}] {content[:300]}")
        dialogue = "\n".join(parts[-20:])

        try:
            resp = await llm.chat([
                {"role": "system", "content": _EXTRACT_SYSTEM},
                {"role": "user", "content": f"对话内容:\n{dialogue[:4000]}"},
            ])
            text = resp.get("content", "").strip()
            return _parse_json_array(text)
        except Exception as e:
            logger.warning(f"Stage 1 LLM 提取失败: {e}")
            return self._rule_extract(messages)

    def _rule_extract(self, messages: list[dict]) -> list[dict]:
        """规则回退提取（无 LLM 时）。"""
        extractions = []

        # 偏好检测
        pref_kw = ["喜欢", "偏好", "习惯", "总是用", "prefer", "always use",
                    "不喜欢", "不要用", "don't like", "never use"]
        # 纠正检测
        correction_kw = ["不对", "错了", "应该是", "不是这样", "wrong", "incorrect"]

        for msg in messages:
            if msg.get("role") != "user":
                continue
            content = msg.get("content", "")
            if not content or len(content) < 5:
                continue

            # 偏好
            if any(kw in content.lower() for kw in pref_kw):
                extractions.append({"type": "PREFERENCE", "content": content[:200]})
            # 纠正 → 教训
            elif any(kw in content.lower() for kw in correction_kw):
                extractions.append({"type": "LESSON", "content": f"用户纠正: {content[:200]}"})

        return extractions

    # ── Stage 2: 决策 ────────────────────────────────────────────

    async def _stage2_decide(self, extractions: list[dict],
                              llm: Any) -> list[dict]:
        """Stage 2: 对比已有记忆，决定 ADD/UPDATE/DELETE/SKIP。"""
        # 获取已有记忆摘要
        existing_summary = self._get_existing_summary()

        # 构建提取结果文本
        extract_text = json.dumps(extractions, ensure_ascii=False, indent=2)

        prompt = (
            f"新提取的信息:\n{extract_text}\n\n"
            f"已有记忆:\n{existing_summary}\n\n"
            "对比新旧信息，为每条新信息决定动作(ADD/UPDATE/DELETE/SKIP):"
        )

        try:
            resp = await llm.chat([
                {"role": "system", "content": _DECIDE_SYSTEM},
                {"role": "user", "content": prompt[:6000]},
            ])
            text = resp.get("content", "").strip()
            decisions = _parse_json_array(text)

            # 确保每个决策都有必要字段
            for d in decisions:
                d.setdefault("action", "ADD")
                d.setdefault("content", "")
                d.setdefault("memory_id", "")
                # 从提取结果中继承 type
                d.setdefault("type", "FACT")

            return decisions
        except Exception as e:
            logger.warning(f"Stage 2 LLM 决策失败: {e}")
            # 回退: 全部 ADD
            return [
                {"action": "ADD", "content": e["content"],
                 "type": e.get("type", "FACT"), "memory_id": ""}
                for e in extractions
            ]

    def _get_existing_summary(self) -> str:
        """获取已有记忆的摘要（用于 Stage 2 对比）。"""
        if not self._store:
            return "无已有记忆"

        memories = self._store.get_all(limit=100)
        if not memories:
            return "无已有记忆"

        lines = []
        for mem in memories:
            content = mem.content[:100] if mem.content else ""
            lines.append(f"[{mem.id}] {content}")

        return "\n".join(lines[:50])


# ── Helper ──────────────────────────────────────────────────

def _type_to_collection(mem_type: str) -> str:
    """将提取类型映射到 collection。"""
    mapping = {
        "FACT": "facts",
        "PREFERENCE": "facts",
        "LESSON": "lessons",
    }
    return mapping.get(mem_type, "lessons")


def _type_to_category(mem_type: str) -> str:
    """将提取类型映射到 category。"""
    mapping = {
        "FACT": "general",
        "PREFERENCE": "user_pref",
        "LESSON": "method",
    }
    return mapping.get(mem_type, "general")


def _parse_json_array(text: str) -> list[dict]:
    """从 LLM 输出中解析 JSON 数组。"""
    text = text.strip()
    # 处理 markdown code block 包裹
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        text = text.strip()

    try:
        result = json.loads(text)
        if isinstance(result, list):
            return result
    except json.JSONDecodeError:
        pass

    # 尝试从文本中提取 JSON 数组
    import re
    match = re.search(r'\[.*\]', text, re.DOTALL)
    if match:
        try:
            result = json.loads(match.group())
            if isinstance(result, list):
                return result
        except json.JSONDecodeError:
            pass

    return []


def _count_actions(decisions: list[dict]) -> str:
    """统计动作计数。"""
    counts: dict[str, int] = {}
    for d in decisions:
        action = d.get("action", "SKIP")
        counts[action] = counts.get(action, 0) + 1
    return ", ".join(f"{k}={v}" for k, v in counts.items())
