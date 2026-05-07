"""ProjectCheckupRunner — 项目体检编排器。

7 项检查:
1. 测试通过率 (pytest)
2. 代码风格 (ruff lint)
3. 类型检查 (mypy/pyright, 可选)
4. 依赖安全 (pip-audit)
5. 冻结文件完整性 (git diff on frozen)
6. 文档一致性 (README/CHANGELOG 存在性)
7. 性能基线 (启动时间/内存)
"""

from __future__ import annotations

import json
import subprocess
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from logs import get_logger

logger = get_logger("checkup.runner")


@dataclass
class CheckItem:
    """单项检查结果。"""
    name: str
    status: str = "pending"  # pending | pass | warn | fail | skip
    message: str = ""
    details: dict[str, Any] = field(default_factory=dict)
    duration_ms: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class CheckupReport:
    """体检报告。"""
    project_id: str
    timestamp: str = ""
    duration_ms: float = 0.0
    summary: dict[str, int] = field(default_factory=dict)
    checks: list[CheckItem] = field(default_factory=list)
    score: int = 0  # 0-100

    def to_dict(self) -> dict:
        return {
            "project_id": self.project_id,
            "timestamp": self.timestamp,
            "duration_ms": self.duration_ms,
            "summary": self.summary,
            "checks": [c.to_dict() for c in self.checks],
            "score": self.score,
        }

    def to_markdown(self) -> str:
        lines = [
            f"# 项目体检报告",
            f"",
            f"- **项目**: {self.project_id}",
            f"- **时间**: {self.timestamp}",
            f"- **耗时**: {self.duration_ms:.0f}ms",
            f"- **健康分数**: {self.score}/100",
            f"",
            f"## 概览",
            f"",
            f"| 状态 | 数量 |",
            f"|------|------|",
        ]
        for status, count in self.summary.items():
            icon = {"pass": "✅", "warn": "⚠️", "fail": "❌", "skip": "⏭️"}.get(status, "❓")
            lines.append(f"| {icon} {status} | {count} |")
        lines.append("")
        lines.append("## 详细结果")
        lines.append("")
        for check in self.checks:
            icon = {"pass": "✅", "warn": "⚠️", "fail": "❌", "skip": "⏭️"}.get(check.status, "❓")
            lines.append(f"### {icon} {check.name}")
            lines.append(f"")
            lines.append(f"- **状态**: {check.status}")
            lines.append(f"- **信息**: {check.message}")
            if check.details:
                lines.append(f"- **详情**: `{json.dumps(check.details, ensure_ascii=False)}`")
            lines.append(f"- **耗时**: {check.duration_ms:.0f}ms")
            lines.append("")
        return "\n".join(lines)


