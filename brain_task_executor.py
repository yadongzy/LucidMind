"""Brain Task Executor — 任务执行相关方法。

从 brain_daemon.py 拆分，保持 Daemon 核心精简（规则03: ≤300行）。
包含: 任务执行、模型分流、工具分组、失败处理。

对标 OpenClaw run.ts:
- while-true 内联重试循环（单任务内多次尝试直到成功）
- 软失败检测（empty_promise 且工具未执行 → 重试而非完成）
- 通过 command_queue 统一入队执行
"""
import asyncio
import re

from logs import get_logger
import task_dispatcher as td
from command_queue import get_command_queue, CommandLane
from task_decomposer import should_decompose, decompose_task

logger = get_logger("daemon")

# 对标 OpenClaw BASE_RUN_RETRY_ITERATIONS / MAX_RUN_RETRY_ITERATIONS
MAX_INLINE_RETRIES = 3          # 单任务内最大内联重试次数
INLINE_RETRY_DELAY_S = 2.0      # 内联重试间隔（指数退避基数）

# DSML/XML 伪工具调用剥离（MiniMax等模型会输出这种格式）
_DSML_XML_RE = re.compile(
    r'<\s*\|?\s*(?:DSML\s*\|?\s*)?(?:function_calls|invoke|parameter|/invoke|/function_calls|/parameter)\b[^>]*>',
    re.IGNORECASE,
)

def _strip_dsml_xml(text: str) -> str:
    """剥离 DSML/XML 伪工具调用标签，保留纯文本。"""
    return _DSML_XML_RE.sub("", text).strip()

# 承诺性结尾模式：回复以这些短语结尾表示任务未完成
_PROMISE_TAIL_PATTERNS = [
    "让我", "我来", "正在", "接下来", "下面我", "现在我",
    "让我用", "让我试", "我来试", "我来帮",
    "稍等", "请稍等", "马上",
    "正在尝试", "正在执行", "正在处理", "正在搜索", "正在查找",
    "I'll", "Let me", "I'm going to", "I will now",
]


