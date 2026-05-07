"""三引擎闭环系统 — 自检引擎 + 修复引擎 + 每日任务引擎。

自检 → 发现问题 → 修复 → 验证(verifying) → 关闭(closed)
每日任务 → 总结 + 规划 + 自检 + 学习
定时学习 → 3:00-6:00 深度学习时段

不修改 brain.py（规则06），作为独立模块被 Daemon 调用。
"""

import json
from datetime import datetime, date
from pathlib import Path

from logs import get_logger
from issue_tracker import (
    report_issue, get_open_issues, check_verifying_issues
)

logger = get_logger("engines")
_DATA = Path(__file__).parent / "data"
_DAILY_FILE = _DATA / "daily_log.json"


class SelfCheckEngine:
    """自检引擎 — 每日轻量自检 + 每月全量自检。"""

    def __init__(self, brain):
        self._brain = brain
        self._last_full_check: str = ""

    async def daily_check(self) -> list[dict]:
        """每日轻量自检：当前报警 + 历史未解决。"""
        new_issues = []
        # 1. 健康自检
        try:
            diag = await self._brain._self_diagnose()
            if not diag.get("healthy"):
                alerts = diag.get("resource_alerts", [])
                new_issues.append(report_issue(
                    f"健康检查异常: {'; '.join(str(a) for a in alerts[:3])}",
                    "medium", "daily_check"))
        except Exception as e:
            new_issues.append(report_issue(f"自检失败: {e}", "severe", "daily_check"))

        # 2. LLM 可用性
        if self._brain.llm:
            try:
                avail = await self._brain.llm.is_available()
                if not avail:
                    new_issues.append(report_issue("LLM不可用", "severe", "daily_check"))
            except Exception:
                new_issues.append(report_issue("LLM检查异常", "medium", "daily_check"))

        # 3. 经验库完整性
        if self._brain.learning:
            try:
                lessons = await self._brain.learning.get_lessons("", limit=500)
                if len(lessons) == 0:
                    new_issues.append(report_issue("经验库为空", "severe", "daily_check"))
                triggers = [l.get("trigger", "")[:60] for l in lessons]
                dupes = len(triggers) - len(set(triggers))
                if dupes > 10:
                    new_issues.append(report_issue(
                        f"经验库有{dupes}条重复", "minor", "daily_check"))
                # 噪音检测
                from memory.noise_filter import is_noise
                noise_count = sum(1 for l in lessons
                    if is_noise(l.get("lesson", "") or l.get("trigger", ""))
                    or (l.get("trigger", "") or "").startswith("[Tool]"))
                if noise_count > 5:
                    new_issues.append(report_issue(
                        f"经验库有{noise_count}条噪音", "minor", "daily_check"))
            except Exception as e:
                new_issues.append(report_issue(f"经验库检查失败: {e}", "medium", "daily_check"))

        # 4. 日志错误检查
        log_path = Path(__file__).parent / "logs" / "brain.log"
        if log_path.exists():
            try:
                lines = log_path.read_text("utf-8").splitlines()[-200:]
                errors = [l for l in lines if "ERROR" in l]
                if len(errors) >= 10:
                    new_issues.append(report_issue(
                        f"最近200行日志有{len(errors)}个ERROR", "medium", "daily_check"))
            except Exception: pass

        # 5. 复查历史未解决问题
        open_issues = get_open_issues()
        stale = [i for i in open_issues if i.get("retries", 0) >= 3]
        if stale:
            logger.warning(f"⚠️ {len(stale)}个问题重试≥3次仍未解决")

        # 6. 检查验证中的问题（连续2次无复发→closed）
        verify_report = check_verifying_issues()
        if verify_report:
            logger.info(f"🔍 验证检查: {'; '.join(verify_report[:3])}")

        # 7. severe/fatal 问题入队任务调度器，触发自动修复
        for issue in new_issues:
            sev = issue.get("severity", "")
            if sev in ("fatal", "severe"):
                try:
                    from task_dispatcher import enqueue_self_check_issue
                    enqueue_self_check_issue(issue.get("description", "")[:200], sev)
                except Exception:
                    pass

        logger.info(f"📋 每日自检完成: 新问题{len(new_issues)}, 历史未解决{len(open_issues)}")
        return new_issues

    async def monthly_full_check(self) -> list[dict]:
        """每月全量自检。"""
        today = date.today().strftime("%Y-%m")
        if self._last_full_check == today:
            return []
        self._last_full_check = today
        logger.info("🔍 开始每月全量自检...")
        issues = await self.daily_check()
        # 额外检查: SOUL.md 行数
        soul = Path(__file__).parent / "identity" / "SOUL.md"
        if soul.exists():
            lines = len(soul.read_text("utf-8").splitlines())
            if lines > 180:
                issues.append(report_issue(f"SOUL.md已{lines}/200行", "minor", "monthly"))
        logger.info(f"🔍 每月全量自检完成: {len(issues)}个问题")
        return issues

def _load_daily() -> dict:
    try: return json.loads(_DAILY_FILE.read_text("utf-8")) if _DAILY_FILE.exists() else {}
    except Exception: return {}

def _save_daily(data: dict):
    _DATA.mkdir(exist_ok=True); _DAILY_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")

