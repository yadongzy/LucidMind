"""LucidMind Brain — 核心大脑，唯一主入口。

Brain 只认识 Port（接口），不认识 Adapter（实现）。
所有外部交互通过 Port 完成。
"""

import asyncio
import json
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
from brain_context import BrainContextMixin
from brain_perf import compress_tool_result, dynamic_max_tool_rounds
from brain_fast_path import classify as _fast_classify
from brain_config import (
    TOOL_LOOP_TIMEOUT_SEC,
    LLM_MAX_RETRIES, LLM_BASE_DELAY_SEC,
    LOOP_HINT, FAIL_HINT,
    TOOL_INFERENCE_MAP,
)
from identity.user_identity import get_user_identity_manager
from logs import get_logger

logger = get_logger("brain")




class Brain(BrainResilienceMixin, BrainLearningMixin, BrainToolGuardMixin, BrainIntentMixin, BrainContextMixin):
    """LucidMind 的核心大脑。"""

    def __init__(
        self,
        llm: LLMPort,
        stream: StreamPort,
        tools: ToolPort | None = None,
        memory: MemoryPort | None = None,
        learning: LearningPort | None = None,
        reflection: ReflectionPort | None = None,
        profile_adapter=None,
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
        self._session_user_map: dict[str, str] = {}  # session_id → user_id
        self._identity_mgr = get_user_identity_manager()
        if profile_adapter is None:
            from adapters.memory.user_profile import UserProfileAdapter
            profile_adapter = UserProfileAdapter()
        self._profile_adapter = profile_adapter
        self._session_msg_counter: dict[str, int] = {}  # P1: 消息计数器，用于空闲同步触发
        self._SYNC_EVERY_N_MSGS = 20  # 每 N 条消息触发一次同步
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

    def set_user_for_session(self, session_id: str, user_id: str) -> None:
        """为会话绑定用户 ID，启用多用户身份隔离。"""
        self._session_user_map[session_id] = user_id
        self._identity_mgr.ensure_user_dir(user_id)

    def _current_user_id(self) -> str:
        """获取当前会话绑定的用户 ID。"""
        return self._session_user_map.get(self._current_sid, "default")

    async def _idle_sync_and_cleanup(self, session_id: str) -> None:
        """P1: 异步空闲同步 — 每 N 条消息触发一次 SyncManager + Curator。"""
        try:
            if hasattr(self.learning, "sync_if_idle"):
                msgs = self._sessions.get(session_id, self._history)
                await self.learning.sync_if_idle(session_id, msgs, llm=self.llm)
            if hasattr(self.learning, "run_curator_cleanup"):
                await self.learning.run_curator_cleanup()
        except Exception as e:
            logger.debug(f"[{session_id}] 空闲同步/清理跳过: {e}")

    async def switch_session(self, session_id: str) -> None:
        # BUG-3 fix: 切换前触发旧会话的 MemorySyncManager 提取
        old_sid = self._current_sid
        if old_sid and old_sid != session_id and self.learning:
            try:
                sync_mgr = getattr(self.learning, "_sync_manager", None)
                old_msgs = self._sessions.get(old_sid, [])
                if sync_mgr and old_msgs:
                    await sync_mgr.on_session_end(old_sid, old_msgs, llm=self.llm)
            except Exception as e:
                logger.debug(f"[{old_sid}] 会话结束同步跳过: {e}")
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

            # 自动提取用户偏好（关键词匹配，无 LLM 调用，零延迟）
            try:
                _user_id = self._current_user_id()
                _prefs = await self._profile_adapter.extract_preferences(user_input)
                for k, v in _prefs.items():
                    self._profile_adapter.update_preference(_user_id, k, v)
            except Exception:
                pass

            # Token 优化：按快速路径分类决定加载哪些工具
            if _fp.skip_tools:
                tools = None
                logger.info(f"[{session_id}] ⚡ 快速路径跳过工具定义 (category={_fp.category})")
            else:
                tools = self.tools.list_tools() if self.tools else None
                if tools:
                    # 按意图分组过滤工具（知识问答只加载5个工具，省85%）
                    try:
                        from tool_groups import filter_tools, FAST_PATH_TOOL_SCOPE
                        scope = FAST_PATH_TOOL_SCOPE.get(_fp.category, "task")
                        if scope != "task":
                            tools = filter_tools(tools, scope)
                            logger.info(f"[{session_id}] 🔧 工具分组[{scope}]: {len(tools)} 个工具")
                    except Exception:
                        pass
                    # Token 预算：工具定义过多时裁剪（技能架构改进3）
                    try:
                        from skills.token_budget import filter_tools_by_budget
                        tools = filter_tools_by_budget(tools)
                    except Exception:
                        pass
            _tool_calls_happened = False
            _tool_steps: list[str] = []  # 追踪每个工具步骤用于任务进度更新
            if self.tools:
                pre_exec_result = await self._pre_execute_intent(session_id, user_input, _s)
                if pre_exec_result:
                    _tool_calls_happened = True
                    _tool_steps.append(pre_exec_result.get("tool_name", ""))
                    messages = await self._build_messages(skip_lessons=_fp.skip_lessons)
                    response = {"content": pre_exec_result.get("result_text", ""), "tool_calls": []}
                    content = await self._stream_final_reply(session_id, messages, response, t0, _s)
                    _result["tool_calls_happened"] = True
                    _result["tool_steps"] = _tool_steps
                    _result["reply"] = content
                    return _result

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
            # B3 fix: 只在经验实际被注入且任务非平凡时标记有效（防止 effectiveness 虚高）
            if _tool_calls_happened and not _fp.skip_lessons and hasattr(self, '_mark_lessons_effective'):
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


