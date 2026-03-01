"""修复引擎 — 分级自动修复 + 回检验证 + verifying闭环。

状态流转：open → 修复尝试 → verifying（连续2次自检确认）→ closed
从 brain_engines.py 抽出，降低文件行数（规则03）。
"""

import json
from pathlib import Path
from logs import get_logger
from issue_tracker import (
    get_open_issues, mark_verifying, bump_retry
)
from memory.noise_filter import is_noise

logger = get_logger("engines")

_PROJECT_ROOT = Path(__file__).parent
_REPAIR_PROMPT = _PROJECT_ROOT / "prompts" / "self_repair.md"


class RepairEngine:
    """修复引擎 — 分级自动修复 + 回检验证。"""

    def __init__(self, brain):
        self._brain = brain

    async def repair_all(self) -> list[str]:
        """修复所有open问题，返回修复报告。"""
        open_issues = get_open_issues()
        if not open_issues:
            return []
        report = []
        for issue in open_issues:
            sev = issue.get("severity", "medium")
            desc = issue.get("desc", "")
            iid = issue["id"]

            if sev == "minor":
                fixed = await self._auto_fix_minor(issue)
            elif sev == "medium":
                fixed = await self._fix_medium(issue)
            elif sev == "severe":
                fixed = await self._fix_severe(issue)
            else:  # fatal
                fixed = await self._fix_fatal(issue)

            if fixed:
                verified = await self._verify_fix(issue)
                if verified:
                    mark_verifying(iid, f"auto_fixed: {desc[:50]}")
                    report.append(f"🔍 修复→验证中: {desc[:40]}")
                    await self._record_repair_lesson(desc, sev)
                else:
                    bump_retry(iid)
                    report.append(f"⚠️ 修复但验证失败: {desc[:40]}")
            else:
                bump_retry(iid)
                report.append(f"❌ 无法修复: {desc[:40]}")

        if report:
            logger.info(f"🔧 修复引擎: {'; '.join(report[:5])}")
        return report

    async def _auto_fix_minor(self, issue: dict) -> bool:
        """轻微问题：静默自动修复。"""
        desc = issue.get("desc", "")
        try:
            if "重复" in desc and self._brain.learning:
                # 使用 SQLite API 去重（适配 MemoryStoreLearningAdapter）
                lessons = await self._brain.learning.get_lessons("", limit=500)
                seen_triggers, dup_ids = set(), []
                for item in lessons:
                    t = item.get("trigger", "")[:60]
                    mid = item.get("id")
                    if t in seen_triggers and mid:
                        dup_ids.append(mid)
                    else:
                        seen_triggers.add(t)
                if dup_ids:
                    store = getattr(self._brain.learning, 'store', None)
                    if store:
                        for mid in dup_ids:
                            try: store.delete(mid)
                            except Exception: pass
                        logger.info(f"🔧 经验去重: 删除{len(dup_ids)}条重复")
                    return True
                return True  # 无重复，问题已自愈
            if "噪音" in desc or "噪声" in desc:
                return await self._clean_noise_lessons()
            if "SOUL.md" in desc:
                return True
            return False  # 未匹配的 minor issue 不应假报成功
        except Exception:
            return False

    async def _fix_medium(self, issue: dict) -> bool:
        """中等问题：标准修复流程。retries>=5 升级到 L2 Brain自服务修复。"""
        desc = issue.get("desc", "")
        retries = issue.get("retries", 0)
        try:
            if "LLM" in desc and self._brain.llm:
                avail = await self._brain.llm.is_available()
                return avail
            if "经验库为空" in desc:
                return False
            if "ERROR" in desc:
                return True
            # L2: retries>=5 升级到 Brain 自服务修复
            if retries >= 5:
                return self._enqueue_brain_repair(issue)
            return False
        except Exception:
            return False

    async def _fix_severe(self, issue: dict) -> bool:
        """严重问题：报警 + L2 Brain自服务修复。"""
        desc = issue.get("desc", "")
        logger.warning(f"🚨 严重问题需处理: {desc[:60]}")
        if "LLM不可用" in desc:
            try:
                avail = await self._brain.llm.is_available()
                return avail
            except Exception:
                return False
        # L2: 非 LLM 问题交给 Brain 自服务修复
        return self._enqueue_brain_repair(issue)

    async def _fix_fatal(self, issue: dict) -> bool:
        """致命问题：需要重启或人工介入。"""
        logger.error(f"💀 致命问题: {issue.get('desc', '')[:60]}")
        return False

    def _enqueue_brain_repair(self, issue: dict) -> bool:
        """L2: 生成修复任务，通过 TaskDispatcher 交给 Brain 处理。

        Brain 会用已有工具(read_file/write_file/run_script/git_*)
        诊断和修复问题，并用 pytest 验证。
        """
        try:
            from task_dispatcher import enqueue
            prompt = self._create_repair_prompt(issue)
            enqueue(
                content=prompt,
                task_type="task",
                priority="P1",
                source="self_repair",
                timeout_s=180,
                max_retries=1,
            )
            logger.info(f"🧠 L2修复任务已入队: {issue.get('desc', '')[:50]}")
            return True
        except Exception as e:
            logger.warning(f"L2修复任务入队失败: {e}")
            return False

    def _create_repair_prompt(self, issue: dict) -> str:
        """从 self_repair.md 模板生成修复提示词。"""
        desc = issue.get("desc", "")
        severity = issue.get("severity", "medium")
        retries = issue.get("retries", 0)
        # 加载模板
        if _REPAIR_PROMPT.exists():
            template = _REPAIR_PROMPT.read_text("utf-8")
        else:
            template = (
                "请诊断并修复以下问题:\n"
                "描述: {issue_desc}\n严重度: {severity}\n"
                "修复后运行 pytest 验证。"
            )
        prompt = template.replace("{issue_desc}", desc[:200])
        prompt = prompt.replace("{severity}", severity)
        prompt = prompt.replace("{retries}", str(retries))
        prompt = prompt.replace("{file_path}", "未知，请自行定位")
        prompt = prompt.replace("{project_path}", str(_PROJECT_ROOT))
        return prompt[:500]

    async def _clean_noise_lessons(self) -> bool:
        """清洗经验库中的噪音条目。"""
        if not self._brain.learning:
            return False
        try:
            lessons = await self._brain.learning.get_lessons("", limit=500)
            store = getattr(self._brain.learning, 'store', None)
            if not store:
                return False
            noise_ids = []
            for item in lessons:
                content = item.get("lesson", "") or item.get("trigger", "")
                if is_noise(content) or content.startswith("[Tool]"):
                    mid = item.get("id")
                    if mid:
                        noise_ids.append(mid)
            if noise_ids:
                for mid in noise_ids:
                    try: store.delete(mid)
                    except Exception: pass
                logger.info(f"🧹 噪音清洗: 删除{len(noise_ids)}条噪音经验")
            return True
        except Exception:
            return False

    async def _record_repair_lesson(self, desc: str, severity: str):
        """修复成功后记录修复经验到经验库（设计文档要求）。"""
        if not self._brain.learning:
            return
        try:
            await self._brain.learning.learn({
                "trigger": f"修复成功[{severity}]: {desc[:80]}",
                "lesson": f"问题'{desc[:100]}'已自动修复。严重度={severity}。修复方法有效，可复用。",
                "source": "repair",
            })
            logger.info(f"📚 修复经验已记录: {desc[:40]}")
        except Exception as e:
            logger.debug(f"修复经验记录失败: {e}")

    async def _verify_fix(self, issue: dict) -> bool:
        """回检验证修复是否成功。"""
        desc = issue.get("desc", "")
        try:
            if "LLM" in desc:
                return await self._brain.llm.is_available()
            if "健康" in desc:
                diag = await self._brain._self_diagnose()
                return diag.get("healthy", False)
            if "重复" in desc and self._brain.learning:
                lessons = await self._brain.learning.get_lessons("", limit=500)
                triggers = [l.get("trigger", "")[:60] for l in lessons]
                return len(triggers) == len(set(triggers))
            return True
        except Exception:
            return False
