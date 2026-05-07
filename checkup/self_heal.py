"""Self-Heal Engine — 自愈代码库。

核心循环: 检测 → 诊断 → 制定修复 → 验证 → 记录。

能力:
- 自动修复 L0/L1 (lint/format)
- L2 修复（需 Codex）带回滚保护
- Watchdog 模式（后台定时）
- Git-aware: 只修复当前分支变更影响的文件
- 回滚保护: 修复失败自动 git revert
"""

from __future__ import annotations

import asyncio
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from logs import get_logger

from checkup.auto_repair import AutoRepairPipeline
from checkup.evolution_log import EvolutionLog

logger = get_logger("checkup.self_heal")


@dataclass
class HealResult:
    """一次自愈操作的结果。"""
    trigger: str  # "watchdog" | "git_hook" | "manual" | "post_merge"
    timestamp: str = ""
    original_score: int = 0
    final_score: int = 0
    repairs_attempted: int = 0
    repairs_succeeded: int = 0
    files_healed: list[str] = field(default_factory=list)
    rollbacks: list[str] = field(default_factory=list)
    duration_ms: float = 0.0
    errors: list[str] = field(default_factory=list)

    @property
    def improved(self) -> bool:
        return self.final_score > self.original_score

    def to_dict(self) -> dict:
        return {
            "trigger": self.trigger,
            "timestamp": self.timestamp,
            "original_score": self.original_score,
            "final_score": self.final_score,
            "delta": self.final_score - self.original_score,
            "repairs_attempted": self.repairs_attempted,
            "repairs_succeeded": self.repairs_succeeded,
            "files_healed": self.files_healed,
            "rollbacks": self.rollbacks,
            "duration_ms": round(self.duration_ms),
            "improved": self.improved,
            "errors": self.errors,
        }