class ProjectCheckupRunner:
    """项目体检编排器。运行 7 项检查并生成报告。"""

    def __init__(self, project_root: str | Path, project_id: str = "default"):
        self.root = Path(project_root).resolve()
        self.project_id = project_id

    def run_all(self) -> CheckupReport:
        """执行全部体检项目。"""
        t0 = time.perf_counter()
        report = CheckupReport(
            project_id=self.project_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

        checks = [
            self._check_tests,
            self._check_lint,
            self._check_types,
            self._check_dependencies,
            self._check_frozen_files,
            self._check_docs,
            self._check_performance,
        ]

        for check_fn in checks:
            try:
                item = check_fn()
            except Exception as e:
                item = CheckItem(
                    name=check_fn.__doc__ or check_fn.__name__,
                    status="fail",
                    message=f"检查异常: {e}",
                )
            report.checks.append(item)

        report.duration_ms = (time.perf_counter() - t0) * 1000
        report.summary = self._calc_summary(report.checks)
        report.score = self._calc_score(report.checks)
        logger.info(f"体检完成: score={report.score}/100, {report.summary}")
        return report

    def _check_tests(self) -> CheckItem:
        """测试通过率"""
        t0 = time.perf_counter()
        try:
            result = subprocess.run(
                ["python", "-m", "pytest", "tests/", "-q", "--tb=no", "-x"],
                cwd=self.root,
                capture_output=True, text=True, timeout=120,
            )
            output = result.stdout + result.stderr
            passed = failed = 0
            for line in output.splitlines():
                if "passed" in line:
                    import re
                    m = re.search(r"(\d+) passed", line)
                    if m:
                        passed = int(m.group(1))
                    m2 = re.search(r"(\d+) failed", line)
                    if m2:
                        failed = int(m2.group(1))

            total = passed + failed
            if total == 0:
                status = "skip"
                msg = "未发现测试"
            elif failed == 0:
                status = "pass"
                msg = f"全部通过 ({passed}/{total})"
            elif failed <= 2:
                status = "warn"
                msg = f"{failed} 个失败 ({passed}/{total} 通过)"
            else:
                status = "fail"
                msg = f"{failed} 个失败 ({passed}/{total} 通过)"

            return CheckItem(
                name="测试通过率",
                status=status,
                message=msg,
                details={"passed": passed, "failed": failed, "total": total},
                duration_ms=(time.perf_counter() - t0) * 1000,
            )
        except subprocess.TimeoutExpired:
            return CheckItem(name="测试通过率", status="warn",
                           message="测试执行超时(120s)",
                           duration_ms=(time.perf_counter() - t0) * 1000)
        except FileNotFoundError:
            return CheckItem(name="测试通过率", status="skip",
                           message="pytest 未安装")

    def _check_lint(self) -> CheckItem:
        """代码风格"""
        t0 = time.perf_counter()
        try:
            result = subprocess.run(
                ["python", "-m", "ruff", "check", ".", "--statistics", "-q"],
                cwd=self.root,
                capture_output=True, text=True, timeout=60,
            )
            issues = len([l for l in result.stdout.splitlines() if l.strip()])
            if result.returncode == 0:
                return CheckItem(name="代码风格", status="pass",
                               message="无 lint 问题",
                               duration_ms=(time.perf_counter() - t0) * 1000)
            elif issues <= 10:
                return CheckItem(name="代码风格", status="warn",
                               message=f"{issues} 条 lint 警告",
                               details={"output": result.stdout[:500]},
                               duration_ms=(time.perf_counter() - t0) * 1000)
            else:
                return CheckItem(name="代码风格", status="fail",
                               message=f"{issues} 条 lint 问题",
                               details={"output": result.stdout[:500]},
                               duration_ms=(time.perf_counter() - t0) * 1000)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return CheckItem(name="代码风格", status="skip",
                           message="ruff 未安装或超时",
                           duration_ms=(time.perf_counter() - t0) * 1000)

    def _check_types(self) -> CheckItem:
        """类型检查"""
        t0 = time.perf_counter()
        try:
            result = subprocess.run(
                ["python", "-m", "mypy", "--ignore-missing-imports",
                 "--no-error-summary", "brain.py"],
                cwd=self.root,
                capture_output=True, text=True, timeout=60,
            )
            errors = len([l for l in result.stdout.splitlines()
                         if ": error:" in l])
            if errors == 0:
                return CheckItem(name="类型检查", status="pass",
                               message="无类型错误",
                               duration_ms=(time.perf_counter() - t0) * 1000)
            else:
                return CheckItem(name="类型检查", status="warn",
                               message=f"{errors} 条类型警告",
                               duration_ms=(time.perf_counter() - t0) * 1000)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return CheckItem(name="类型检查", status="skip",
                           message="mypy 未安装（可选）",
                           duration_ms=(time.perf_counter() - t0) * 1000)

    def _check_dependencies(self) -> CheckItem:
        """依赖安全"""
        t0 = time.perf_counter()
        req_file = self.root / "requirements.txt"
        if not req_file.exists():
            return CheckItem(name="依赖安全", status="skip",
                           message="requirements.txt 不存在",
                           duration_ms=(time.perf_counter() - t0) * 1000)
        try:
            result = subprocess.run(
                ["python", "-m", "pip_audit", "-r", "requirements.txt", "-f", "json"],
                cwd=self.root,
                capture_output=True, text=True, timeout=60,
            )
            if result.returncode == 0:
                return CheckItem(name="依赖安全", status="pass",
                               message="无已知漏洞",
                               duration_ms=(time.perf_counter() - t0) * 1000)
            try:
                vulns = json.loads(result.stdout)
                count = len(vulns) if isinstance(vulns, list) else 0
            except (json.JSONDecodeError, TypeError):
                count = 1
            return CheckItem(name="依赖安全", status="warn",
                           message=f"发现 {count} 个依赖漏洞",
                           duration_ms=(time.perf_counter() - t0) * 1000)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return CheckItem(name="依赖安全", status="skip",
                           message="pip-audit 未安装（可选）",
                           duration_ms=(time.perf_counter() - t0) * 1000)

    def _check_frozen_files(self) -> CheckItem:
        """冻结文件完整性"""
        t0 = time.perf_counter()
        frozen_patterns = [
            "governance/policy.py",
            "ports/",
            "identity/",
        ]
        modified = []
        try:
            result = subprocess.run(
                ["git", "diff", "--name-only", "HEAD"],
                cwd=self.root,
                capture_output=True, text=True, timeout=10,
            )
            changed_files = result.stdout.strip().splitlines()
            for f in changed_files:
                for pat in frozen_patterns:
                    if f.startswith(pat):
                        modified.append(f)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return CheckItem(name="冻结文件完整性", status="skip",
                           message="git 不可用",
                           duration_ms=(time.perf_counter() - t0) * 1000)

        if not modified:
            return CheckItem(name="冻结文件完整性", status="pass",
                           message="冻结文件未被修改",
                           duration_ms=(time.perf_counter() - t0) * 1000)
        else:
            return CheckItem(name="冻结文件完整性", status="warn",
                           message=f"{len(modified)} 个冻结文件被修改",
                           details={"files": modified},
                           duration_ms=(time.perf_counter() - t0) * 1000)

    def _check_docs(self) -> CheckItem:
        """文档一致性"""
        t0 = time.perf_counter()
        required = ["README.md", "CHANGELOG.md", "docs/"]
        missing = []
        for name in required:
            path = self.root / name
            if not path.exists():
                missing.append(name)

        if not missing:
            return CheckItem(name="文档一致性", status="pass",
                           message="核心文档完整",
                           duration_ms=(time.perf_counter() - t0) * 1000)
        else:
            return CheckItem(name="文档一致性", status="warn",
                           message=f"缺少: {', '.join(missing)}",
                           details={"missing": missing},
                           duration_ms=(time.perf_counter() - t0) * 1000)

    def _check_performance(self) -> CheckItem:
        """性能基线"""
        t0 = time.perf_counter()
        try:
            result = subprocess.run(
                ["python", "-c", "import time; t=time.time(); import brain; print(f'{(time.time()-t)*1000:.0f}')"],
                cwd=self.root,
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode == 0:
                ms = float(result.stdout.strip())
                if ms < 2000:
                    status = "pass"
                    msg = f"启动耗时 {ms:.0f}ms"
                elif ms < 5000:
                    status = "warn"
                    msg = f"启动较慢 {ms:.0f}ms (>2s)"
                else:
                    status = "fail"
                    msg = f"启动过慢 {ms:.0f}ms (>5s)"
                return CheckItem(name="性能基线", status=status, message=msg,
                               details={"startup_ms": ms},
                               duration_ms=(time.perf_counter() - t0) * 1000)
            else:
                return CheckItem(name="性能基线", status="warn",
                               message=f"导入失败: {result.stderr[:200]}",
                               duration_ms=(time.perf_counter() - t0) * 1000)
        except (subprocess.TimeoutExpired, Exception) as e:
            return CheckItem(name="性能基线", status="warn",
                           message=f"性能检测异常: {e}",
                           duration_ms=(time.perf_counter() - t0) * 1000)

    @staticmethod
    def _calc_summary(checks: list[CheckItem]) -> dict[str, int]:
        summary: dict[str, int] = {}
        for c in checks:
            summary[c.status] = summary.get(c.status, 0) + 1
        return summary

    @staticmethod
    def _calc_score(checks: list[CheckItem]) -> int:
        if not checks:
            return 0
        weights = {"pass": 100, "warn": 60, "skip": 50, "fail": 0, "pending": 0}
        total = sum(weights.get(c.status, 0) for c in checks)
        return round(total / len(checks))
