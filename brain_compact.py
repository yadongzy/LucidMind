"""Brain Compact Mixin — 上下文压缩、token估算、消息清洗、Memory Flush。

从 brain_resilience.py 拆分，负责:
- _estimate_tokens / _estimate_history_tokens: token 估算
- _find_safe_cut_point: 安全截断（保护 tool_calls/tool 配对）
- _memory_flush_before_compact: 压缩前持久化
- _smart_compact_history: 统一上下文窗口管理
- _compact_history_if_needed: 轮间工具结果截断
- _sanitize_messages: 消息清洗
"""

import asyncio
import re
from pathlib import Path
from datetime import datetime, timezone

from logs import get_logger
from brain_config import (
    COMPACT_SKIP_TOKENS, COMPACT_SKIP_MSGS, COMPACT_PRUNE_TOKENS,
    COMPACT_PRUNE_TOOL_CHARS, COMPACT_PRUNE_HEAD_CHARS, COMPACT_PRUNE_TAIL_CHARS,
    COMPACT_FULL_TOKENS, COMPACT_FULL_MSGS, COMPACT_KEEP_RECENT,
    COMPACT_INLINE_TOOL_CHARS, COMPACT_INLINE_HEAD_CHARS, COMPACT_INLINE_TAIL_CHARS,
    COMPACT_SUMMARY_PROMPT, SUMMARY_TIMEOUT_SEC,
    MEMORY_FLUSH_PROMPT, MEMORY_FLUSH_TIMEOUT_SEC, MEMORY_FLUSH_MAX_CHARS,
)

_MEMORY_DIR = Path(__file__).parent / "data" / "memory"

logger = get_logger("brain")


