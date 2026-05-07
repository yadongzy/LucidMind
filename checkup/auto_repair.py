"""Auto-Repair — 体检→诊断→自动修复→验证闭环。

只自动修复 L0/L1 级问题:
- L0: ruff --fix（纯格式）
- L1: ruff --fix（unused imports 等）

L2+ 问题生成修复建议但不执行，等待用户确认或 Codex patch。
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Any

from logs import get_logger

from checkup.runner import ProjectCheckupRunner
from checkup.diagnosis import diagnose_checkup, DiagnosisReport, get_auto_fixable
from checkup.evolution_log import EvolutionLog

logger = get_logger("checkup.auto_repair")


class AutoRepairPipeline:
    """诊断+修复闭环 pipeline。"""

    def __init__(self, project_root: str | Path, project_id: str = "lucidmind"):
        self.root = Path(project_root).resolve()
        self.project_id = project_id
        self.evo_log = EvolutionLog()

    def run_full_pipeline(self) -> dict[str, Any]:
        """完整流程: 体检 → 诊断 → 自动修复 L0/L1 → 重新验证。

        Returns:
            {
                "checkup": {...},
                "diagnosis": {...},
                "repairs": [...],
                "recheck_score": int,
            }
        """
        t0 = time.perf_counter()

        # Step 1: 体检
        runner = ProjectCheckupRunner(self.root, self.project_id)
        checkup = runner.run_all()
        logger.info(f"体检完成: score={checkup.score}/100")

        # Step 2: 诊断
        diagnosis = diagnose_checkup(checkup.to_dict())

        # Step 3: 自动修复 L0/L1
        auto_fixes = get_auto_fixable(diagnosis)
        repair_results = []

        if auto_fixes:
            repair_results = self._auto_fix_lint(auto_fixes)

        # Step 4: 如果有修复，重新验证
        recheck_score = checkup.score
        if repair_results:
            recheck = runner.run_all()
            recheck_score = recheck.score
            logger.info(f"修复后重检: {checkup.score} → {recheck_score}")

        duration_ms = (time.perf_counter() - t0) * 1000
        return {
            "checkup": checkup.to_dict(),
            "diagnosis": diagnosis.to_dict(),
            "repairs": repair_results,
            "original_score": checkup.score,
            "recheck_score": recheck_score,
            "improved": recheck_score > checkup.score,
            "duration_ms": round(duration_ms),
        }

    def _auto_fix_lint(self, items: list) -> list[dict]:
        """自动修复 lint 问题 (ruff --fix)。"""
        # 收集可修复的错误码
        fixable_codes = set()
        for item in items:
            if item.auto_fixable:
                fixable_codes.add(item.issue_code)

        if not fixable_codes:
            return []

        results = []
        codes_str = ",".join(sorted(fixable_codes))

        # 创建 Bead
        bead = self.evo_log.create_bead(
            trigger="checkup",
            severity="L0-L1",
            action=f"ruff --fix --select {codes_str}",
            executor="local_cli",
        )

        t0 = time.perf_counter()
        try:
            result = subprocess.run(
                ["python", "-m", "ruff", "check", ".", "--fix",
                 "--select", codes_str, "-q"],
                cwd=self.root,
                capture_output=True, text=True, timeout=30,
            )
            bead.duration_ms = (time.perf_counter() - t0) * 1000

            if result.returncode in (0, 1):
                # 检查实际修改了什么
                git_result = subprocess.run(
                    ["git", "diff", "--name-only"],
                    cwd=self.root,
                    capture_output=True, text=True, timeout=10,
                )
                changed = [f for f in git_result.stdout.strip().splitlines() if f]
                bead.files_changed = changed
                bead.outcome = "success" if changed else "success"
                bead.approved_by = "auto"
                bead.notes = f"修复了 {len(changed)} 个文件的 {codes_str} 问题"

                results.append({
                    "action": f"ruff --fix --select {codes_str}",
                    "codes": list(fixable_codes),
                    "files_changed": changed,
                    "success": True,
                })

                # 自动 commit
                if changed:
                    subprocess.run(
                        ["git", "add"] + changed,
                        cwd=self.root, capture_output=True, timeout=10,
                    )
                    subprocess.run(
                        ["git", "commit", "--no-verify", "-m",
                         f"fix(auto): ruff --fix {codes_str} ({len(changed)} files)"],
                        cwd=self.root, capture_output=True, timeout=10,
                    )
                    logger.info(f"自动修复已提交: {codes_str} ({len(changed)} files)")
            else:
                bead.outcome = "failure"
                bead.notes = result.stderr[:200]
                results.append({
                    "action": f"ruff --fix --select {codes_str}",
                    "success": False,
                    "error": result.stderr[:200],
                })

        except (FileNotFoundError, subprocess.TimeoutExpired) as e:
            bead.outcome = "failure"
            bead.notes = str(e)
            bead.duration_ms = (time.perf_counter() - t0) * 1000

        # 记录 Bead
        self.evo_log.record(bead)
        return results

    def get_pending_l2_plus(self, diagnosis: DiagnosisReport) -> list[dict]:
        """获取需要用户确认的 L2+ 问题列表。"""
        return [
            i.to_dict() for i in diagnosis.items
            if i.severity_level >= 2
        ]
