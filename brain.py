"""LucidMind Brain — 核心大脑，唯一主入口。

Brain 只认识 Port（接口），不认识 Adapter（实现）。
所有外部交互通过 Port 完成。
"""

import asyncio
import datetime
import json
import os
import pathlib
import platform
import re
import time
from pathlib import Path

from ports.llm_port import LLMPort
from ports.tool_port import ToolPort
from ports.memory_port import MemoryPort
from ports.stream_port import StreamPort
from ports.learning_port import LearningPort
from ports.reflection_port import ReflectionPort
from brain_resilience import BrainResilienceMixin
from brain_learning import BrainLearningMixin
from brain_tool_guard import BrainToolGuardMixin
from tool_call_parser import parse_xml_tool_calls, strip_xml_tool_calls
from brain_intent import BrainIntentMixin
from brain_perf import compress_tool_result, dynamic_max_tool_rounds
from brain_fast_path import classify as _fast_classify
from brain_config import (
    TOOL_LOOP_TIMEOUT_SEC, MAX_SYSTEM_PROMPT_TOKENS,
    MAX_HISTORY_HARD_LIMIT, LOCAL_MODEL_HISTORY_LIMIT, REMOTE_MODEL_HISTORY_LIMIT,
    LOCAL_SOUL_MAX_LINES, LLM_MAX_RETRIES, LLM_BASE_DELAY_SEC,
    PSEUDO_STREAM_CHUNK_SIZE, PSEUDO_STREAM_DELAY_SEC,
    LOOP_HINT, FAIL_HINT, TOOL_USAGE_HINTS, EMPTY_REPLY_FALLBACK,
    TOOL_INFERENCE_MAP,
)
from logs import get_logger

logger = get_logger("brain")

_IDENTITY_DIR = Path(__file__).parent / "identity"
_CORE_PATH = _IDENTITY_DIR / "CORE.md"
_SOUL_PATH = _IDENTITY_DIR / "SOUL.md"
_USER_PATH = _IDENTITY_DIR / "USER.md"
_BOOTSTRAP_PATH = _IDENTITY_DIR / "BOOTSTRAP.md"



