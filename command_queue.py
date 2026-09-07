"""Command Queue — OpenClaw 风格的 Lane-based 异步任务队列。

对标 OpenClaw command-queue.ts，实现：
- 多车道并发（chat / daemon / cron / subagent）互不阻塞
- Generation 计数器防幽灵任务（重启后旧任务自动忽略）
- Pump 自驱动排水（任务完成后立即驱动下一个）
- 并发上限控制（每个 Lane 独立 maxConcurrent）
- 优雅关闭（draining 模式拒绝新任务，等待活跃任务完成）
"""
import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Awaitable, Optional

from logs import get_logger

logger = get_logger("command_queue")


class CommandLane(Enum):
    """命令车道类型 — 对标 OpenClaw lanes.ts"""
    CHAT = "chat"          # 用户对话（实时，高优先级）
    DAEMON = "daemon"      # Daemon 后台任务
    CRON = "cron"          # 定时任务
    SUBAGENT = "subagent"  # 子代理任务


class LaneClearedError(Exception):
    """车道被清空时，排队中的任务收到此异常。"""
    pass


class GatewayDrainingError(Exception):
    """系统正在关闭，拒绝新任务。"""
    pass


@dataclass
class QueueEntry:
    """队列条目 — 对标 OpenClaw QueueEntry"""
    task: Callable[[], Awaitable[Any]]
    future: asyncio.Future
    enqueued_at: float = field(default_factory=time.time)
    warn_after_s: float = 30.0
    on_wait: Optional[Callable[[float, int], None]] = None
    task_id: str = ""


@dataclass
class LaneState:
    """车道状态 — 对标 OpenClaw LaneState"""
    lane: CommandLane
    queue: list[QueueEntry] = field(default_factory=list)
    active_count: int = 0
    max_concurrent: int = 1
    draining: bool = False
    generation: int = 0


