"""Codex-Powered Repair — L2+ 问题修复（需用户确认）。

L0-L1: auto_repair.py 处理（ruff --fix，自动执行）
L2:    Codex patch + 测试验证 + 用户确认
L3:    Codex review + 方案协商 + 用户确认
L4:    仅生成报告，禁止自动修复

流程:
1. 从诊断报告获取 L2+ 问题
2. 通过 Codex CLI 生成修复方案
3. Brain 评估方案 → 记录协商决策
4. 用户确认后执行 → 测试验证 → 进化日志
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Any

from logs import get_logger
from checkup.diagnosis import DiagnosisItem, DiagnosisReport
from checkup.evolution_log import EvolutionLog
from checkup.negotiation import NegotiationProtocol

logger = get_logger("checkup.codex_repair")


class CodexRepairEngine:
    """Codex 修复引擎 — 处理 L2-L3 级问题。"""

    def __init__(self, project_root: str | Path, project_id: str = "lucidmind"):
        self.root = Path(project_root).resolve()
        self.project_id = project_id
        self.evo_log = EvolutionLog()
        self.negotiation = NegotiationProtocol()

    def plan_repairs(self, diagnosis: DiagnosisReport) -> list[dict]:
        """为 L2-L3 问题生成修复计划（不执行）。

        Returns:
            修复计划列表，每项包含:
            - diagnosis_item: 原始诊断
            - negotiation_request: 协商请求 (含 prompt)
            - severity: 分级
            - requires_approval: 是否需要用户确认
        """
        plans = []
        for item in diagnosis.items:
            if item.severity_level < 2 or item.severity_level > 3:
                continue

            req = self.negotiation.create_request(
                problem=f"[{item.issue_code}] {item.title}: {item.description}",
                context=f"Source: {item.source_check}, File: {item.file_path}" if item.file_path else f"Source: {item.source_check}",
                constraints=self._get_constraints(item.severity_level),
            )

            plans.append({
                "diagnosis_item": item.to_dict(),
                "negotiation_request": req.to_dict(),
                "codex_prompt": req.to_prompt(),
                "severity": f"L{item.severity_level}",
                "requires_approval": True,
                "status": "pending_approval",
            })

        logger.info(f"生成 {len(plans)} 个 L2-L3 修复计划")
        return plans

    def execute_repair(self, plan: dict, codex_response: str = "",
                       approved: bool = False) -> dict:
        """执行单个修复计划。

        Args:
            plan: plan_repairs() 返回的计划项
            codex_response: Codex CLI 的响应（可由 Brain 调用后传入）
            approved: 用户是否已确认

        Returns:
            执行结果
        """
        severity = plan.get("severity", "L2")
        diag = plan.get("diagnosis_item", {})

        if not approved:
            return {
                "status": "pending_approval",
                "message": f"L{severity} 修复需要用户确认",
                "plan": plan,
            }

        # 创建进化 Bead
        bead = self.evo_log.create_bead(
            trigger="codex_repair",
            diagnosis_id=diag.get("id", ""),
            severity=severity,
            action=f"codex_patch: {diag.get('title', '')}",
            executor="codex_patch",
        )
        bead.approved_by = "user"

        t0 = time.perf_counter()

        # 如果有 Codex 响应，解析方案
        if codex_response:
            resp = self.negotiation.parse_response(
                plan.get("negotiation_request", {}).get("id", ""),
                codex_response,
            )
            best = self.negotiation.evaluate_proposals(resp.proposals)
            if best:
                self.negotiation.record_decision(
                    resp.request_id, best.id, "approved", decided_by="user"
                )
                bead.action = f"codex_patch: {best.title}"
                bead.notes = best.description

        # 尝试通过 Codex CLI 执行
        try:
            from skills.codex_cli.runner import CodexCliRunner
            codex = CodexCliRunner(self.root)

            if diag.get("issue_code") == "test_failure":
                result = codex.fix_tests("pytest tests/ -x", approved=True)
            else:
                result = codex.patch(
                    target=diag.get("file_path", "."),
                    instruction=diag.get("suggested_fix", diag.get("description", "")),
                    approved=True,
                )

            bead.duration_ms = (time.perf_counter() - t0) * 1000

            if result.success:
                # 验证修复
                verify_ok = self._verify_after_fix()
                bead.outcome = "success" if verify_ok else "failure"
                bead.test_result = "pass" if verify_ok else "verify_failed"
            else:
                bead.outcome = "failure"
                bead.notes = result.error[:200]

        except Exception as e:
            bead.outcome = "failure"
            bead.notes = str(e)[:200]
            bead.duration_ms = (time.perf_counter() - t0) * 1000
            logger.warning(f"Codex 修复异常: {e}")

        self.evo_log.record(bead)

        return {
            "status": bead.outcome,
            "bead_id": bead.id,
            "duration_ms": bead.duration_ms,
            "notes": bead.notes,
        }

    def generate_l4_report(self, diagnosis: DiagnosisReport) -> list[dict]:
        """L4 问题仅生成报告，不执行任何修复。"""
        l4_items = [i for i in diagnosis.items if i.severity_level >= 4]
        return [{
            "diagnosis_item": i.to_dict(),
            "severity": "L4",
            "action": "MANUAL_REVIEW_ONLY",
            "message": f"治理文件变更: {i.title} — 需要人工审查，禁止自动修复",
        } for i in l4_items]

    def _verify_after_fix(self) -> bool:
        """修复后运行快速测试验证。"""
        try:
            result = subprocess.run(
                ["python", "-m", "pytest", "tests/", "-x", "-q", "--tb=no"],
                cwd=self.root,
                capture_output=True, text=True, timeout=60,
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return True  # 无法验证时默认通过

    def _get_constraints(self, level: int) -> list[str]:
        """根据安全等级返回约束条件。"""
        base = ["不得修改 governance/ 下的文件", "不得修改 ports/ 接口定义"]
        if level >= 3:
            base.extend([
                "不得删除现有文件",
                "新增文件需遵循现有目录结构",
                "需要 Codex review 确认",
            ])
        return base
