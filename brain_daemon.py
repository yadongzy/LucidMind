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
from issue_tracker import report_issue, get_open_issues
import task_dispatcher as td

logger = get_logger("daemon")


class BrainDaemon(TaskExecutorMixin):
    """后台思考+自主行动守护进程。"""

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
                await asyncio.wait_for(self._observe(), timeout=30)
                # === Orient + Decide + Act（每轮最多3个任务，防积压）===
                tasks_done = 0
                for _ in range(3):
                    task = td.dequeue()
                    if not task:
                        break
                    self._idle_rounds = 0
                    await self._execute_task(task)
                    tasks_done += 1
                if tasks_done == 0:
                    # 无任务时执行后台引擎
                    self._idle_rounds += 1
                    await asyncio.wait_for(self._run_engines(), timeout=120)
                    await asyncio.wait_for(self._teaching_cycle(), timeout=60)
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
                wait = max(wait, 30)  # 封顶30s（保证教学消息快速响应）
            self._wake_event.clear()
            try:
                await asyncio.wait_for(self._wake_event.wait(), timeout=wait)
                logger.info("⚡ 收到唤醒信号，立即处理")
            except asyncio.TimeoutError:
                pass

    def _check_vitals(self) -> bool:
        """求生本能：检查生命体征。无WebSocket时仍继续工作（后台任务不需要前端）。"""
        if not self._ws_channel:
            return True
        conns = len(self._ws_channel._connections)
        if conns == 0:
            if not self._was_disconnected:
                logger.warning("💀 WebSocket 无连接，大脑切换为后台模式（仍继续工作）")
                self._was_disconnected = True
            return True  # 无连接也继续工作，只是无法输出到前端
        if self._was_disconnected:
            logger.info(f"💚 连接已恢复！({conns}个活跃连接) 大脑重新上线")
            self._was_disconnected = False
            # 连接恢复时推送状态通知，让前端知道大脑在线
            asyncio.create_task(self._notify_reconnect(conns))
        return True

    async def _notify_reconnect(self, conns: int):
        """连接恢复时向前端推送状态。"""
        try:
            await self._ws_channel.broadcast(json.dumps({
                "type": "info", "data": f"💚 大脑已重新上线 ({conns}个连接)"}))
        except Exception as e:
            logger.warning(f"重连通知失败: {e}")

    async def _boot_goal_check(self):
        """启动自检（轻量）：检查系统健康状态，结果保存到大脑状态中展示。
        
        每天仅自检一次（持久化标记），重启不重复。不创建任务、不调用LLM。
        """
        await asyncio.sleep(3)
        try:
            # 每日仅一次
            from datetime import date
            today = date.today().isoformat()
            if getattr(self, '_last_boot_check_date', '') == today:
                logger.info("⏭️ 今日已自检，跳过")
                return
            store = td.load_store()
            if store.get("daily_state", {}).get("last_boot_check") == today:
                self._last_boot_check_date = today
                logger.info("⏭️ 今日已自检（持久化标记），跳过")
                return

            diag = await self._brain._self_diagnose()
            goals_ctx = "无活跃目标"
            if self._goal_system:
                active = self._goal_system.get_active_goals()
                if active:
                    goals_ctx = "; ".join(g.get("content", "")[:60] for g in active[:3])

            self._boot_diag = {
                "time": datetime.now().isoformat(),
                "healthy": diag.get("healthy", False),
                "llm": diag.get("llm", False),
                "tools": diag.get("tools", False),
                "memory": diag.get("memory", False),
                "learning": diag.get("learning", False),
                "model": diag.get("model", "?"),
                "mem_percent": diag.get("mem_percent", 0),
                "disk_free_gb": diag.get("disk_free_gb", 0),
                "resource_alerts": diag.get("resource_alerts", []),
                "goals": goals_ctx,
            }

            # 持久化标记
            store.setdefault("daily_state", {})["last_boot_check"] = today
            td.save_store(store)
            self._last_boot_check_date = today

            status = "✅ 健康" if diag.get("healthy") else f"⚠️ {diag.get('resource_alerts', [])}"
            logger.info(f"🩺 启动自检完成: {status}, 目标: {goals_ctx}")

            # 推送结果到前端（仅通知，不创建任务）
            if self._ws_channel:
                await self._ws_channel.broadcast(json.dumps({
                    "type": "info",
                    "data": f"🩺 自检完成: {status} | 模型: {diag.get('model', '?')} | 目标: {goals_ctx[:60]}",
                }))

            # === 首次引导检测 ===
            await self._check_bootstrap()
        except Exception as e:
            logger.warning(f"启动自检失败: {e}")

    async def _check_bootstrap(self):
        """检测 BOOTSTRAP.md 是否已完成，未完成则入队引导任务。"""
        try:
            bootstrap_path = Path(__file__).parent / "identity" / "BOOTSTRAP.md"
            if not bootstrap_path.exists():
                return
            content = bootstrap_path.read_text(encoding="utf-8")
            if "BOOTSTRAP_COMPLETE" in content:
                return
            # 检查是否已入队过（避免重复）
            store = td.load_store()
            if store.get("daily_state", {}).get("bootstrap_enqueued"):
                return
            # 入队引导任务
            td.enqueue(
                content="[首次启动引导] 请阅读 identity/BOOTSTRAP.md，与用户进行首次对话，了解用户信息并建立身份。完成后在 BOOTSTRAP.md 头部添加 <!-- BOOTSTRAP_COMPLETE: 日期 --> 标记。",
                task_type="task", priority="P2", source="bootstrap",
            )
            store.setdefault("daily_state", {})["bootstrap_enqueued"] = True
            td.save_store(store)
            logger.info("🚀 首次引导任务已入队")
            if self._ws_channel:
                await self._ws_channel.broadcast(json.dumps({
                    "type": "info",
                    "data": "🚀 检测到首次启动，已安排引导对话",
                }))
        except Exception as e:
            logger.warning(f"首次引导检测失败: {e}")

    async def _observe(self):
        """Observe阶段：收集信息，入队新任务，淘汰过期任务。"""
        await self._idle_think()
        td.auto_expire()
        td.cleanup_completed(max_keep=10)  # 每轮清理，保持队列精简
        # 老师消息入队（每轮最多5条）
        await asyncio.wait_for(self._ingest_teacher_messages(), timeout=10)

    async def _ingest_teacher_messages(self):
        """从老师outbox取未读消息，智能分类后入队（每轮最多5条）。

        分类策略：
        - 纯信息通知（无action/exercise）且<150字 → 直接记为经验，跳过LLM
        - 有action/exercise或长消息 → 入队走LLM处理
        """
        if not self._teacher:
            return
        try:
            from teacher_channel import _load_json, _OUTBOX
            outbox = _load_json(_OUTBOX)
            unread = [m for m in outbox if not m.get("read_by_brain")]
            for msg in unread[:5]:
                answer = msg.get("answer", "")
                action = msg.get("action", "")
                exercise = msg.get("exercise", "")
                # 智能分类：纯信息通知直接记为经验（不调LLM，省10-30秒/条）
                if answer and not action and not exercise and len(answer) < 150:
                    await self._fast_learn_from_teacher(answer)
                    msg["read_by_brain"] = True
                    msg["status"] = "learned"
                    continue
                # 有行动/练习指令 → 合并入队走LLM
                parts = []
                if answer:
                    parts.append(answer)
                if action:
                    parts.append(f"[行动] {action}")
                if exercise:
                    parts.append(f"[练习] {exercise}")
                content = "\n".join(parts) if parts else ""
                if content:
                    td.enqueue_from_teacher(content[:500])
                msg["read_by_brain"] = True
                msg["status"] = "queued"
            if unread:
                from teacher_channel import _save_json
                _save_json(_OUTBOX, outbox)
        except Exception as e:
            logger.debug(f"老师消息入队异常: {e}")

    async def _fast_learn_from_teacher(self, content: str):
        """老师简短通知：仅记录日志，不再自动写入经验库（避免垃圾）。"""
        logger.info(f"📨 老师通知: {content[:60]}")

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

    async def _idle_think(self):
        t0 = time.time()
        thoughts = [f"📊 会话{len(self._brain._sessions)}"]
        try:
            diag = await self._brain._self_diagnose()
            thoughts.insert(0, "✅ 健康" if diag.get("healthy") else f"⚠️ {diag.get('resource_alerts', [])}")
        except Exception: thoughts.insert(0, "⚠️ 自检失败")
        if self._brain.learning:
            try: thoughts.append(f"📚 经验{len(await self._brain.learning.get_lessons('', limit=100))}条")
            except Exception: pass
        oc = len(get_open_issues())
        if oc > 0: thoughts.append(f"🔴 问题{oc}个")
        qs = td.get_queue_status()
        if qs["total"] > 0: thoughts.append(f"📋 队列{qs['total']}条")
        ms = int((time.time() - t0) * 1000)
        self._thought_log.append({"time": datetime.now().strftime("%H:%M:%S"), "thoughts": thoughts, "ms": ms})
        if len(self._thought_log) > 100: self._thought_log = self._thought_log[-50:]
        self._last_think_time = time.time(); logger.info(f"💭 [{self._loop_tick}]: {'; '.join(thoughts)} ({ms}ms)")

    async def _teaching_cycle(self):
        """教学循环（精简版）：仅保留老师消息通道检查。"""
        if not self._teacher: return
        self._teach_cycle_count += 1
        try:
            await self._teacher.auto_self_check()
        except Exception as e: logger.warning(f"教学循环异常: {e}")

    async def _proactive_health_check(self):
        """主动健康监控：定期检查系统状态，发现异常主动提醒用户。"""
        try:
            import shutil, os
            alerts = []
            # 1. 磁盘空间检查
            usage = shutil.disk_usage("/")
            free_pct = usage.free / usage.total * 100
            if free_pct < 10:
                alerts.append(f"⚠️ 磁盘空间不足: 仅剩 {free_pct:.1f}%")
            # 2. 日志文件大小检查
            log_dir = Path(__file__).parent / "logs"
            if log_dir.exists():
                for lf in log_dir.glob("*.log"):
                    size_mb = lf.stat().st_size / 1024 / 1024
                    if size_mb > 50:
                        alerts.append(f"📄 日志过大: {lf.name} = {size_mb:.0f}MB")
            # 3. 数据目录大小检查
            data_dir = Path(__file__).parent / "data"
            if data_dir.exists():
                total_data = sum(f.stat().st_size for f in data_dir.rglob("*") if f.is_file())
                data_mb = total_data / 1024 / 1024
                if data_mb > 100:
                    alerts.append(f"💾 数据目录过大: {data_mb:.0f}MB")
            # 4. 推送告警
            if alerts and self._ws_channel:
                msg = "🏥 主动健康检查:\n" + "\n".join(alerts)
                await self._ws_channel.broadcast(json.dumps({"type": "info", "data": msg}))
                logger.info(f"🏥 主动告警: {'; '.join(alerts)}")
        except Exception as e:
            logger.debug(f"主动健康检查异常: {e}")

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
