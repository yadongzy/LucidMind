"""Brain Daemon Observe Mixin — 观察、自检、教学、健康监控方法。

从 brain_daemon.py 拆分，保持 Daemon 核心精简（规则03: ≤300行）。
包含: _boot_goal_check, _check_bootstrap, _observe, _ingest_teacher_messages,
      _idle_think, _teaching_cycle, _proactive_health_check
"""
import asyncio
import json
import time
from datetime import datetime
from pathlib import Path

from logs import get_logger
import task_dispatcher as td

logger = get_logger("daemon")


class DaemonObserveMixin:
    """观察与健康监控混入 — BrainDaemon 继承此 Mixin。"""

    def _check_vitals(self) -> bool:
        """求生本能：检查生命体征。无WebSocket时仍继续工作（后台任务不需要前端）。"""
        if not self._ws_channel:
            return True
        conns = len(self._ws_channel._connections)
        if conns == 0:
            if not self._was_disconnected:
                logger.warning("💀 WebSocket 无连接，大脑切换为后台模式（仍继续工作）")
                self._was_disconnected = True
            return True
        if self._was_disconnected:
            logger.info(f"💚 连接已恢复！({conns}个活跃连接) 大脑重新上线")
            self._was_disconnected = False
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

            store.setdefault("daily_state", {})["last_boot_check"] = today
            td.save_store(store)
            self._last_boot_check_date = today

            status = "✅ 健康" if diag.get("healthy") else f"⚠️ {diag.get('resource_alerts', [])}"
            logger.info(f"🩺 启动自检完成: {status}, 目标: {goals_ctx}")

            if self._ws_channel:
                await self._ws_channel.broadcast(json.dumps({
                    "type": "info",
                    "data": f"🩺 自检完成: {status} | 模型: {diag.get('model', '?')} | 目标: {goals_ctx[:60]}",
                }))

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
            store = td.load_store()
            if store.get("daily_state", {}).get("bootstrap_enqueued"):
                return
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
        td.cleanup_completed(max_keep=10)
        await asyncio.wait_for(self._ingest_teacher_messages(), timeout=10)

    async def _ingest_teacher_messages(self):
        """从老师outbox取未读消息，智能分类后入队（每轮最多5条）。"""
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
                if answer and not action and not exercise and len(answer) < 150:
                    await self._fast_learn_from_teacher(answer)
                    msg["read_by_brain"] = True
                    msg["status"] = "learned"
                    continue
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
        from issue_tracker import get_open_issues
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
            import shutil
            alerts = []
            usage = shutil.disk_usage("/")
            free_pct = usage.free / usage.total * 100
            if free_pct < 10:
                alerts.append(f"⚠️ 磁盘空间不足: 仅剩 {free_pct:.1f}%")
            log_dir = Path(__file__).parent / "logs"
            if log_dir.exists():
                for lf in log_dir.glob("*.log"):
                    size_mb = lf.stat().st_size / 1024 / 1024
                    if size_mb > 50:
                        alerts.append(f"📄 日志过大: {lf.name} = {size_mb:.0f}MB")
            data_dir = Path(__file__).parent / "data"
            if data_dir.exists():
                total_data = sum(f.stat().st_size for f in data_dir.rglob("*") if f.is_file())
                data_mb = total_data / 1024 / 1024
                if data_mb > 100:
                    alerts.append(f"💾 数据目录过大: {data_mb:.0f}MB")
            if alerts and self._ws_channel:
                msg = "🏥 主动健康检查:\n" + "\n".join(alerts)
                await self._ws_channel.broadcast(json.dumps({"type": "info", "data": msg}))
                logger.info(f"🏥 主动告警: {'; '.join(alerts)}")
        except Exception as e:
            logger.debug(f"主动健康检查异常: {e}")
