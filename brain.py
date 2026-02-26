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
from logs import get_logger

logger = get_logger("brain")

_IDENTITY_DIR = Path(__file__).parent / "identity"
_CORE_PATH = _IDENTITY_DIR / "CORE.md"
_SOUL_PATH = _IDENTITY_DIR / "SOUL.md"
_USER_PATH = _IDENTITY_DIR / "USER.md"
_BOOTSTRAP_PATH = _IDENTITY_DIR / "BOOTSTRAP.md"

_LOOP_HINT = ("你正在重复同样的失败操作。请停下来思考："
    "1.分析失败原因 2.用web_search搜索解决方案 "
    "3.换一种完全不同的策略 4.实在不行就诚实告诉用户并建议替代方案。不要再重复同样的命令。")
_FAIL_HINT = "[提示] 操作失败。请分析错误原因，考虑：搜索解决方案(web_search)、换方法、或告知用户。"

_TOOL_USAGE_HINTS = """
工具使用原则:
1. 需要事实/数据→先用工具获取，不要凭记忆回答
2. 文件操作→用read_file/write_file，不要用run_command cat/echo
3. 搜索信息→web_search；搜索本地文件→grep/find_files
4. 需要执行代码→run_python(安全沙盒)；系统命令→run_command
5. 复杂任务→先用decompose_task拆分，再逐步执行
6. 不确定能否完成→先尝试，失败后换方法，不要直接说不会
7. 多个工具可用时，选最直接的那个（如查天气用get_weather而非web_search）
""".strip()