class Brain(BrainResilienceMixin, BrainLearningMixin, BrainToolGuardMixin, BrainIntentMixin):
    """LucidMind 的核心大脑。"""

    def __init__(
        self,
        llm: LLMPort,
        stream: StreamPort,
        tools: ToolPort | None = None,
        memory: MemoryPort | None = None,
        learning: LearningPort | None = None,
        reflection: ReflectionPort | None = None,
    ):
        self.llm = llm
        self.stream = stream
        self.tools = tools
        self.memory = memory
        self.learning = learning
        self.reflection = reflection
        self._sessions: dict[str, list[dict]] = {}
        self._current_sid: str = "default"
        self.ralph_max_retries = LLM_MAX_RETRIES
        self.ralph_base_delay = LLM_BASE_DELAY_SEC
        self._soul_prompt = ""
        self._soul_mtime: float = 0.0
        self._reflection_text = ""
        self._awake = False
        self._goal_context = ""
        self.lessons_enabled = True  # A/B开关：经验注入
        self._ab_stats: dict[str, list] = self._load_ab_stats()  # A/B质量追踪（持久化）
        self._persona_manager = None  # P2a: 多角色系统（延迟初始化）
        self._reload_soul_if_changed()

    _AB_STATS_PATH = Path(__file__).parent / "data" / "ab_stats.json"

    @classmethod
    def _load_ab_stats(cls) -> dict[str, list]:
        """从 data/ab_stats.json 加载 A/B 追踪数据。"""
        try:
            if cls._AB_STATS_PATH.exists():
                data = json.loads(cls._AB_STATS_PATH.read_text())
                if isinstance(data, dict):
                    return {
                        "with_lessons": data.get("with_lessons", [])[-100:],
                        "without_lessons": data.get("without_lessons", [])[-100:],
                    }
        except Exception:
            pass
        return {"with_lessons": [], "without_lessons": []}

    def _save_ab_stats(self) -> None:
        """持久化 A/B 追踪数据到 data/ab_stats.json。"""
        try:
            self._AB_STATS_PATH.parent.mkdir(parents=True, exist_ok=True)
            self._AB_STATS_PATH.write_text(json.dumps(self._ab_stats, ensure_ascii=False))
        except Exception:
            pass

    def set_stream(self, stream: StreamPort) -> None:
        self.stream = stream

    @property
    def _history(self) -> list[dict]:
        return self._sessions.setdefault(self._current_sid, [])

    @_history.setter
    def _history(self, value: list[dict]):
        self._sessions[self._current_sid] = value

    async def switch_session(self, session_id: str) -> None:
        self._current_sid = session_id
        if not self._sessions.get(session_id) and self.memory:
            stored = await self.memory.get_context(session_id)
            if stored: self._sessions[session_id] = stored
            logger.info(f"[{session_id}] 切换会话，加载 {len(stored) if stored else 0} 条历史")
        await self.stream.emit("info", f"📋 已切换到会话 {session_id}")

    async def process(self, session_id: str, user_input: str, stream: "StreamPort | None" = None) -> dict:
        """处理用户输入 — Brain 唯一主入口。stream: 可选局部流引用（D1竞态修复）。"""
        _s = stream or self.stream
        self._current_sid, t0 = session_id, time.time()
        _result = {"tool_calls_happened": False, "reply": "", "empty_promise_detected": False}
        logger.info(f"[{session_id}] 收到用户输入: {user_input[:100]}")

        try:
            # P0: 快速路径分类 — 减少不必要的 LLM 调用
            _fp = _fast_classify(user_input, len(self._history))
            logger.info(f"[{session_id}] 快速路径: {_fp}")

            await self._smart_compact_history(session_id)
            if not self._history and self.memory:
                stored = await self.memory.get_context(session_id)
                if stored:
                    self._history = stored
                    logger.info(f"[{session_id}] 从记忆恢复 {len(stored)} 条历史")

            if self.reflection:
                ref = await self.reflection.on_user_message(session_id, user_input)
                if ref.get("repeated"):
                    await _s.emit("info", f"🔄 检测到重复提问 (第{ref['similar_count']+1}次) — 我会尝试给出更好的回答")
                self._reflection_text = await self.reflection.get_reflection(session_id)

            self._history.append({"role": "user", "content": user_input})
            if self.memory:
                await self.memory.save_message(session_id, {"role": "user", "content": user_input})

            tools = self.tools.list_tools() if self.tools else None
            # Token 预算：工具定义过多时裁剪（技能架构改进3）
            if tools:
                try:
                    from skills.token_budget import filter_tools_by_budget
                    tools = filter_tools_by_budget(tools)
                except Exception:
                    pass
            _tool_calls_happened = False
            _tool_steps: list[str] = []  # 追踪每个工具步骤用于任务进度更新
            if self.tools:
                if await self._pre_execute_intent(session_id, user_input, _s):
                    _tool_calls_happened = True

            # P0: 简单对话跳过元认知（省 1 次 LLM 调用，~3-5s）
            metacog = ""
            if not _fp.skip_metacog:
                metacog = await self._metacognize(user_input, tools)
            if metacog:
                await _s.emit("thinking", metacog)
            else:
                # 快速路径分析摘要 — 确保思考按钮开启时总有内容显示
                _thinking_map = {
                    "tool_use": "识别到工具意图，准备调用工具执行",
                    "greeting": "简单问候，直接回复",
                    "trivial": "简单对话",
                    "correction": "检测到纠正/教学意图",
                    "complex": "复杂任务，深度分析中",
                    "knowledge": "知识问答，检索相关经验后回答",
                }
                await _s.emit("thinking", f"分析: {_thinking_map.get(_fp.category, _fp.category)}")

            max_rounds = dynamic_max_tool_rounds(user_input, tools)
            deadline = time.time() + TOOL_LOOP_TIMEOUT_SEC
            for round_i in range(max_rounds + 1):
                self._compact_history_if_needed()
                messages = await self._build_messages(skip_lessons=_fp.skip_lessons)
                response = await self._llm_call_with_retry(session_id, messages, tools, _s=_s)

                thinking = self._extract_thinking(response)
                if thinking:
                    await _s.emit("thinking", thinking)

                tool_calls = response.get("tool_calls")
                if not tool_calls and self.tools:
                    xml_tcs = parse_xml_tool_calls(response.get("content", "") or "")
                    if xml_tcs:
                        tool_calls = xml_tcs
                        response["content"] = strip_xml_tool_calls(response.get("content", "") or "")
                        response["tool_calls"] = xml_tcs
                if not tool_calls or not self.tools:
                    # 检测"回复以承诺结尾"：工具已调用过，但最后一轮LLM说"让我..."却没调工具
                    final_text = (response.get("content", "") or "").strip()
                    if _tool_calls_happened and final_text and self._detect_empty_promise(final_text):
                        logger.warning(f"[{session_id}] 工具轮后检测到未兑现承诺: '{final_text[:60]}...'")
                        await _s.emit("info", "🔄 检测到未完成的操作承诺，继续执行...")
                        self._history.append({"role": "user", "content":
                            "[系统] 你刚才承诺要执行操作但没有调用工具。请立即使用工具完成操作，不要只是描述你要做什么。"})
                        continue  # 回到工具循环，让 LLM 重新产生工具调用
                    break
                if time.time() > deadline:
                    logger.warning(f"[{session_id}] 工具循环超时({TOOL_LOOP_TIMEOUT_SEC}s)")
                    await _s.emit("info", "⏱️ 工具执行超时，正在总结已有结果...")
                    self._history.append({"role": "user", "content": "[系统] 工具执行超时，请根据已获取的信息直接用文字回复用户，不要再调用工具。"})
                    messages = await self._build_messages()
                    response = await self._llm_call_with_retry(session_id, messages, tools=None, _s=_s)
                    break

                _tool_calls_happened = True
                _round_t0 = time.time()
                # 记录本轮工具名称用于步骤追踪 + 实时推送 tool_step 事件
                for _tc in tool_calls:
                    _fn = _tc.get("function", {}).get("name", "")
                    if _fn:
                        _tool_steps.append(_fn)
                        await _s.emit("tool_step", _fn)
                await self._execute_tool_round(session_id, tool_calls, response, _s)
                _round_elapsed = time.time() - _round_t0
                await _s.emit("info", f"⚡ 工具轮 {round_i + 1}/{max_rounds} 完成 ({_round_elapsed:.1f}s)")
                logger.info(f"[{session_id}] 工具轮 {round_i + 1} 完成 ({_round_elapsed:.1f}s)")

            content_text = response.get("content", "") or ""
            if not _tool_calls_happened and self.tools:
                response, guard_fixed = await self._guard_empty_promise(
                    session_id, user_input, response, messages, tools, _s=_s)
                if guard_fixed:
                    _tool_calls_happened = True
                    _result["empty_promise_detected"] = True
                else:
                    forced = await self._force_tool_if_faked(session_id, user_input, content_text, _s=_s)
                    if forced:
                        _tool_calls_happened = True
                        self._compact_history_if_needed()
                        messages = await self._build_messages()
                        response = await self._llm_call_with_retry(session_id, messages, tools, _s=_s)
                        retry_tcs = response.get("tool_calls")
                        if retry_tcs and self.tools:
                            await self._execute_tool_round(session_id, retry_tcs, response, _s)
                            self._compact_history_if_needed()
                            messages = await self._build_messages()
                            response = await self._llm_call_with_retry(session_id, messages, tools=None, _s=_s)
                        elif not retry_tcs:
                            await self._try_auto_provision_tool(session_id, user_input, _s=_s)

            # Post-tool-call 伪造检测：工具被调用了，但 LLM 可能在文本中伪造了其他操作
            # 例：调了 read_file 但声称"已删除文件"
            elif _tool_calls_happened and self.tools:
                content_text = response.get("content", "") or ""
                forced = await self._force_tool_if_faked(session_id, user_input, content_text, _s=_s)
                if forced:
                    self._compact_history_if_needed()
                    messages = await self._build_messages()
                    response = await self._llm_call_with_retry(session_id, messages, tools, _s=_s)
                    retry_tcs = response.get("tool_calls")
                    if retry_tcs and self.tools:
                        await self._execute_tool_round(session_id, retry_tcs, response, _s)
                        self._compact_history_if_needed()
                        messages = await self._build_messages()
                        response = await self._llm_call_with_retry(session_id, messages, tools=None, _s=_s)
                    _result["empty_promise_detected"] = True

            content = await self._stream_final_reply(session_id, messages, response, t0, _s)
            _result["tool_calls_happened"] = _tool_calls_happened
            _result["tool_steps"] = _tool_steps
            _result["reply"] = content

            # P0: 简单对话跳过学习检测（省 1-2 次 LLM 调用，~3-6s）
            if not _fp.skip_learn_detect:
                await self._detect_and_learn(session_id, user_input)
                await self._learn_from_inability(session_id, user_input, content)
            if _tool_calls_happened and hasattr(self, '_mark_lessons_effective'):
                await self._mark_lessons_effective(True)

        except Exception as e:
            logger.error(f"[{session_id}] 处理失败: {e}", exc_info=True)
            friendly = self._graceful_error_response(str(e))
            await _s.emit("error", f"Error: {e}")
            await _s.emit("response", friendly)
            _result["reply"] = friendly
            if hasattr(self, '_mark_lessons_effective'):
                await self._mark_lessons_effective(False)
            if self.learning:
                await self._learn_pattern(session_id, f"处理失败: {user_input[:50]}", str(e)[:200], source="error")

        finally:
            await _s.emit("complete", None)
            if _tool_calls_happened:
                asyncio.create_task(self._ace_reflect_and_merge(session_id))
            try:
                from diagnostics import DiagnosticEvent, get_collector
                get_collector().record(DiagnosticEvent(timestamp=t0, category="brain_process", action="process",
                    status="success" if _result.get("reply") else "failure", duration_ms=(time.time()-t0)*1000,
                    input_summary=user_input[:200], output_summary=(_result.get("reply") or "")[:200],
                    metadata={"session_id": session_id, "tool_calls": _tool_calls_happened}))
            except Exception: pass
            logger.info(f"[{session_id}] 处理完成")
            return _result

    async def _execute_tool_round(self, session_id: str, tool_calls: list, response: dict, _s=None) -> None:
        """执行一轮工具调用并将结果加入历史。"""
        _s = _s or self.stream
        formatted_tcs = [{"id": tc.get("id", ""), "type": "function",
            "function": tc.get("function", {})} for tc in tool_calls]
        self._history.append({"role": "assistant", "content": response.get("content") or None,
            "tool_calls": formatted_tcs})

        for tc in tool_calls:
            func = tc.get("function", {})
            tool_name = func.get("name", "")
            try:
                tool_params = json.loads(func.get("arguments", "{}"))
            except json.JSONDecodeError:
                tool_params = {}

            await _s.emit("tool_call", f"🔧 {tool_name}({json.dumps(tool_params, ensure_ascii=False)[:100]})")
            logger.info(f"[{session_id}] 工具调用: {tool_name}({tool_params})")

            if self.reflection:
                loop_check = await self.reflection.on_tool_call(session_id, tool_name, tool_params)
                if loop_check.get("loop_detected"):
                    warn = loop_check.get('warning', '工具循环检测')
                    await _s.emit("info", "🧠 暂停重试，冷静分析中...")
                    self._history.append({"role": "tool", "tool_call_id": tc.get("id", ""),
                        "content": f"[学习提示] {warn}。\n{LOOP_HINT}"})
                    await self._learn_from_tool_failure(session_id, tool_name, tool_params, warn)
                    continue

            result = await self._tool_call_with_retry(session_id, tool_name, tool_params, _s=_s)
            val = result.get("result") if result.get("result") is not None else result.get("error")
            result_text = str(val) if val is not None else ""
            if not result_text.strip():
                result_text = "(Command executed with no output)"
            result_text = compress_tool_result(result_text)

            await _s.emit("tool_result", result_text[:200])
            logger.info(f"[{session_id}] 工具结果: success={result.get('success')}, {result_text[:80]}")

            if not result.get("success") and result_text:
                result_text += f"\n{FAIL_HINT}"
                await self._learn_from_tool_failure(session_id, tool_name, tool_params, result_text[:150])
            self._history.append({"role": "tool", "tool_call_id": tc.get("id", ""), "content": result_text})

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
        if len(self._history) > MAX_HISTORY_HARD_LIMIT:  # 安全截断：保护 tool_calls/tool 配对
            self._history = self._history[self._find_safe_cut_point(len(self._history)-50, len(self._history)-40):]
        try:
            from memory_journal import save_conversation_summary
            user_msg = next((m["content"] for m in reversed(messages) if m.get("role") == "user"), "")
            tl = [tc["function"]["name"] for tc in response.get("tool_calls", [])] if response.get("tool_calls") else []
            save_conversation_summary(session_id, user_msg, content, tl)
        except Exception: pass
        return content

    # ── 缺失工具自动补齐 ─────────────────────────────────────────

    _TOOL_INFERENCE_MAP = TOOL_INFERENCE_MAP

    async def _try_auto_provision_tool(self, session_id: str, user_input: str, _s=None) -> bool:
        """当 LLM 承认缺少工具或拒绝伪造后，推断用户需要的工具并触发自动安装/创建。

        流程:
        1. 从用户输入推断可能需要的工具名
        2. 检查该工具是否已注册
        3. 未注册 → 调用 _on_tool_not_found（搜索 Hub → 安装 → 自创 skill）
        """
        _s = _s or self.stream
        if not hasattr(self, '_on_tool_not_found'):
            return False

        # 推断用户需要的工具
        inferred_tool = None
        for pattern, tool_name in self._TOOL_INFERENCE_MAP:
            if pattern.search(user_input):
                inferred_tool = tool_name
                break

        if not inferred_tool:
            return False

        # 检查该工具是否已注册
        if self.tools:
            existing_tools = {t["function"]["name"] for t in self.tools.list_tools()}
            if inferred_tool in existing_tools:
                return False  # 工具已存在，不需要补齐

        logger.info(f"[{session_id}] 缺失工具补齐: 推断需要 {inferred_tool}，触发自动安装/创建")
        await _s.emit("info", f"🔍 检测到缺少工具 {inferred_tool}，正在搜索并安装...")

        installed = await self._on_tool_not_found(session_id, inferred_tool)
        if installed:
            logger.info(f"[{session_id}] 缺失工具补齐成功: {inferred_tool}")
            return True
        else:
            logger.warning(f"[{session_id}] 缺失工具补齐失败: {inferred_tool}")
            return False

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
        return "\n".join(s)

    async def _build_messages(self, skip_lessons: bool = False) -> list[dict]:
        """构建发送给 LLM 的消息列表。本地模型时精简 prompt。"""
        self._reload_soul_if_changed()
        local = self._is_local_model()

        messages = []
        if self._soul_prompt:
            awareness = self._build_self_awareness()
            if local:
                # 本地模型：只用 SOUL.md 前80行（核心身份），省 token 给回复
                soul_lines = self._soul_prompt.splitlines()[:LOCAL_SOUL_MAX_LINES]
                system_content = "\n".join(soul_lines) + f"\n\n## 状态\n{awareness}"
            else:
                system_content = self._soul_prompt + f"\n\n## 当前状态\n{awareness}"
            # 用户画像注入（identity/USER.md，兼容旧 user_profile.md）
            user_text = self._load_identity_file(_USER_PATH)
            if not user_text:
                user_text = self._load_identity_file(pathlib.Path(__file__).parent / "user_profile.md")
            if user_text:
                system_content += f"\n\n{user_text}"
            # 首次引导检测
            bootstrap_text = self._load_identity_file(_BOOTSTRAP_PATH)
            if bootstrap_text and "BOOTSTRAP_COMPLETE" not in bootstrap_text:
                system_content += f"\n\n## 首次启动引导\n{bootstrap_text}"
            # 可选部分 — 按优先级排列，超预算时从末尾裁剪
            optional_sections = []
            # P2a: 多角色人格注入（最高优先）
            if self._persona_manager:
                persona_prompt = self._persona_manager.get_persona_prompt()
                if persona_prompt:
                    optional_sections.append(f"\n\n## 当前角色\n{persona_prompt}")
            if self._goal_context:
                optional_sections.append(f"\n\n{self._goal_context}")
            # 经验库注入（精炼后的高质量经验）— 受A/B开关控制 + P0快速路径控制
            if self.lessons_enabled and not skip_lessons:
                lessons_text = await self._get_relevant_lessons()
                if lessons_text:
                    optional_sections.append(f"\n\n## 过往经验（参考）\n{lessons_text}")
            if not local and self._reflection_text:
                optional_sections.append(f"\n\n## 自省\n{self._reflection_text}")
            # 知识型技能注入（kind:"prompt" 技能的 SKILL.md 内容）
            try:
                from skills.token_budget import get_prompt_skills_content
                _prompt_skills = get_prompt_skills_content()
                if _prompt_skills:
                    optional_sections.append(f"\n\n## 知识技能\n{_prompt_skills}")
            except Exception:
                pass
            # Token 预算控制：system prompt 超预算时从末尾裁剪可选部分
            base_tokens = self._estimate_tokens(system_content)
            for section in optional_sections:
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

