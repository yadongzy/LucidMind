"""Diagnosis Engine — 针对体检发现的问题进行深入分析 + 安全分级 + 修复建议。

安全分级 (L0-L4):
- L0: 纯格式/命名 → 自动修复，无需确认
- L1: 代码质量（unused imports, simple lint） → 自动修复，通知用户
- L2: 逻辑修改（重构、新功能） → 需用户确认
- L3: 架构变更（新模块、删除文件） → 需用户 + Codex review
- L4: 安全/治理文件 → 禁止自动修复
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict

from logs import get_logger

logger = get_logger("checkup.diagnosis")


# ── 安全分级映射 ─────────────────────────────────────────────

_ISSUE_SEVERITY_MAP = {
    # lint 类
    "F401": 1, "F841": 1, "E401": 0, "E402": 0,
    "E701": 0, "E702": 0, "E741": 0, "F541": 1,
    "E722": 1, "F811": 1,
    # 测试失败
    "test_failure": 2,
    # 依赖漏洞
    "dependency_vuln": 2,
    # 类型错误
    "type_error": 1,
    # 冻结文件修改
    "frozen_file_modified": 4,
    # 性能退化
    "perf_degradation": 2,
    # 文档缺失
    "doc_missing": 0,
}


@dataclass
class DiagnosisItem:
    """单个问题诊断。"""
    id: str
    source_check: str          # 来自哪项体检
    issue_code: str            # 问题代码 (如 F401, test_failure)
    severity_level: int        # L0-L4
    title: str
    description: str
    file_path: str = ""
    line_number: int = 0
    suggested_fix: str = ""
    auto_fixable: bool = False
    requires_approval: bool = True

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class DiagnosisReport:
    """诊断报告。"""
    timestamp: str = ""
    items: list[DiagnosisItem] = field(default_factory=list)
    summary: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "summary": self.summary,
            "items": [i.to_dict() for i in self.items],
        }


def classify_severity(issue_code: str) -> int:
    """根据问题代码自动分级 (L0-L4)。"""
    return _ISSUE_SEVERITY_MAP.get(issue_code, 2)


def diagnose_checkup(checkup_report: dict) -> DiagnosisReport:
    """从体检报告生成诊断报告。

    Args:
        checkup_report: CheckupReport.to_dict() 的输出

    Returns:
        诊断报告（含分级 + 修复建议）
    """
    from datetime import datetime, timezone
    report = DiagnosisReport(
        timestamp=datetime.now(timezone.utc).isoformat()
    )

    checks = checkup_report.get("checks", [])
    item_id = 0

    for check in checks:
        if check["status"] in ("pass", "pending"):
            continue

        source = check["name"]
        details = check.get("details", {})

        if source == "代码风格" and check["status"] in ("fail", "warn"):
            # 解析 lint 输出
            output = details.get("output", "")
            for line in output.split("\n"):
                line = line.strip()
                if not line:
                    continue
                parts = line.split("\t")
                if len(parts) >= 2:
                    code = parts[1].strip()
                    level = classify_severity(code)
                    item_id += 1
                    report.items.append(DiagnosisItem(
                        id=f"DIAG-{item_id:03d}",
                        source_check=source,
                        issue_code=code,
                        severity_level=level,
                        title=f"Lint: {code}",
                        description=parts[2].strip() if len(parts) > 2 else code,
                        auto_fixable=level <= 1 and "[*]" in line,
                        requires_approval=level >= 2,
                    ))

        elif source == "测试通过率" and check["status"] in ("fail", "warn"):
            failed = details.get("failed", 0)
            if failed > 0:
                item_id += 1
                report.items.append(DiagnosisItem(
                    id=f"DIAG-{item_id:03d}",
                    source_check=source,
                    issue_code="test_failure",
                    severity_level=2,
                    title=f"测试失败: {failed} 个",
                    description=f"{failed} 个测试用例未通过",
                    suggested_fix="运行 pytest -v 查看详情，使用 codex_fix_tests 修复",
                    auto_fixable=False,
                    requires_approval=True,
                ))

        elif source == "类型检查" and check["status"] == "warn":
            item_id += 1
            report.items.append(DiagnosisItem(
                id=f"DIAG-{item_id:03d}",
                source_check=source,
                issue_code="type_error",
                severity_level=1,
                title="类型警告",
                description=check.get("message", ""),
                auto_fixable=False,
                requires_approval=False,
            ))

        elif source == "依赖安全" and check["status"] == "warn":
            item_id += 1
            report.items.append(DiagnosisItem(
                id=f"DIAG-{item_id:03d}",
                source_check=source,
                issue_code="dependency_vuln",
                severity_level=2,
                title="依赖漏洞",
                description=check.get("message", ""),
                suggested_fix="运行 pip-audit --fix 或手动升级",
                auto_fixable=False,
                requires_approval=True,
            ))

        elif source == "冻结文件完整性" and check["status"] == "warn":
            files = details.get("files", [])
            for f in files:
                item_id += 1
                report.items.append(DiagnosisItem(
                    id=f"DIAG-{item_id:03d}",
                    source_check=source,
                    issue_code="frozen_file_modified",
                    severity_level=4,
                    title=f"冻结文件被修改: {f}",
                    description=f"治理文件 {f} 被修改，需要人工审查",
                    file_path=f,
                    auto_fixable=False,
                    requires_approval=True,
                ))

        elif source == "性能基线" and check["status"] in ("fail", "warn"):
            item_id += 1
            report.items.append(DiagnosisItem(
                id=f"DIAG-{item_id:03d}",
                source_check=source,
                issue_code="perf_degradation",
                severity_level=2,
                title="性能退化",
                description=check.get("message", ""),
                suggested_fix="检查新增模块的导入链，优化延迟加载",
                auto_fixable=False,
                requires_approval=True,
            ))

    # 统计
    level_counts: dict[str, int] = {}
    for item in report.items:
        key = f"L{item.severity_level}"
        level_counts[key] = level_counts.get(key, 0) + 1
    report.summary = {
        "total": len(report.items),
        "auto_fixable": sum(1 for i in report.items if i.auto_fixable),
        **level_counts,
    }

    logger.info(f"诊断完成: {report.summary}")
    return report


def get_auto_fixable(diagnosis: DiagnosisReport) -> list[DiagnosisItem]:
    """获取可自动修复的问题列表（L0-L1, auto_fixable=True）。"""
    return [i for i in diagnosis.items if i.auto_fixable and i.severity_level <= 1]
