"""Brain Daemon — OODA闭环系统。任务队列驱动，动态间隔，防重入。"""
import asyncio
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from logs import get_logger
from brain_engines import (
    SelfCheckEngine, RepairEngine, DailyRoutineEngine, LearningEngine
)
from brain_task_executor import TaskExecutorMixin
from brain_daemon_observe import DaemonObserveMixin
from issue_tracker import report_issue, get_open_issues
import task_dispatcher as td

logger = get_logger("daemon")


class BrainDaemon(DaemonObserveMixin, TaskExecutorMixin):
    """后台思考+自主行动守护进程。"""
    # 超时配置集中管理
    OBSERVE_TIMEOUT = 30
    ENGINES_TIMEOUT = 120
    TEACHING_TIMEOUT = 60
    IDLE_MAX_WAIT = 30

    def __init__(self, brain, interval: int = 60, soul_engine=None, goal_system=None,
                 teacher_channel=None, ws_channel=None):
        self._brain = brain
        self._running = False
        self._task: asyncio.Task | None = None
        self._thought_log: list[dict] = []
        self._last_think_time: float = 0
        self._soul_engine = soul_engine
        self._goal_system = goal_system
        self._teacher = teacher_channel
        self._teach_cycle_count = 0
        self._ws_channel = ws_channel
        self._was_disconnected = False
        self._paused = False
        self._pending_plan: str | None = None
        self._user_confirmed = False
        self._wake_event = asyncio.Event()
        # 三引擎闭环
        self._check_engine = SelfCheckEngine(brain)
        self._repair_engine = RepairEngine(brain)
        self._daily_engine = DailyRoutineEngine(brain, teacher_channel)
        self._learn_engine = LearningEngine(brain, teacher_channel, soul_engine=soul_engine)
        self._loop_tick: int = 0
        self._idle_rounds: int = 0

    async def start(self):
        if self._running: return
        self._running = True
        self._brain._awake = True
        self._task = asyncio.create_task(self._think_loop())
        logger.info("🧠 Brain Daemon 已启动 — 大脑已醒来")
        asyncio.create_task(self._boot_goal_check())

    async def stop(self):
        self._running = False
        self._brain._awake = False
        if self._task:
            self._task.cancel()
            try: await self._task
            except asyncio.CancelledError: pass
        logger.info("🧠 Brain Daemon 已停止")

    async def _think_loop(self):
        """OODA主循环：Observe→Orient→Decide→Act，每轮只做1件事。"""
        await asyncio.sleep(10)
        while self._running:
            self._loop_tick += 1
            t0 = time.time()
            try:
                alive = self._check_vitals()
                if not alive:
                    await asyncio.sleep(10)
                    continue
                # === Observe（观察）===
                td.release_stuck_tasks()
                await asyncio.wait_for(self._observe(), timeout=self.OBSERVE_TIMEOUT)
                # === Orient + Decide + Act（每轮最多3个任务，防积压）===
                tasks_done = 0
                for _ in range(3):
                    task = td.dequeue()
                    if not task:
                        break
                    self._idle_rounds = 0
                    self._learn_engine.reset_idle()
                    await self._execute_task(task)
                    tasks_done += 1
                if tasks_done == 0:
                    # 无任务时执行后台引擎
                    self._idle_rounds += 1
                    await asyncio.wait_for(self._run_engines(), timeout=self.ENGINES_TIMEOUT)
                    await asyncio.wait_for(self._teaching_cycle(), timeout=self.TEACHING_TIMEOUT)
                    # 每10轮做一次主动健康检查
                    if self._loop_tick % 10 == 0:
                        await self._proactive_health_check()
                if self._user_confirmed and not self._paused:
                    await self._execute_confirmed_plan()
                    self._user_confirmed = False
            except asyncio.TimeoutError:
                elapsed = time.time() - t0
                logger.error(f"⏰ 思考循环超时({elapsed:.0f}s)，跳过本轮")
                report_issue(f"思考循环超时{elapsed:.0f}s", "medium", "watchdog")
            except Exception as e:
                logger.error(f"后台思考异常: {e}")
                report_issue(f"思考异常: {str(e)[:80]}", "medium", "watchdog")
            wait = td.compute_interval()
            if self._idle_rounds >= 3:
                wait = max(wait, self.IDLE_MAX_WAIT)
            self._wake_event.clear()
            try:
                await asyncio.wait_for(self._wake_event.wait(), timeout=wait)
                logger.info("⚡ 收到唤醒信号，立即处理")
            except asyncio.TimeoutError:
                pass

    async def _run_engines(self):
        """空闲时运行后台引擎：每日任务→自检→修复→学习。"""
        # 1. 每日任务（持久化，重启不重复）
        if not td.is_daily_check_done():
            try:
                daily_report = await self._daily_engine.run_daily_routine()
                if daily_report:
                    logger.info(f"📅 每日任务完成: {len(daily_report)}项")
                await self._check_engine.daily_check()
                if datetime.now().day == 1 and not td.is_monthly_check_done():
                    await self._check_engine.monthly_full_check()
                    td.set_monthly_check_done()
                td.set_daily_check_done()
                # 清理旧日记文件（保留30天）
                try:
                    from memory_journal import cleanup_old_journals
                    cleanup_old_journals()
                except Exception:
                    pass
            except Exception as e:
                logger.warning(f"每日引擎异常: {e}")
        # 2. 修复引擎
        try:
            if get_open_issues(): await self._repair_engine.repair_all()
        except Exception as e: logger.warning(f"修复引擎异常: {e}")
        # 3. 定时学习
        try: await self._learn_engine.maybe_learn()
        except Exception as e: logger.warning(f"学习引擎异常: {e}")
        td.cleanup_completed(max_keep=10)  # 4. 清理过期任务

    def wake(self):
        """外部信号唤醒 Daemon（老师发消息、用户输入等）。"""
        self._wake_event.set()

    async def _execute_confirmed_plan(self): td.enqueue_from_user(self._pending_plan or "执行用户确认的任务")
    def confirm_plan(self, plan: str = ""):
        if plan: self._pending_plan = plan
        self._user_confirmed = True; logger.info(f"✅ 确认执行: {self._pending_plan}")

    def get_status(self) -> dict[str, Any]:
        return {"running": self._running, "awake": self._brain._awake,
            "paused": self._paused, "pending_plan": self._pending_plan,
            "last_think": self._last_think_time, "disconnected": self._was_disconnected,
            "queue": td.get_queue_status(), "recent_thoughts": self._thought_log[-3:],
            "teaching": self._teacher.get_status() if self._teacher else {},
            "boot_diag": getattr(self, '_boot_diag', None)}