class TaskExecutorMixin:
    """任务执行能力混入 — BrainDaemon 继承此 Mixin。"""

    def _get_tool_scope(self, task: dict) -> str:
        """根据任务类型确定工具分组场景（任务逻辑.md §6.6）。"""
        if task.get("type") == "learn":
            return "learn"
        src = task.get("source", "")
        if src == "self_check":
            return "self_check"
        if src == "self_repair":
            return "task"  # L2自修复需要完整工具访问
        return "task"

    def _should_use_local(self, task: dict) -> bool:
        """判断任务是否应该用本地模型（省外部API token）。

        本地模型适合：学习任务、自检、任务驱动学习、简短教学消息。
        外部API适合：用户任务、复杂教学指令（含[练习]/[行动]）。
        """
        task_type = task.get("type", "task")
        source = task.get("source", "")
        content = task.get("content", "")
        if task_type == "learn":
            return True
        if source == "self_check":
            return True
        if source == "task_driven":
            return True
        if source == "teacher" and len(content) < 200 and "[练习]" not in content and "[行动]" not in content:
            return True
        return False

    async def _execute_task(self, task: dict):
        """Act阶段：通过 command_queue 统一入队执行任务。

        混合模式 Scheduler: 复杂任务先尝试分解为子任务。
        """
        cq = get_command_queue()
        # 子任务走 SUBAGENT lane，与父任务物理隔离
        lane = CommandLane.SUBAGENT if task.get("parent_id") else CommandLane.DAEMON
        tid = task["id"]
        # === Scheduler: 复杂任务分解 ===
        if should_decompose(task):
            try:
                subtasks = await decompose_task(self._brain, task)
                if subtasks:
                    logger.info(f"🔀 任务已分解: {tid} → {len(subtasks)}个子任务")
                    return  # 子任务已入队，父任务已阻塞，等子任务完成后自动恢复
            except Exception as e:
                logger.warning(f"任务分解失败，直接执行: {tid} {e}")
        try:
            await cq.enqueue(
                lane=lane,
                task=lambda t=task: self._execute_task_inner(t),
                task_id=f"task_{tid}",
            )
        except Exception as e:
            logger.error(f"命令队列入队失败: {tid} {e}")
            self._handle_task_failure(task, f"入队失败: {str(e)[:100]}")

    async def _execute_task_inner(self, task: dict):
        """内部执行逻辑：while-true 内联重试循环。

        对标 OpenClaw run.ts while(true) 循环：
        - 每次调用 brain.process() 执行一轮
        - 软失败（空承诺且工具未执行）→ 内联重试
        - 硬失败（异常/超时）→ 外部 fail_task 重试
        - 上限保护：MAX_INLINE_RETRIES 次后放弃
        """
        tid = task["id"]
        content = task["content"]
        task_type = task.get("type", "task")
        # 创建广播 stream，让任务执行结果推送到前端对话页面
        task_stream = None
        try:
            from adapters.stream.broadcast_stream import BroadcastStreamAdapter
            ws_ch = getattr(self._brain, '_stream', None)
            # 获取 ws_channel：从 brain daemon 的 _ws_channel 属性
            ws_channel = getattr(self, '_ws_channel', None)
            if ws_channel:
                task_stream = BroadcastStreamAdapter(
                    ws_channel,
                    job_name=content[:60],
                    task_id=tid,
                )
        except Exception:
            pass
        # 智能分流：低复杂度任务用本地模型
        # 用 ContextVar 任务级覆盖，不再全局替换 brain.llm/brain.tools
        # （全局替换会让并发运行的用户对话被切到本地模型/受限工具集）
        use_local = self._should_use_local(task)
        original_llm = self._brain.llm
        llm_token = None
        if use_local and hasattr(original_llm, '_fallbacks') and original_llm._fallbacks:
            local_adapter = original_llm._fallbacks[-1]
            llm_token = self._brain.set_llm_override(local_adapter)
            logger.info(f"🏠 本地模型分流: {tid} ({task.get('source','?')}/{task_type})")
        # 工具分组：按场景限制可用工具（任务逻辑.md §6.6）
        scope = self._get_tool_scope(task)
        original_tools = self._brain.tools
        tools_token = None
        if scope != "task" and original_tools and hasattr(original_tools, 'list_tools_for_scope'):
            from tool_groups import ScopedToolProxy
            tools_token = self._brain.set_tools_override(ScopedToolProxy(original_tools, scope))
            logger.info(f"🔧 工具分组[{scope}]: {tid}")
        try:
            sid = f"task_{tid}"
            attempt = 0
            last_error = ""
            # === OpenClaw 风格 while-true 内联重试 ===
            while attempt <= MAX_INLINE_RETRIES:
                attempt += 1
                try:
                    # 推送中间状态
                    td.update_task_progress(tid, f"执行中(第{attempt}次尝试)")
                    result = await asyncio.wait_for(
                        self._brain.process(sid, f"[执行任务] {content}",
                                            stream=task_stream),
                        timeout=task.get("timeout_s", 120)
                    )
                    # === 软失败检测（对标 OpenClaw attempt 结果检查）===
                    if isinstance(result, dict):
                        tool_happened = result.get("tool_calls_happened", False)
                        empty_promise = result.get("empty_promise_detected", False)
                        reply = result.get("reply", "")
                        # 检测空回复 fallback（工具执行成功但 LLM 未生成有效回复）
                        is_empty_fallback = reply and "没有生成有效的回复" in reply
                        # 检测回复以承诺结尾（工具调用了但任务未完成）
                        is_promise_ending = False
                        if reply and not is_empty_fallback:
                            # 先剥离 DSML/XML 伪工具调用标签再检测承诺
                            clean_reply = _strip_dsml_xml(reply.strip())
                            tail = clean_reply[-200:] if len(clean_reply) > 200 else clean_reply
                            is_promise_ending = any(p in tail for p in _PROMISE_TAIL_PATTERNS)
                        if (empty_promise and not tool_happened) or is_empty_fallback or is_promise_ending:
                            if is_promise_ending:
                                last_error = f"承诺未兑现:回复以'{tail[-30:]}...'结尾"
                            elif is_empty_fallback:
                                last_error = "空回复:LLM未总结工具结果"
                            else:
                                last_error = "空承诺:工具未执行"
                            if attempt <= MAX_INLINE_RETRIES:
                                delay = INLINE_RETRY_DELAY_S * (2 ** (attempt - 1))
                                logger.warning(
                                    f"🔄 内联重试 {tid}: attempt={attempt} "
                                    f"reason={last_error} delay={delay:.1f}s"
                                )
                                await asyncio.sleep(delay)
                                continue
                            else:
                                # 所有内联重试耗尽且仍是软失败 → 不标记完成
                                break
                    # 成功完成
                    self._brain._sessions.pop(sid, None)
                    td.complete_task(tid)
                    logger.info(f"✅ 任务完成: {tid} (attempt={attempt})")
                    return
                except asyncio.TimeoutError:
                    last_error = f"执行超时(attempt={attempt})"
                    if attempt <= MAX_INLINE_RETRIES:
                        logger.warning(f"🔄 内联重试(超时) {tid}: attempt={attempt}")
                        await asyncio.sleep(INLINE_RETRY_DELAY_S)
                        continue
                    break
                except Exception as e:
                    last_error = str(e)[:200]
                    break  # 硬异常不内联重试，交给外部 fail_task
            # 所有内联重试耗尽
            self._brain._sessions.pop(sid, None)
            self._handle_task_failure(task, last_error)
        finally:
            # 恢复任务级覆盖（ContextVar reset 必须与 set 在同一上下文）
            if tools_token is not None:
                self._brain.reset_tools_override(tools_token)
            if llm_token is not None:
                self._brain.reset_llm_override(llm_token)

    def _handle_task_failure(self, task: dict, error: str):
        """任务失败处理：判断是否触发任务驱动学习。"""
        tid = task["id"]
        retries = task.get("retries", 0)
        # 学习任务失败不再生成子学习任务（防无限递归）
        if task.get("type") == "learn":
            td.fail_task(tid, error)
            return
        # 首次失败→直接重试；第2次失败→触发任务驱动学习
        if retries < 1:
            td.fail_task(tid, error)
        else:
            td.block_task(tid, error)
            td.enqueue_learning(
                f"[任务驱动学习] 任务'{task['content'][:80]}'失败: {error[:100]}。分析原因并学习解决方法。",
                priority="L0", source="task_driven", parent_id=tid
            )
            logger.info(f"📖 任务驱动学习: {tid} → 生成L0子任务")