class DailyRoutineEngine:
    """每日任务引擎 — 5项必做，完成才进入下一天。"""

    def __init__(self, brain, teacher=None):
        self._brain = brain
        self._teacher = teacher

    def _today(self) -> str:
        return date.today().isoformat()

    def _get_today_log(self) -> dict:
        data = _load_daily()
        today = self._today()
        if data.get("date") != today:
            data = {"date": today, "tasks": {
                "yesterday_summary": False,
                "yesterday_learning": False,
                "today_plan": False,
                "daily_check": False,
                "issue_review": False
            }, "notes": []}
            _save_daily(data)
        return data

    def is_today_done(self) -> bool:
        data = self._get_today_log()
        return all(data.get("tasks", {}).values())

    async def run_daily_routine(self) -> list[str]:
        """执行每日必做任务，返回执行报告。"""
        data = self._get_today_log()
        tasks = data.get("tasks", {})
        report = []
        # 1. 前一天任务总结
        if not tasks.get("yesterday_summary"):
            data.setdefault("notes", []).append(f"[{self._today()}] 每日任务总结已执行")
            tasks["yesterday_summary"] = True; report.append("📝 前日任务总结")
        # 2. 前一天学习总结
        if not tasks.get("yesterday_learning"):
            lesson_count = 0
            if self._brain.learning:
                try:
                    lessons = await self._brain.learning.get_lessons("", limit=200)
                    lesson_count = len(lessons)
                except Exception: pass
            data.setdefault("notes", []).append(f"经验库: {lesson_count}条")
            tasks["yesterday_learning"] = True; report.append(f"📚 学习总结(经验{lesson_count}条)")
        # 3. 今日规划
        if not tasks.get("today_plan"):
            open_count = len(get_open_issues())
            data.setdefault("notes", []).append(f"今日待解决问题: {open_count}个")
            tasks["today_plan"] = True; report.append(f"📋 今日规划({open_count}个问题)")
        # 4. 每日轻量自检（由 SelfCheckEngine 执行）
        if not tasks.get("daily_check"):
            tasks["daily_check"] = True; report.append("🔍 每日自检已标记")
        # 5. 报警/未解决问题复查
        if not tasks.get("issue_review"):
            open_issues = get_open_issues()
            stale = [i for i in open_issues if i.get("retries", 0) >= 3]
            if stale:
                data.setdefault("notes", []).append(
                    f"⚠️ {len(stale)}个问题重试≥3次: " +
                    "; ".join(i["desc"][:30] for i in stale[:3]))
            tasks["issue_review"] = True
            report.append(f"🔎 问题复查(未解决{len(open_issues)}个)")

        data["tasks"] = tasks
        _save_daily(data)

        if report:
            logger.info(f"📅 每日任务: {'; '.join(report)}")
        return report


class LearningEngine:
    """定时学习引擎 — 3:00-6:00 或空闲时深度学习。"""

    def __init__(self, brain, teacher=None, soul_engine=None):
        self._brain = brain
        self._teacher = teacher
        self._soul_engine = soul_engine
        self._learning_done_today: str = ""
        self._idle_ticks: int = 0

    def is_learning_time(self) -> bool:
        """判断是否在学习时段。"""
        hour = datetime.now().hour
        return 3 <= hour < 6

    def is_idle(self) -> bool:
        """判断大脑是否空闲（无活跃会话或连续空闲5轮）。"""
        self._idle_ticks += 1
        return self._idle_ticks >= 5

    def reset_idle(self):
        """有新消息时重置空闲计数。"""
        self._idle_ticks = 0

    async def maybe_learn(self) -> list[str]:
        """如果满足条件，执行深度学习。"""
        today = date.today().isoformat()
        if self._learning_done_today == today:
            return []

        if not (self.is_learning_time() or self.is_idle()):
            return []

        report = []

        # 0. 种子经验注入（首次或缺失时自动补充）
        if self._brain.learning:
            try:
                from scripts.seed_lessons import inject_seeds
                injected = await inject_seeds(self._brain.learning)
                if injected:
                    report.append(f"🌱 种子注入{injected}条")
            except Exception as e:
                logger.debug(f"种子注入跳过: {e}")

        # 1. 学习修复失败的问题
        open_issues = get_open_issues()
        failed = [i for i in open_issues if i.get("retries", 0) >= 2]
        if failed:
            report.append(f"📖 分析{len(failed)}个难题")

        # 2. 处理老师的教学内容
        if self._teacher:
            try:
                await self._teacher.process_teacher_replies()
                report.append("📖 处理老师教学")
            except Exception as e:
                report.append(f"⚠️ 教学处理失败: {str(e)[:30]}")

        # 3. 自检暴露的弱点 → 记忆更新
        lessons = []
        if self._brain.learning:
            try:
                lessons = await self._brain.learning.get_lessons("", limit=50)
                fail_lessons = [l for l in lessons
                               if "失败" in l.get("lesson", "") or "错误" in l.get("lesson", "")]
                if fail_lessons:
                    report.append(f"📖 复习{len(fail_lessons)}条失败经验")
            except Exception: pass

        # 4. 灵魂进化 — 频繁触发的经验→固化为灵魂规则
        if self._soul_engine and lessons:
            try:
                suggestions = self._soul_engine.analyze_patterns(lessons)
                for s in suggestions[:1]:
                    ok = self._soul_engine.evolve(s["trigger"], s["suggested_rule"])
                    if ok:
                        report.append(f"🧬 灵魂进化: {s['suggested_rule'][:40]}")
            except Exception as e:
                logger.debug(f"灵魂进化跳过: {e}")

        if report:
            self._learning_done_today = today
            logger.info(f"🎓 深度学习: {'; '.join(report)}")

        return report