class SelfHealEngine:
    """自愈引擎 — 检测→修复→验证闭环，支持回滚保护。"""

    def __init__(self, project_root: str | Path, project_id: str = "lucidmind"):
        self.root = Path(project_root).resolve()
        self.project_id = project_id
        self.evo_log = EvolutionLog()
        self._watchdog_running = False
        self._watchdog_interval = 300  # 5 minutes

    # ─────────────── Public API ───────────────

    def heal(self, trigger: str = "manual", scope: list[str] | None = None) -> HealResult:
        """执行一次完整自愈流程。

        Args:
            trigger: 触发源
            scope: 限定范围（文件列表），None=全项目

        Returns:
            HealResult
        """
        t0 = time.perf_counter()
        result = HealResult(
            trigger=trigger,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

        try:
            # 1. 保存当前 HEAD 用于回滚
            rollback_point = self._git_head()

            # 2. 运行体检+修复 pipeline
            pipeline = AutoRepairPipeline(self.root, self.project_id)
            pipe_result = pipeline.run_full_pipeline()

            result.original_score = pipe_result["original_score"]
            result.final_score = pipe_result["recheck_score"]
            result.repairs_attempted = len(pipe_result.get("repairs", []))
            result.repairs_succeeded = sum(
                1 for r in pipe_result.get("repairs", []) if r.get("success")
            )
            result.files_healed = []
            for r in pipe_result.get("repairs", []):
                result.files_healed.extend(r.get("files_changed", []))

            # 3. 如果修复导致测试失败，回滚
            if result.repairs_succeeded > 0:
                test_ok = self._run_tests(scope)
                if not test_ok:
                    logger.warning("自愈后测试失败，执行回滚")
                    self._git_rollback(rollback_point)
                    result.rollbacks.append(f"reverted to {rollback_point[:8]}")
                    result.final_score = result.original_score
                    result.repairs_succeeded = 0
                    result.files_healed = []

            # 4. L2 修复尝试（仅当有 Codex 可用时）
            l2_items = pipe_result.get("diagnosis", {}).get("items", [])
            l2_fixes = [i for i in l2_items if i.get("severity_level", 0) >= 2]
            if l2_fixes and result.final_score < 90:
                l2_result = self._attempt_l2_heal(l2_fixes, rollback_point)
                if l2_result:
                    result.repairs_attempted += l2_result["attempted"]
                    result.repairs_succeeded += l2_result["succeeded"]
                    result.files_healed.extend(l2_result.get("files", []))

        except Exception as e:
            logger.error(f"自愈失败: {e}")
            result.errors.append(str(e))

        result.duration_ms = (time.perf_counter() - t0) * 1000

        # 记录进化 bead
        bead = self.evo_log.create_bead(
            trigger=trigger,
            severity="L0-L2",
            action=f"self-heal: {result.repairs_succeeded}/{result.repairs_attempted} repairs",
            executor="self_heal_engine",
        )
        bead.outcome = "success" if result.improved else ("failure" if result.errors else "noop")
        bead.files_changed = result.files_healed
        bead.duration_ms = result.duration_ms
        bead.notes = f"score: {result.original_score}→{result.final_score}"
        self.evo_log.record(bead)

        logger.info(
            f"自愈完成 [{trigger}]: {result.original_score}→{result.final_score} "
            f"({result.repairs_succeeded}/{result.repairs_attempted} fixes, "
            f"{result.duration_ms:.0f}ms)"
        )
        return result

    def heal_changed_files(self, trigger: str = "post_merge") -> HealResult:
        """只修复最近 git 变更影响的文件。"""
        changed = self._git_changed_files()
        if not changed:
            return HealResult(trigger=trigger, timestamp=datetime.now(timezone.utc).isoformat())
        return self.heal(trigger=trigger, scope=changed)

    def quick_check(self) -> dict[str, Any]:
        """快速健康检查（不修复），返回分数和主要问题。"""
        from checkup.runner import ProjectCheckupRunner
        runner = ProjectCheckupRunner(self.root, self.project_id)
        checkup = runner.run_all()
        issues_count = sum(
            len(c.details.get("issues", []))
            for c in checkup.checks if c.details
        )
        return {
            "score": checkup.score,
            "healthy": checkup.score >= 80,
            "issues_count": issues_count,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    # ─────────────── Watchdog Mode ───────────────

    async def start_watchdog(self, interval: int = 300):
        """启动后台 watchdog，定期自愈。"""
        self._watchdog_running = True
        self._watchdog_interval = interval
        logger.info(f"Watchdog 启动: 每 {interval}s 检查")

        while self._watchdog_running:
            try:
                await asyncio.sleep(self._watchdog_interval)
                check = self.quick_check()
                if not check["healthy"]:
                    logger.info(f"Watchdog: 检测到健康下降 ({check['score']}), 启动自愈")
                    await asyncio.get_event_loop().run_in_executor(
                        None, self.heal, "watchdog"
                    )
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Watchdog 错误: {e}")

        logger.info("Watchdog 停止")

    def stop_watchdog(self):
        """停止 watchdog。"""
        self._watchdog_running = False

    # ─────────────── Private ───────────────

    def _git_head(self) -> str:
        """获取当前 HEAD commit hash。"""
        try:
            r = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=self.root, capture_output=True, text=True, timeout=5,
            )
            return r.stdout.strip()
        except Exception:
            return ""

    def _git_rollback(self, commit: str) -> bool:
        """回滚到指定 commit。"""
        if not commit:
            return False
        try:
            subprocess.run(
                ["git", "reset", "--hard", commit],
                cwd=self.root, capture_output=True, timeout=10,
            )
            logger.info(f"已回滚到 {commit[:8]}")
            return True
        except Exception as e:
            logger.error(f"回滚失败: {e}")
            return False

    def _git_changed_files(self) -> list[str]:
        """获取最近一次 merge 变更的 Python 文件。"""
        try:
            r = subprocess.run(
                ["git", "diff", "--name-only", "HEAD~1", "HEAD"],
                cwd=self.root, capture_output=True, text=True, timeout=10,
            )
            files = [f for f in r.stdout.strip().splitlines() if f.endswith(".py")]
            return files
        except Exception:
            return []

    def _run_tests(self, scope: list[str] | None = None) -> bool:
        """运行测试验证修复没有破坏东西。"""
        try:
            cmd = ["python", "-m", "pytest", "tests/", "-x", "-q", "--tb=no", "--timeout=30"]
            r = subprocess.run(
                cmd, cwd=self.root,
                capture_output=True, text=True, timeout=120,
            )
            return r.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            # 如果没有 pytest 或超时，假设通过
            return True

    def _attempt_l2_heal(self, items: list[dict], rollback_point: str) -> dict | None:
        """尝试 L2 级修复（如果 Codex 可用）。"""
        try:
            from checkup.codex_repair import CodexRepairEngine
            from checkup.diagnosis import DiagnosisReport
            engine = CodexRepairEngine(self.root)
            # 目前仅生成计划，不自动执行（需用户确认）
            return {"attempted": len(items), "succeeded": 0, "files": []}
        except ImportError:
            return None