class Brain(BrainResilienceMixin, BrainLearningMixin):
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
        self.ralph_max_retries = 3
        self.ralph_base_delay = 2.0
        self._soul_prompt = ""
        self._soul_mtime: float = 0.0
        self._reflection_text = ""
        self._awake = False
        self._goal_context = ""
        self.lessons_enabled = True  # A/B开关：经验注入
        self._ab_stats: dict[str, list] = {"with_lessons": [], "without_lessons": []}  # A/B质量追踪
        self._persona_manager = None  # P2a: 多角色系统（延迟初始化）
        self._reload_soul_if_changed()

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

    async def process(self, session_id: str, user_input: str) -> None:
        """处理用户输入 — Brain 的唯一主入口。

        流程: 调 LLM → 提取真实思考 → 若有工具调用则执行并回传 → 最终回复
        S2: 真实思考展示
        S3: 工具调用（LLM 决定是否调工具，Brain 执行并把结果喂回）
        S6: 记忆持久化（会话历史跨连接保留）
        S7: Ralph 循环（LLM 调用失败自动重试，透明告知用户）
        S8: 经验学习（用户纠正时自动提取经验，下次回答时注入相关经验）
        """
        self._current_sid = session_id
        t0 = time.time()
        logger.info(f"[{session_id}] 收到用户输入: {user_input[:100]}")

        try:
            # P1b: 智能上下文窗口管理 — 超长对话自动摘要压缩
            await self._smart_compact_history(session_id)

            # S6: 首次消息时从记忆加载会话历史
            if not self._history and self.memory:
                stored = await self.memory.get_context(session_id)
                if stored:
                    self._history = stored
                    logger.info(f"[{session_id}] 从记忆恢复 {len(stored)} 条历史")

            # S15: 自省 — 重复检测 + 行为分析 + 反思注入
            if self.reflection:
                ref = await self.reflection.on_user_message(session_id, user_input)
                if ref.get("repeated"):
                    await self.stream.emit("info", f"🔄 检测到重复提问 (第{ref['similar_count']+1}次) — 我会尝试给出更好的回答")
                self._reflection_text = await self.reflection.get_reflection(session_id)

            self._history.append({"role": "user", "content": user_input})
            if self.memory:
                await self.memory.save_message(session_id, {"role": "user", "content": user_input})

            # 获取工具定义（如果有 ToolPort）
            tools = self.tools.list_tools() if self.tools else None

            # === 预执行：检测明确的工具意图，LLM调用前先执行 ===
            _tool_calls_happened = False
            if self.tools:
                pre_result = await self._pre_execute_intent(session_id, user_input)
                if pre_result:
                    _tool_calls_happened = True

            # === 元认知：LLM 调用前分析意图，生成真实思考计划 ===
            metacog = await self._metacognize(user_input, tools)
            if metacog:
                await self.stream.emit("thinking", metacog)

            # === LLM 调用（可能多轮：调工具 → 喂结果 → 再调 LLM）===
            max_tool_rounds = 10
            for round_i in range(max_tool_rounds + 1):
                self._compact_history_if_needed()
                messages = await self._build_messages()
                logger.debug(f"[{session_id}] LLM 调用 (round {round_i}): {len(messages)} 条消息")

                response = await self._llm_call_with_retry(session_id, messages, tools)
                elapsed = time.time() - t0

                # 提取 LLM 原生思考（如果有）
                thinking = self._extract_thinking(response)
                if thinking:
                    await self.stream.emit("thinking", thinking)

                # 检查是否有工具调用
                tool_calls = response.get("tool_calls")
                if not tool_calls or not self.tools:
                    break  # 无工具调用，进入最终回复

                # === 执行工具调用 ===
                _tool_calls_happened = True
                # 先把 LLM 的 assistant 消息（含 tool_calls）加入历史
                # DeepSeek/OpenAI 要求 tool_calls 里每个对象有 type: "function"
                formatted_tcs = []
                for tc in tool_calls:
                    formatted_tcs.append({
                        "id": tc.get("id", ""),
                        "type": "function",
                        "function": tc.get("function", {}),
                    })
                assistant_msg = {
                    "role": "assistant",
                    "content": response.get("content") or None,
                    "tool_calls": formatted_tcs,
                }
                self._history.append(assistant_msg)

                for tc in tool_calls:
                    func = tc.get("function", {})
                    tool_name = func.get("name", "")
                    try:
                        tool_params = json.loads(func.get("arguments", "{}"))
                    except json.JSONDecodeError:
                        tool_params = {}

                    await self.stream.emit("tool_call", f"{tool_name}({json.dumps(tool_params, ensure_ascii=False)[:100]})")
                    logger.info(f"[{session_id}] 工具调用: {tool_name}({tool_params})")

                    # S15: 工具循环检测 — 失败时冷静分析，搜索学习，换策略
                    if self.reflection:
                        loop_check = await self.reflection.on_tool_call(session_id, tool_name, tool_params)
                        if loop_check.get("loop_detected"):
                            warn = loop_check.get('warning', '工具循环检测')
                            await self.stream.emit("info", f"🧠 暂停重试，冷静分析中...")
                            self._history.append({"role": "tool", "tool_call_id": tc.get("id", ""),
                                "content": f"[学习提示] {warn}。\n{_LOOP_HINT}"})
                            await self._learn_from_tool_failure(session_id, tool_name, tool_params, warn)
                            continue

                    result = await self._tool_call_with_retry(session_id, tool_name, tool_params)

                    val = result.get("result")
                    if val is None:
                        val = result.get("error")
                    result_text = str(val) if val is not None else ""
                    if not result_text.strip():
                        result_text = "(Command executed with no output)"

                    await self.stream.emit("tool_result", result_text[:200])
                    logger.info(f"[{session_id}] 工具结果: success={result.get('success')}, {result_text[:80]}")

                    # 工具失败时追加学习提示 + 记录失败经验
                    if not result.get("success") and result_text:
                        result_text += f"\n{_FAIL_HINT}"
                        await self._learn_from_tool_failure(session_id, tool_name, tool_params, result_text[:150])
                    self._history.append({
                        "role": "tool",
                        "tool_call_id": tc.get("id", ""),
                        "content": result_text,
                    })

                logger.info(f"[{session_id}] 工具轮 {round_i + 1} 完成，回传 LLM")

            # === 防伪造守卫：检测 LLM 假装完成操作但未调用工具 ===
            content_text = response.get("content", "") or ""
            if not _tool_calls_happened and self.tools:
                forced = await self._force_tool_if_faked(session_id, user_input, content_text)
                if forced:
                    # 重新获取 LLM 回复（带真实工具结果）
                    self._compact_history_if_needed()
                    messages = await self._build_messages()
                    response = await self._llm_call_with_retry(session_id, messages, tools)

            # === 最终回复（流式输出）===
            content = await self._stream_final_reply(session_id, messages, response, t0)

            # S8: 检测用户纠正信号，触发学习
            await self._detect_and_learn(session_id, user_input)
            # S59: 失败自学习 — 说"不会"后自动反思+学习
            await self._learn_from_inability(session_id, user_input, content)
            # P4: 只在涉及工具调用时标记经验有效（简单问候不算真正验证）
            if _tool_calls_happened:
                await self._mark_lessons_effective(True)

        except Exception as e:
            logger.error(f"[{session_id}] 处理失败: {e}", exc_info=True)
            friendly = self._graceful_error_response(str(e))
            await self.stream.emit("error", f"Error: {e}")
            await self.stream.emit("response", friendly)
            # P4: 标记注入的经验为无效（处理失败）
            await self._mark_lessons_effective(False)
            # 记录失败经验，下次避免
            if self.learning:
                await self._learn_pattern(session_id, f"处理失败: {user_input[:50]}", str(e)[:200], source="error")

        finally:
            await self.stream.emit("complete", None)
            logger.info(f"[{session_id}] 处理完成")

    async def _stream_final_reply(self, session_id: str, messages: list, response: dict, t0: float) -> str:
        """最终回复：优先真流式（LLM stream=True），降级伪流式。"""
        raw = response.get("content", "")
        content = re.sub(r"<think>.*?</think>\s*", "", raw, flags=re.DOTALL).strip() if raw else ""
        _already_streamed = False

        # 尝试真流式：用 LLM stream=True 直接推送（仅已有内容为空时）
        if not content and not response.get("tool_calls"):
            try:
                stream_iter = await self.llm.chat(messages, tools=None, stream=True)
                if hasattr(stream_iter, '__aiter__'):
                    await self.stream.emit("response_start", None)
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
                        await self.stream.emit("response_delta", chunk)
                    await self.stream.emit("response_end", None)
                    content = "".join(chunks).strip()
                    _already_streamed = True
                    if content:
                        logger.info(f"[{session_id}] 真流式输出完成: {len(content)} 字符")
            except Exception as e:
                logger.debug(f"[{session_id}] 真流式失败({e})，降级伪流式")

        content = content or "抱歉，我没有生成有效的回复。"
        if not content.strip(): logger.warning(f"[{session_id}] LLM 返回空内容")

        # 伪流式推送（仅真流式未使用时）
        if not _already_streamed:
            chunk_size = 8
            if len(content) > chunk_size * 2:
                await self.stream.emit("response_start", None)
                for i in range(0, len(content), chunk_size):
                    await self.stream.emit("response_delta", content[i:i+chunk_size])
                    await asyncio.sleep(0.02)
                await self.stream.emit("response_end", None)
            else:
                await self.stream.emit("response", content)
        elapsed = time.time() - t0
        usage = response.get("usage", {})
        total_tokens = usage.get("total_tokens", 0)
        info = [f"耗时 {elapsed:.1f}s"]
        if usage: info.append(f"{total_tokens} tokens")
        await self.stream.emit("info", " · ".join(info))
        self._history.append({"role": "assistant", "content": content})
        if self.memory:
            await self.memory.save_message(session_id, {"role": "assistant", "content": content})
        # A/B质量追踪
        mode = "with_lessons" if self.lessons_enabled else "without_lessons"
        self._ab_stats[mode].append({
            "elapsed": round(elapsed, 2), "tokens": total_tokens,
            "response_len": len(content), "ts": time.time(),
        })
        # 最多保留100条每组
        if len(self._ab_stats[mode]) > 100:
            self._ab_stats[mode] = self._ab_stats[mode][-100:]
        logger.info(f"[{session_id}] 回复完成(流式推送): {content[:80]}...")
        # 安全截断：保护 tool_calls/tool 配对
        if len(self._history) > 60:
            cut = self._find_safe_cut_point(len(self._history) - 50, len(self._history) - 40)
            self._history = self._history[cut:]
        # 会话记忆持久化：保存对话摘要到每日日记
        try:
            from memory_journal import save_conversation_summary
            user_msg = next((m["content"] for m in reversed(messages) if m.get("role") == "user"), "")
            tools_used = [tc["function"]["name"] for tc in response.get("tool_calls", [])] if response.get("tool_calls") else []
            save_conversation_summary(session_id, user_msg, content, tools_used)
        except Exception:
            pass
        return content

    # === 预执行意图检测：在 LLM 调用前拦截明确的工具意图 ===
    _PRE_EXEC_PATTERNS = [
        # (用户输入正则, 工具名, 参数提取函数)
        {
            "re": r"(\d+)\s*秒后?(?:提醒|叫)我?(.+?)$",
            "tool": "set_reminder",
            "extract": lambda m: {"message": m.group(2).strip() or "提醒", "seconds": int(m.group(1))},
        },
        {
            "re": r"(\d+)\s*分钟?后?(?:提醒|叫)我?(.+?)$",
            "tool": "set_reminder",
            "extract": lambda m: {"message": m.group(2).strip() or "提醒", "minutes": int(m.group(1))},
        },
        {
            "re": r"(?:提醒|叫)我?(.+?)(?:在|，)?(\d{1,2}:\d{2})",
            "tool": "set_reminder",
            "extract": lambda m: {"message": m.group(1).strip() or "提醒", "time": m.group(2)},
        },
        # 每天定时任务: "每天8点给我新闻" / "每天16:33给我时事新闻"
        {
            "re": r"每天\s*(?:早上|上午|下午|晚上)?\s*(\d{1,2})\s*[点:：]\s*(\d{0,2})\s*(?:给我|发送|推送|提醒我?|告诉我)(.+?)(?:[。.!！]?)$",
            "tool": "scheduler",
            "extract": lambda m: {
                "action": "add",
                "name": m.group(3).strip()[:30],
                "schedule": f"{int(m.group(2)) if m.group(2) else 0} {int(m.group(1))} * * *",
                "command": m.group(3).strip(),
                "job_type": "cron",
            },
        },
    ]

    async def _pre_execute_intent(self, session_id: str, user_input: str) -> bool:
        """在 LLM 调用前检测明确意图并预执行工具。返回 True 表示已执行。"""
        import re as _re
        for pat in self._PRE_EXEC_PATTERNS:
            m = _re.search(pat["re"], user_input)
            if not m:
                continue
            tool_name = pat["tool"]
            params = pat["extract"](m)
            # 清理 message
            msg = params.get("message", "")
            msg = _re.sub(r"^[你我]", "", msg).strip()
            if msg:
                params["message"] = msg
            logger.info(f"[{session_id}] 预执行: 检测到 {tool_name} 意图，直接执行")
            try:
                result = await self.tools.execute(tool_name, params, session_id=session_id)
                result_text = str(result.get("result") or result.get("error") or "")
                await self.stream.emit("tool_call", f"{tool_name}({json.dumps(params, ensure_ascii=False)})")
                await self.stream.emit("tool_result", result_text[:200])
                logger.info(f"[{session_id}] 预执行: {tool_name} 成功: {result_text[:80]}")
                # 注入工具调用+结果到历史，LLM 会基于真实数据回复
                self._history.append({"role": "assistant", "content": None, "tool_calls": [{
                    "id": f"pre_{tool_name}", "type": "function",
                    "function": {"name": tool_name, "arguments": json.dumps(params, ensure_ascii=False)},
                }]})
                self._history.append({"role": "tool", "tool_call_id": f"pre_{tool_name}", "content": result_text})
                return True
            except Exception as e:
                logger.error(f"[{session_id}] 预执行: {tool_name} 失败: {e}")
                return False
        return False

    # === 防伪造守卫：检测并强制调用工具（后备方案） ===
    _FAKE_PATTERNS = [
        # (用户输入模式, LLM回复模式, 工具名, 参数提取函数)
        {
            "user_re": r"(\d+)\s*秒后[提醒叫]",
            "reply_re": r"已设置提醒|已设定提醒|提醒已设置",
            "tool": "set_reminder",
            "extract": lambda m, _: {"message": "提醒", "seconds": int(m.group(1))},
        },
        {
            "user_re": r"(\d+)\s*分钟?后[提醒叫]",
            "reply_re": r"已设置提醒|已设定提醒|提醒已设置",
            "tool": "set_reminder",
            "extract": lambda m, _: {"message": "提醒", "minutes": int(m.group(1))},
        },
    ]

    async def _force_tool_if_faked(self, session_id: str, user_input: str, reply_text: str) -> bool:
        """检测 LLM 伪造工具结果并强制执行真实工具调用。返回 True 表示已强制执行。"""
        import re as _re
        for pat in self._FAKE_PATTERNS:
            user_match = _re.search(pat["user_re"], user_input)
            if not user_match:
                continue
            if not _re.search(pat["reply_re"], reply_text):
                continue
            # 命中：用户要求操作 + LLM 假装已完成
            tool_name = pat["tool"]
            # 从用户输入提取更完整的提醒内容
            msg_match = _re.search(r"(?:提醒|叫)我?(.+?)$", user_input)
            params = pat["extract"](user_match, user_input)
            if msg_match:
                extracted = msg_match.group(1).strip()
                # 去掉可能残留的"你"前缀
                extracted = _re.sub(r"^你", "", extracted).strip()
                if extracted:
                    params["message"] = extracted
            logger.warning(f"[{session_id}] 防伪造守卫: LLM 假装已调用 {tool_name}，强制执行")
            await self.stream.emit("info", f"🛡️ 检测到未执行的操作，正在补救...")
            try:
                result = await self.tools.execute(tool_name, params, session_id=session_id)
                result_text = str(result.get("result") or result.get("error") or "")
                await self.stream.emit("tool_call", f"{tool_name}({json.dumps(params, ensure_ascii=False)})")
                await self.stream.emit("tool_result", result_text[:200])
                logger.info(f"[{session_id}] 防伪造守卫: {tool_name} 执行成功: {result_text[:80]}")
                # 将真实结果加入历史，让 LLM 下轮基于真实数据回复
                self._history.append({"role": "assistant", "content": None, "tool_calls": [{
                    "id": f"forced_{tool_name}", "type": "function",
                    "function": {"name": tool_name, "arguments": json.dumps(params, ensure_ascii=False)},
                }]})
                self._history.append({"role": "tool", "tool_call_id": f"forced_{tool_name}", "content": result_text})
                return True
            except Exception as e:
                logger.error(f"[{session_id}] 防伪造守卫: {tool_name} 执行失败: {e}")
                return False
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
        """检查身份文件是否被修改，变化时重新加载。加载 CORE + SOUL。"""
        parts = []
        for p in [_CORE_PATH, _SOUL_PATH]:
            if not p.exists():
                continue
            try:
                key = str(p)
                cached = self._identity_cache.get(key)
                mtime = p.stat().st_mtime
                if cached and cached["mtime"] == mtime:
                    parts.append(cached["content"])
                else:
                    content = p.read_text(encoding="utf-8")
                    self._identity_cache[key] = {"mtime": mtime, "content": content}
                    parts.append(content)
                    logger.info(f"{p.name} 已重载 (mtime={mtime:.0f})")
            except OSError as e:
                logger.warning(f"{p.name} 读取失败: {e}")
        if parts:
            self._soul_prompt = "\n\n".join(parts)
            self._soul_mtime = 1  # mark as loaded

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
                    s.append(_TOOL_USAGE_HINTS)
            except Exception:
                s.append("可用工具: 获取失败")
        s.extend([f"模型: {getattr(self.llm, 'model', '?')}",
            f"时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"])
        if not local:
            platform_note = ""
            if platform.system() == "Windows":
                platform_note = " (注意: 不要用Linux/macOS命令如grep/head/tail/env/lsof/nc/ss; 不要用gui_window工具)"
            s.extend([f"记忆: {'ON' if self.memory else 'OFF'}", f"学习: {'ON' if self.learning else 'OFF'}",
                f"环境: {platform.system()} {platform.release()}{platform_note}", f"目录: {os.getcwd()}",
                f"历史: {len(self._history)}条", "安全: 禁止 rm -rf / 等危险命令; 禁止访问 .env/.git"])
        return "\n".join(s)

    async def _build_messages(self) -> list[dict]:
        """构建发送给 LLM 的消息列表。本地模型时精简 prompt。"""
        self._reload_soul_if_changed()
        local = self._is_local_model()

        messages = []
        if self._soul_prompt:
            awareness = self._build_self_awareness()
            if local:
                # 本地模型：只用 SOUL.md 前80行（核心身份），省 token 给回复
                soul_lines = self._soul_prompt.splitlines()[:80]
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
            # 经验库注入（精炼后的高质量经验）— 受A/B开关控制
            if self.lessons_enabled:
                lessons_text = await self._get_relevant_lessons()
                if lessons_text:
                    optional_sections.append(f"\n\n## 过往经验（参考）\n{lessons_text}")
            if not local and self._reflection_text:
                optional_sections.append(f"\n\n## 自省\n{self._reflection_text}")
            # Token 预算控制：system prompt 超过 4K tokens 时从末尾裁剪可选部分
            _MAX_SYSTEM_TOKENS = 4000
            base_tokens = self._estimate_tokens(system_content)
            for section in optional_sections:
                section_tokens = self._estimate_tokens(section)
                if base_tokens + section_tokens <= _MAX_SYSTEM_TOKENS:
                    system_content += section
                    base_tokens += section_tokens
                else:
                    logger.debug(f"System prompt 预算已满({base_tokens} tokens)，跳过 {len(section)} 字符")
            messages.append({"role": "system", "content": system_content})

        # 本地模型限制历史条数（省 token）
        hist = self._history
        if local and len(hist) > 6:
            hist = [m for m in hist if m.get("role") in ("user", "assistant") and "tool_calls" not in m][-6:]
        messages.extend(hist)
        self._sanitize_messages(messages)
        return messages