class BrainCompactMixin:
    """上下文压缩 + token 估算 + 消息清洗混入。"""

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        """估算文本 token 数：中文约1.5字/token，英文约4字符/token。"""
        if not text:
            return 0
        cn = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
        en = len(text) - cn
        return int(cn / 1.5 + en / 4)

    def _estimate_history_tokens(self) -> int:
        """估算当前历史的总 token 数。"""
        return sum(self._estimate_tokens(m.get("content") or "") for m in self._history)

    def _find_safe_cut_point(self, start: int, end: int) -> int:
        """在 [start, end) 范围内找到安全的截断点，不破坏 tool_calls/tool 配对。"""
        cut = start
        while cut < end:
            msg = self._history[cut]
            prev = self._history[cut - 1] if cut > 0 else {}
            if msg.get("role") == "tool" or prev.get("tool_calls"):
                cut += 1
            else:
                return cut
        return end

    async def _memory_flush_before_compact(self, session_id: str,
                                             old_messages: list[dict]) -> None:
        """压缩前 Memory Flush — 将即将丢失的对话持久化到 Markdown 文件。

        对标 OpenClaw memory-flush.ts：压缩前自动提取关键信息写入磁盘，
        确保压缩后仍可通过 memory.search() 找回。
        """
        if not old_messages:
            return
        # 构建 flush 文本
        flush_lines = []
        char_count = 0
        for m in old_messages:
            role = m.get("role", "")
            content = (m.get("content") or "").strip()
            if not content or role not in ("user", "assistant"):
                continue
            line = f"{role}: {content[:200]}"
            flush_lines.append(line)
            char_count += len(line)
            if char_count > MEMORY_FLUSH_MAX_CHARS:
                break
        if not flush_lines:
            return
        flush_text = "\n".join(flush_lines)

        # 方案A: 有 LLM 时用 LLM 提取关键信息
        extracted = None
        try:
            prompt = MEMORY_FLUSH_PROMPT.replace("{flush_text}", flush_text)
            resp = await asyncio.wait_for(
                self.llm.chat([{"role": "user", "content": prompt}], tools=None),
                timeout=MEMORY_FLUSH_TIMEOUT_SEC
            )
            raw = resp.get("content", "").strip()
            raw = re.sub(r"<think>.*?</think>\s*", "", raw, flags=re.DOTALL).strip()
            if raw and raw != "无" and len(raw) > 10:
                extracted = raw
        except Exception as e:
            logger.debug(f"[{session_id}] Memory Flush LLM 提取失败({e})，回退规则提取")

        # 方案B: LLM 失败时用规则提取（保留 user 消息）
        if not extracted:
            user_lines = [l for l in flush_lines if l.startswith("user:")]
            if user_lines:
                extracted = "\n".join(f"- {l[6:]}" for l in user_lines[-5:])

        if not extracted:
            return

        # 写入 Markdown 文件
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        _MEMORY_DIR.mkdir(parents=True, exist_ok=True)
        md_path = _MEMORY_DIR / f"{today}.md"
        header = f"\n## {datetime.now(timezone.utc).strftime('%H:%M')} 会话记忆\n"
        try:
            if md_path.exists():
                existing = md_path.read_text(encoding="utf-8")
                # 去重: 如果前50字符已存在则跳过
                if extracted[:50] in existing:
                    logger.debug(f"[{session_id}] Memory Flush 跳过重复内容")
                    return
                md_path.write_text(existing + header + extracted + "\n",
                                   encoding="utf-8")
            else:
                md_path.write_text(
                    f"# {today} 记忆日志\n" + header + extracted + "\n",
                    encoding="utf-8")
            logger.info(f"[{session_id}] Memory Flush: {len(extracted)}字 → {md_path.name}")
        except Exception as e:
            logger.warning(f"[{session_id}] Memory Flush 写入失败: {e}")
            return

        # 同步写入 MemoryStore（确保 search 可检索）
        if self.memory:
            try:
                for line in extracted.split("\n"):
                    line = line.strip().lstrip("- ").strip()
                    if line and len(line) > 5:
                        await self.memory.save(
                            key=f"flush_{today}_{hash(line) & 0xFFFF:04x}",
                            value=line,
                            category="sessions"
                        )
            except Exception as e:
                logger.debug(f"[{session_id}] Memory Flush 存入 MemoryStore 失败: {e}")

    async def _smart_compact_history(self, session_id: str) -> None:
        """统一上下文窗口管理 — token-aware 压缩，保护 tool_calls/tool 配对。

        策略（基于 token 估算，已回退到 v1.7 验证阈值）：
        - 阶段0: <COMPACT_SKIP_TOKENS 且 <=COMPACT_SKIP_MSGS → 不处理
        - 阶段0.5: Memory Flush — 压缩前持久化即将丢失的内容
        - 阶段1: 截断过长工具结果
        - 阶段2: >COMPACT_FULL_TOKENS 或 >COMPACT_FULL_MSGS → LLM摘要压缩
        - 阶段3: 摘要失败 → 安全截断（保护 tool_calls/tool 配对）
        """
        hist_len = len(self._history)
        total_tokens = self._estimate_history_tokens()

        if total_tokens < COMPACT_SKIP_TOKENS and hist_len <= COMPACT_SKIP_MSGS:
            return

        # 阶段1: 截断过长工具结果
        if total_tokens > COMPACT_PRUNE_TOKENS:
            for m in self._history:
                if m.get("role") == "tool" and len(m.get("content", "")) > COMPACT_PRUNE_TOOL_CHARS:
                    m["content"] = (m["content"][:COMPACT_PRUNE_HEAD_CHARS]
                                    + "\n...(已压缩)...\n"
                                    + m["content"][-COMPACT_PRUNE_TAIL_CHARS:])
            total_tokens = self._estimate_history_tokens()

        # 阶段2: 需要摘要压缩
        if total_tokens < COMPACT_FULL_TOKENS and hist_len <= COMPACT_FULL_MSGS:
            return

        keep_recent = COMPACT_KEEP_RECENT
        if hist_len <= keep_recent + 2:
            return

        # 找安全截断点
        cut = self._find_safe_cut_point(max(hist_len - keep_recent - 2, 0), hist_len - keep_recent)
        old_messages = self._history[:cut]
        recent_messages = self._history[cut:]

        if not old_messages:
            return

        # 阶段0.5: Memory Flush — 压缩前持久化
        try:
            await self._memory_flush_before_compact(session_id, old_messages)
        except Exception as e:
            logger.debug(f"[{session_id}] Memory Flush 异常(不影响压缩): {e}")

        # 尝试 LLM 摘要
        try:
            summary_lines = []
            for m in old_messages:
                role = m.get("role", "")
                content = (m.get("content") or "")[:150]
                if content and role in ("user", "assistant"):
                    summary_lines.append(f"{role}: {content}")
            summary_text = "\n".join(summary_lines[-20:])

            if summary_text:
                prompt_text = COMPACT_SUMMARY_PROMPT.replace("{summary_text}", summary_text)
                resp = await asyncio.wait_for(
                    self.llm.chat([{"role": "user", "content": prompt_text}],
                        tools=None),
                    timeout=SUMMARY_TIMEOUT_SEC
                )
                summary_content = resp.get("content", "").strip()
                summary_content = re.sub(r"<think>.*?</think>\s*", "", summary_content, flags=re.DOTALL).strip()
                if summary_content and len(summary_content) > 20:
                    self._history = [{"role": "system", "content": f"[对话摘要] {summary_content}"}] + recent_messages
                    logger.info(f"[{session_id}] LLM摘要压缩: {hist_len}→{len(self._history)}条, "
                                f"{total_tokens}→{self._estimate_history_tokens()} tokens")
                    return
        except Exception as e:
            logger.debug(f"[{session_id}] LLM摘要失败({e})，回退安全截断")

        # 阶段3: 回退 — 安全截断（保护配对）
        self._history = recent_messages
        logger.info(f"[{session_id}] 安全截断: {hist_len}→{len(self._history)}条")

    def _compact_history_if_needed(self) -> None:
        """轮间压缩 — 仅截断超长工具结果，不做消息级压缩（由 _smart_compact_history 统一处理）。"""
        for m in self._history:
            if m.get("role") == "tool" and len(m.get("content", "")) > COMPACT_INLINE_TOOL_CHARS:
                m["content"] = (m["content"][:COMPACT_INLINE_HEAD_CHARS]
                                + "\n...(已压缩)...\n"
                                + m["content"][-COMPACT_INLINE_TAIL_CHARS:])

    def _sanitize_messages(self, messages: list[dict]) -> None:
        """清洗消息列表，修复 tool_calls/tool 配对问题，防止 LLM API 400。"""
        valid_tool_ids = set()
        to_remove = []
        for i, m in enumerate(messages):
            if m.get("role") == "assistant" and m.get("tool_calls"):
                for tc in m["tool_calls"]:
                    if not tc.get("id"):
                        tc["id"] = f"call_{id(tc)}"
                    if "type" not in tc:
                        tc["type"] = "function"
                    valid_tool_ids.add(tc["id"])
            elif m.get("role") == "tool":
                tid = m.get("tool_call_id", "")
                if not tid:
                    m["tool_call_id"] = f"call_{id(m)}"
                if tid and tid not in valid_tool_ids:
                    to_remove.append(i)
        for i in reversed(to_remove):
            logger.warning(f"清洗: 移除孤立 tool 消息 (tool_call_id={messages[i].get('tool_call_id')})")
            messages.pop(i)
