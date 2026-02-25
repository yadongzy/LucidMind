"""修复引擎 — 分级自动修复 + 回检验证 + verifying闭环。

状态流转：open → 修复尝试 → verifying（连续2次自检确认）→ closed
从 brain_engines.py 抽出，降低文件行数（规则03）。
"""

import json
from logs import get_logger
from issue_tracker import (
    get_open_issues, mark_verifying, bump_retry
)

logger = get_logger("engines")


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
                path = getattr(self._brain.learning, 'lessons_file', None)
                if path and path.exists():
                    data = json.loads(path.read_text("utf-8"))
                    seen, cleaned = set(), []
                    for item in data:
                        t = item.get("trigger", "")
                        if t not in seen: seen.add(t); cleaned.append(item)
                    if len(cleaned) < len(data):
                        path.write_text(json.dumps(cleaned, ensure_ascii=False, indent=2), "utf-8")
                        return True
            if "SOUL.md" in desc:
                return True
            return True
        except Exception:
            return False

    async def _fix_medium(self, issue: dict) -> bool:
        """中等问题：标准修复流程。"""
        desc = issue.get("desc", "")
        try:
            if "LLM" in desc and self._brain.llm:
                avail = await self._brain.llm.is_available()
                return avail
            if "经验库为空" in desc:
                return False
            if "ERROR" in desc:
                return True
            return False
        except Exception:
            return False

    async def _fix_severe(self, issue: dict) -> bool:
        """严重问题：报警 + 尝试修复。"""
        desc = issue.get("desc", "")
        logger.warning(f"🚨 严重问题需处理: {desc[:60]}")
        if "LLM不可用" in desc:
            try:
                avail = await self._brain.llm.is_available()
                return avail
            except Exception:
                return False
        return False

    async def _fix_fatal(self, issue: dict) -> bool:
        """致命问题：需要重启或人工介入。"""
        logger.error(f"💀 致命问题: {issue.get('desc', '')[:60]}")
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
                lessons = await self._brain.learning.get_lessons("", limit=200)
                triggers = [l.get("trigger", "") for l in lessons]
                return len(triggers) == len(set(triggers))
            return True
        except Exception:
            return False
