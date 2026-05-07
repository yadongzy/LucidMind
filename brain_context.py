"""Brain Context Mixin — 消息构建、流式输出、身份加载。

从 brain.py 拆分，负责:
- _build_messages: 构建 LLM 消息列表
- _build_self_awareness: 动态生成自我感知上下文
- _stream_final_reply: 流式/伪流式最终回复
- 身份文件加载与缓存
"""

import asyncio
import datetime
import os
import platform
import re
import time
from pathlib import Path

from brain_config import (
    MAX_SYSTEM_PROMPT_TOKENS, MAX_HISTORY_HARD_LIMIT,
    LOCAL_MODEL_HISTORY_LIMIT, REMOTE_MODEL_HISTORY_LIMIT,
    LOCAL_SOUL_MAX_LINES, PSEUDO_STREAM_CHUNK_SIZE, PSEUDO_STREAM_DELAY_SEC,
    TOOL_USAGE_HINTS, EMPTY_REPLY_FALLBACK,
)
from logs import get_logger

logger = get_logger("brain")

_IDENTITY_DIR = Path(__file__).parent / "identity"
_CORE_PATH = _IDENTITY_DIR / "CORE.md"
_SOUL_PATH = _IDENTITY_DIR / "SOUL.md"


class BrainContextMixin:
    """消息构建 + 流式输出 + 身份工具方法。"""

    _identity_cache: dict = {}   # path_str -> {mtime, content}

    def _load_identity_file(self, path: Path) -> str:
        """加载身份文件，带文件修改时间缓存。"""
        if not path.exists():
            return ""
        try:
            key = str(path)
            mtime = path.stat().st_mtime
            cached = self._identity_cache.get(key)
            if cached and cached["mtime"] == mtime:
                return cached["content"]
            content = path.read_text(encoding="utf-8").strip()
            self._identity_cache[key] = {"mtime": mtime, "content": content}
            return content
        except Exception:
            return ""

    def _extract_thinking(self, response: dict) -> str:
        """从 LLM 响应中提取真实思考内容。

        来源 1: reasoning_content（DeepSeek-R1 原生推理字段）
        来源 2: <think> 标签（SOUL.md 引导）
        都没有 → 返回空字符串，不伪造
        """
        # 来源 1
        if response.get("reasoning_content"):
            return response["reasoning_content"]

        # 来源 2
        content = response.get("content", "")
        if content:
            match = re.search(r"<think>(.*?)</think>", content, re.DOTALL)
            if match:
                return match.group(1).strip()

        return ""

    async def _metacognize(self, user_input: str, tools: list | None) -> str:
        """S35: 真实元认知 — 用 LLM 做意图分析，替代关键词匹配。"""
        from metacognition import metacognize
        return await metacognize(user_input, self._history, tools, self.llm)

    def _reload_soul_if_changed(self) -> None:
        """检查身份文件是否被修改，变化时重新加载。"""
        parts = [self._load_identity_file(p) for p in [_CORE_PATH, _SOUL_PATH]]
        parts = [p for p in parts if p]
        if parts:
            self._soul_prompt = "\n\n".join(parts)
            self._soul_mtime = 1

    def _is_local_model(self) -> bool:
        """检测当前是否只有本地模型可用。"""
        if hasattr(self.llm, 'is_local_only'):
            return self.llm.is_local_only()
        return getattr(self.llm, '_is_local', False)

    def _build_self_awareness(self) -> str:
        """S8: 动态生成自我感知上下文。本地模型时精简版。"""
        local = self._is_local_model()
        s = []
        if self.tools:
            try:
                tools_list = self.tools.list_tools()
                if local:
                    names = [t['function']['name'] for t in tools_list]
                    s.append(f"可用工具: {', '.join(names)}")
                else:
                    s.append("可用工具:\n" + "\n".join(f"- {t['function']['name']}: {t['function'].get('description','')[:60]}" for t in tools_list))
                    # P1c: 工具使用强化 — few-shot 提示
                    s.append(TOOL_USAGE_HINTS)
            except Exception:
                s.append("可用工具: 获取失败")
        s.append(f"模型: {getattr(self.llm, 'model', '?')} | 时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        if not local:
            win = " (注意: 不要用Linux/macOS命令)" if platform.system() == "Windows" else ""
            s.extend([f"记忆: {'ON' if self.memory else 'OFF'} | 学习: {'ON' if self.learning else 'OFF'}",
                f"环境: {platform.system()} {platform.release()}{win} | 目录: {os.getcwd()}",
                f"历史: {len(self._history)}条 | 安全: 禁止危险命令; 禁止访问 .env/.git"])
            # Codex 能力声明 — 让 LLM 知道自己确实能调用 Codex
            if self.tools:
                tool_names = [t['function']['name'] for t in (self.tools.list_tools() or [])]
                if 'codex' in tool_names:
                    s.append("重要能力: 你已接入本机 Codex CLI（OpenAI Codex），可通过 codex 工具执行: explain(解释代码)、review(代码审查)、patch(修复代码)、heal(自愈体检)。当用户问你能否调用 Codex 时，回答「可以」并说明用法。")
        return "\n".join(s)

    async def _build_messages(self, skip_lessons: bool = False) -> list[dict]:
        """构建发送给 LLM 的消息列表。本地模型时精简 prompt。
        
        Prompt 结构优化（缓存友好）：
        静态前缀（不变，触发 Gemini/OpenAI 隐式缓存 75-90% 折扣）：
          SOUL.md → USER.md → 角色人格 → 知识技能 → 首次引导
        动态后缀（每次变化，不影响前缀缓存命中）：
          当前状态 → 目标 → 经验 → 自省
        """
        local = self._is_local_model()
        user_id = self._current_user_id()

        messages = []
        # ── 静态前缀（缓存友好：请求间保持不变）──
        # 通过 UserIdentityManager 加载: CORE + SOUL + USER + profile + custom_prompts
        _profile_ctx = self._profile_adapter.get_context_prompt(user_id)
        system_content = self._identity_mgr.build_identity_prompt(user_id, profile_context=_profile_ctx)
        if system_content:
            if local:
                soul_lines = system_content.splitlines()[:LOCAL_SOUL_MAX_LINES]
                system_content = "\n".join(soul_lines)
            # P2a: 多角色人格注入（静态：角色不会每次调用都换）
            if self._persona_manager:
                persona_prompt = self._persona_manager.get_persona_prompt()
                if persona_prompt:
                    system_content += f"\n\n## 当前角色\n{persona_prompt}"
            # 知识型技能注入（静态：技能不会每次调用都换）
            try:
                from skills.token_budget import get_prompt_skills_content
                _prompt_skills = get_prompt_skills_content()
                if _prompt_skills:
                    system_content += f"\n\n## 知识技能\n{_prompt_skills}"
            except Exception:
                pass
            # BUG-5 fix: Letta Blocks 直注 — 核心记忆零延迟注入
            _bm = getattr(self, "_block_manager", None)
            if _bm:
                _blocks_text = _bm.format_for_prompt()
                if _blocks_text:
                    system_content += f"\n\n## 核心记忆\n{_blocks_text}"
            # 首次引导检测（per-user）
            bootstrap_text = self._identity_mgr.get_bootstrap(user_id)
            if bootstrap_text and "BOOTSTRAP_COMPLETE" not in bootstrap_text:
                system_content += f"\n\n## 首次启动引导\n{bootstrap_text}"

            # ── 动态后缀（每次变化，放在最后不影响前缀缓存）──
            dynamic_sections = []
            awareness = self._build_self_awareness()
            dynamic_sections.append(f"\n\n## 当前状态\n{awareness}")
            if self._goal_context:
                dynamic_sections.append(f"\n\n{self._goal_context}")
            # 经验库注入 — 受A/B开关控制 + P0快速路径控制
            if self.lessons_enabled and not skip_lessons:
                lessons_text = await self._get_relevant_lessons()
                if lessons_text:
                    dynamic_sections.append(f"\n\n## 过往经验（参考）\n{lessons_text}")
            if not local and self._reflection_text:
                dynamic_sections.append(f"\n\n## 自省\n{self._reflection_text}")

            # Token 预算控制：超预算时从动态后缀末尾裁剪
            base_tokens = self._estimate_tokens(system_content)
            for section in dynamic_sections:
                section_tokens = self._estimate_tokens(section)
                if base_tokens + section_tokens <= MAX_SYSTEM_PROMPT_TOKENS:
                    system_content += section
                    base_tokens += section_tokens
                else:
                    logger.debug(f"System prompt 预算已满({base_tokens} tokens)，跳过 {len(section)} 字符")
            messages.append({"role": "system", "content": system_content})

        # 历史条数限制 — 本地模型6条，远程模型20条（防止 prompt 无限膨胀）
        hist = self._history
        if local and len(hist) > LOCAL_MODEL_HISTORY_LIMIT:
            hist = [m for m in hist if m.get("role") in ("user", "assistant") and "tool_calls" not in m][-LOCAL_MODEL_HISTORY_LIMIT:]
        elif not local and len(hist) > REMOTE_MODEL_HISTORY_LIMIT:
            hist = hist[-REMOTE_MODEL_HISTORY_LIMIT:]
        messages.extend(hist)
        self._sanitize_messages(messages)
        return messages

    async def _stream_final_reply(self, session_id: str, messages: list, response: dict, t0: float, _s=None) -> str:
        """最终回复：优先真流式，降级伪流式。"""
        _s = _s or self.stream
        raw = response.get("content", "")
        content = re.sub(r"<think>.*?</think>\s*", "", raw, flags=re.DOTALL).strip() if raw else ""
        _already_streamed = False

        # 真流式：非流式返回空时用 stream=True 重调
        if not content and not response.get("tool_calls"):
            try:
                stream_iter = await self.llm.chat(messages, tools=None, stream=True)
                if hasattr(stream_iter, '__aiter__'):
                    await _s.emit("response_start", None)
                    chunks = []
                    in_think = False
                    async for chunk in stream_iter:
                        if "<think>" in chunk:
                            in_think = True
                        if in_think:
                            if "</think>" in chunk:
                                in_think = False
                                chunk = chunk.split("</think>", 1)[-1]
                                if not chunk:
                                    continue
                            else:
                                continue
                        chunks.append(chunk)
                        await _s.emit("response_delta", chunk)
                    await _s.emit("response_end", None)
                    content = "".join(chunks).strip()
                    _already_streamed = True
                    if content:
                        logger.info(f"[{session_id}] 真流式输出完成: {len(content)} 字符")
            except Exception as e:
                logger.debug(f"[{session_id}] 真流式失败({e})，降级伪流式")

        # 空回复自救：工具已执行但回复为空，追加强制总结提示再试一次
        if not content and not _already_streamed:
            has_tool_results = any(m.get("role") == "tool" for m in messages)
            if has_tool_results:
                logger.warning(f"[{session_id}] 工具已执行但回复为空，尝试强制总结")
                rescue_messages = messages + [{"role": "user", "content":
                    "[系统] 你已经成功执行了工具并获得了结果。请根据上面的工具返回内容，"
                    "直接用自然语言回复用户的问题。不要再调用任何工具，直接给出回答。"}]
                try:
                    rescue_resp = await self._llm_call_with_retry(session_id, rescue_messages, tools=None, _s=_s)
                    rescue_raw = rescue_resp.get("content", "")
                    content = re.sub(r"<think>.*?</think>\s*", "", rescue_raw, flags=re.DOTALL).strip() if rescue_raw else ""
                    if content:
                        logger.info(f"[{session_id}] 空回复自救成功: {len(content)} 字符")
                except Exception as e:
                    logger.warning(f"[{session_id}] 空回复自救失败: {e}")

        content = content or EMPTY_REPLY_FALLBACK
        if not content.strip(): logger.warning(f"[{session_id}] LLM 返回空内容")

        if not _already_streamed:
            chunk_size = PSEUDO_STREAM_CHUNK_SIZE
            if len(content) > chunk_size * 2:
                await _s.emit("response_start", None)
                for i in range(0, len(content), chunk_size):
                    await _s.emit("response_delta", content[i:i+chunk_size])
                    await asyncio.sleep(PSEUDO_STREAM_DELAY_SEC)
                await _s.emit("response_end", None)
            else:
                await _s.emit("response", content)
        elapsed = time.time() - t0
        usage = response.get("usage", {}); total_tokens = usage.get("total_tokens", 0)
        info_text = f"耗时 {elapsed:.1f}s" + (f" · {total_tokens} tokens" if usage else "")
        await _s.emit("info", info_text)
        self._history.append({"role": "assistant", "content": content})
        if self.memory:
            await self.memory.save_message(session_id, {"role": "assistant", "content": content})
        mode = "with_lessons" if self.lessons_enabled else "without_lessons"
        self._ab_stats[mode].append({"elapsed": round(elapsed, 2), "tokens": total_tokens, "response_len": len(content), "ts": time.time()})
        self._ab_stats[mode] = self._ab_stats[mode][-100:]; self._save_ab_stats()
        logger.info(f"[{session_id}] 回复完成(流式推送): {content[:80]}...")
        # P1: 消息计数 → 空闲同步 + Curator 清理
        self._session_msg_counter[session_id] = self._session_msg_counter.get(session_id, 0) + 1
        if self._session_msg_counter[session_id] % self._SYNC_EVERY_N_MSGS == 0 and self.learning:
            asyncio.create_task(self._idle_sync_and_cleanup(session_id))
        if len(self._history) > MAX_HISTORY_HARD_LIMIT:  # 安全截断：保护 tool_calls/tool 配对
            self._history = self._history[self._find_safe_cut_point(len(self._history)-50, len(self._history)-40):]
        try:
            from memory_journal import save_conversation_summary
            user_msg = next((m["content"] for m in reversed(messages) if m.get("role") == "user"), "")
            tl = [tc["function"]["name"] for tc in response.get("tool_calls", [])] if response.get("tool_calls") else []
            save_conversation_summary(session_id, user_msg, content, tl)
        except Exception: pass
        return content