class CommandQueue:
    """统一命令队列 — 所有操作通过此队列调度。

    对标 OpenClaw 的 enqueueCommandInLane / drainLane / resetAllLanes。
    """

    def __init__(self):
        self._lanes: dict[CommandLane, LaneState] = {}
        self._gateway_draining = False
        self._lock = asyncio.Lock()
        # 初始化所有车道（并发上限配置）
        _MAX_CONCURRENT = {
            CommandLane.CHAT: 3,       # 多用户对话并发
            CommandLane.DAEMON: 2,     # Daemon 可并行执行2个任务
            CommandLane.CRON: 1,       # 定时任务串行
            CommandLane.SUBAGENT: 2,   # 子代理并发
        }
        for lane in CommandLane:
            self._lanes[lane] = LaneState(
                lane=lane, max_concurrent=_MAX_CONCURRENT.get(lane, 1)
            )
        self._notify_hooks: list[Callable] = []

    def register_notify_hook(self, hook: Callable):
        """注册队列事件通知钩子。"""
        self._notify_hooks.append(hook)

    def _notify(self, event: str, data: dict):
        for hook in self._notify_hooks:
            try:
                hook(event, data)
            except Exception as e:
                logger.debug(f"通知钩子异常: {e}")

    async def enqueue(
        self,
        lane: CommandLane,
        task: Callable[[], Awaitable[Any]],
        task_id: str = "",
        warn_after_s: float = 30.0,
        on_wait: Optional[Callable[[float, int], None]] = None,
    ) -> Any:
        """将任务入队到指定车道，返回任务结果。

        对标 OpenClaw enqueueCommandInLane()。
        调用者 await 此方法即可等待任务完成。
        """
        async with self._lock:
            if self._gateway_draining:
                raise GatewayDrainingError("系统正在关闭，拒绝新任务")

            state = self._lanes[lane]
            if state.draining:
                raise LaneClearedError(f"车道 {lane.value} 正在排水")

            loop = asyncio.get_event_loop()
            future: asyncio.Future = loop.create_future()
            entry = QueueEntry(
                task=task,
                future=future,
                warn_after_s=warn_after_s,
                on_wait=on_wait,
                task_id=task_id,
            )
            state.queue.append(entry)
            gen = state.generation

            logger.debug(
                f"📥 入队 lane={lane.value} task_id={task_id} "
                f"queued={len(state.queue)} active={state.active_count}"
            )
            self._notify("enqueued", {
                "lane": lane.value, "task_id": task_id,
                "queued": len(state.queue), "active": state.active_count,
            })

        # 启动 pump（不在锁内，避免死锁）
        asyncio.ensure_future(self._pump(lane, gen))

        # 等待任务完成
        return await future

    async def _pump(self, lane: CommandLane, generation: int):
        """排水泵 — 从队列中取任务执行，完成后递归驱动下一个。

        对标 OpenClaw drainLane() 内的 pump()。
        """
        async with self._lock:
            state = self._lanes[lane]
            # Generation 防幽灵：如果 generation 已变，放弃
            if state.generation != generation:
                return
            # 并发上限检查
            if state.active_count >= state.max_concurrent:
                return
            # 队列为空
            if not state.queue:
                return

            entry = state.queue.pop(0)
            state.active_count += 1

        # 执行任务（在锁外）
        try:
            result = await entry.task()
            if not entry.future.done():
                entry.future.set_result(result)
        except asyncio.CancelledError:
            if not entry.future.done():
                entry.future.cancel()
        except Exception as e:
            if not entry.future.done():
                entry.future.set_exception(e)
        finally:
            async with self._lock:
                state = self._lanes[lane]
                state.active_count = max(0, state.active_count - 1)
                logger.debug(
                    f"✅ 完成 lane={lane.value} task_id={entry.task_id} "
                    f"active={state.active_count} queued={len(state.queue)}"
                )

            # 递归驱动下一个任务（Pump 自驱动）
            asyncio.ensure_future(self._pump(lane, generation))

    async def clear_lane(self, lane: CommandLane):
        """清空指定车道的排队任务（不影响正在执行的）。

        对标 OpenClaw clearCommandLane()。
        """
        async with self._lock:
            state = self._lanes[lane]
            cleared = len(state.queue)
            for entry in state.queue:
                if not entry.future.done():
                    entry.future.set_exception(LaneClearedError(
                        f"车道 {lane.value} 已清空"
                    ))
            state.queue.clear()
            logger.info(f"🧹 清空车道 {lane.value}: {cleared} 个排队任务")

    async def reset_all_lanes(self):
        """重置所有车道 — 递增 generation，清空排队任务。

        对标 OpenClaw resetAllLanes()。
        正在执行的任务会自然完成，但它们的 generation 已过期，
        后续的 pump 调用会被忽略。
        """
        async with self._lock:
            for lane, state in self._lanes.items():
                state.generation += 1
                cleared = len(state.queue)
                for entry in state.queue:
                    if not entry.future.done():
                        entry.future.set_exception(LaneClearedError(
                            f"车道 {lane.value} 已重置 (gen={state.generation})"
                        ))
                state.queue.clear()
                if cleared:
                    logger.info(
                        f"♻️ 重置车道 {lane.value}: gen={state.generation} "
                        f"cleared={cleared}"
                    )

    def mark_gateway_draining(self):
        """标记系统正在关闭，拒绝所有新任务。"""
        self._gateway_draining = True
        logger.info("🔻 Gateway 进入排水模式")

    async def wait_for_idle(self, timeout: float = 60.0) -> bool:
        """等待所有车道空闲（优雅关闭）。

        对标 OpenClaw dispatcher-registry 的 waitForIdle()。
        Returns: True 如果全部空闲，False 如果超时。
        """
        deadline = time.time() + timeout
        while time.time() < deadline:
            total_active = self.get_total_active()
            if total_active == 0:
                logger.info("✅ 所有车道已空闲")
                return True
            await asyncio.sleep(0.5)
        total_active = self.get_total_active()
        logger.warning(f"⏰ 等待空闲超时: 仍有 {total_active} 个活跃任务")
        return False

    def get_total_active(self) -> int:
        """获取所有车道的活跃任务总数。"""
        return sum(s.active_count for s in self._lanes.values())

    def get_total_queued(self) -> int:
        """获取所有车道的排队任务总数。"""
        return sum(len(s.queue) for s in self._lanes.values())

    def get_lane_status(self, lane: CommandLane) -> dict:
        """获取指定车道状态。"""
        state = self._lanes[lane]
        return {
            "lane": lane.value,
            "active": state.active_count,
            "queued": len(state.queue),
            "max_concurrent": state.max_concurrent,
            "generation": state.generation,
            "draining": state.draining,
        }

    def get_all_status(self) -> dict:
        """获取所有车道状态。"""
        lanes = {lane.value: self.get_lane_status(lane) for lane in CommandLane}
        return {
            "lanes": lanes,
            "total_active": self.get_total_active(),
            "total_queued": self.get_total_queued(),
            "gateway_draining": self._gateway_draining,
        }


# ═══════════════════════════════════════════════
# 全局单例
# ═══════════════════════════════════════════════

_global_queue: CommandQueue | None = None


def get_command_queue() -> CommandQueue:
    """获取全局命令队列单例。"""
    global _global_queue
    if _global_queue is None:
        _global_queue = CommandQueue()
    return _global_queue


def reset_command_queue():
    """重置全局命令队列（用于测试）。"""
    global _global_queue
    _global_queue = None
