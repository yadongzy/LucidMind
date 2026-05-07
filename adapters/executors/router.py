"""ExecutorRouter — 按任务类型分发到合适的执行器。

路由策略:
  coding task → Codex CLI
  local automation → LocalToolExecutor
  browser task → BrowserExecutor (future)
  fallback → Brain 内部执行
"""

from __future__ import annotations

from ports.executor_port import ExecutorPort, ExecutorContext, ExecutorResult
from logs import get_logger

logger = get_logger("executor.router")


class ExecutorRouter:
    """注册多个执行器，按优先级匹配分发任务。"""

    def __init__(self):
        self._executors: list[ExecutorPort] = []

    def register(self, executor: ExecutorPort) -> None:
        self._executors.append(executor)
        logger.info(f"Registered executor: {executor.name}")

    def find_executor(self, task: dict) -> ExecutorPort | None:
        """找到第一个能处理该任务的执行器。"""
        for ex in self._executors:
            if ex.can_handle(task):
                return ex
        return None

    async def route_and_run(self, task: dict, context: ExecutorContext) -> ExecutorResult | None:
        """路由并执行任务。返回 None 表示无执行器匹配（应回退到 Brain 内部执行）。"""
        executor = self.find_executor(task)
        if not executor:
            logger.debug(f"No executor matched for task: {task.get('content', '')[:60]}")
            return None
        logger.info(f"Routing task to executor '{executor.name}': {task.get('content', '')[:60]}")
        result = await executor.run(task, context)
        return result

    def list_executors(self) -> list[dict]:
        return [{"name": ex.name} for ex in self._executors]


def create_default_router() -> ExecutorRouter:
    """创建预注册了 Codex + Local 的默认路由器。"""
    from adapters.executors.codex_executor import CodexExecutor
    from adapters.executors.local_executor import LocalToolExecutor

    router = ExecutorRouter()
    router.register(CodexExecutor())
    router.register(LocalToolExecutor())
    return router
