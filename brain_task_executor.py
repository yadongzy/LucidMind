"""Brain Task Executor — 任务执行相关方法。

从 brain_daemon.py 拆分，保持 Daemon 核心精简（规则03: ≤300行）。
包含: 任务执行、模型分流、工具分组、失败处理。
"""
import asyncio

from logs import get_logger
import task_dispatcher as td

logger = get_logger("daemon")


class TaskExecutorMixin:
    """任务执行能力混入 — BrainDaemon 继承此 Mixin。"""

    def _get_tool_scope(self, task: dict) -> str:
        """根据任务类型确定工具分组场景（任务逻辑.md §6.6）。"""
        if task.get("type") == "learn":
            return "learn"
        src = task.get("source", "")
        if src == "self_check":
            return "self_check"
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
        """Act阶段：执行一个任务。智能分流到本地/外部模型。"""
        tid = task["id"]
        content = task["content"]
        task_type = task.get("type", "task")
        # 智能分流：低复杂度任务用本地模型
        use_local = self._should_use_local(task)
        original_llm = self._brain.llm
        if use_local and hasattr(original_llm, '_fallbacks') and original_llm._fallbacks:
            local_adapter = original_llm._fallbacks[-1]
            self._brain.llm = local_adapter
            logger.info(f"🏠 本地模型分流: {tid} ({task.get('source','?')}/{task_type})")
        # 工具分组：按场景限制可用工具（任务逻辑.md §6.6）
        scope = self._get_tool_scope(task)
        original_tools = self._brain.tools
        if scope != "task" and original_tools and hasattr(original_tools, 'list_tools_for_scope'):
            from tool_groups import ScopedToolProxy
            self._brain.tools = ScopedToolProxy(original_tools, scope)
            logger.info(f"🔧 工具分组[{scope}]: {tid}")
        try:
            sid = f"task_{tid}"
            await asyncio.wait_for(
                self._brain.process(sid, f"[执行任务] {content}"),
                timeout=task.get("timeout_s", 120)
            )
            self._brain._sessions.pop(sid, None)
            td.complete_task(tid)
            # 不再自动记录task_success经验（产生低质量垃圾）
            # 只有用户纠正和工具失败才值得记录
        except asyncio.TimeoutError:
            self._handle_task_failure(task, "执行超时")
        except Exception as e:
            self._handle_task_failure(task, str(e)[:200])
        finally:
            # 恢复原始工具集（工具分组清理）
            if original_tools and self._brain.tools is not original_tools:
                self._brain.tools = original_tools
            # 恢复原始LLM（本地模型分流清理）
            if use_local and self._brain.llm is not original_llm:
                self._brain.llm = original_llm

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
