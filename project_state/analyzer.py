"""Reversa-like 项目理解 pipeline — 5 阶段分析器。

Pipeline:
  1. Scout      — 表面扫描: 文件清单、语言、大小、目录结构
  2. Archaeologist — 核心模块深读: import 图、类/函数提取
  3. Detective  — 业务规则和约束: 配置、环境变量、硬编码、API 路由
  4. Writer     — 规格和架构: 架构图、依赖图、模块职责
  5. Reviewer   — gap 和问题: 缺失测试、无文档模块、风险

输出: data/projects/<project>/specs/*.md + confidence-report.md
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from logs import get_logger

logger = get_logger("project.analyzer")

# 置信度标记
C_CONFIRMED = "🟢"
C_INFERRED = "🟡"
C_GAP = "🔴"

# 忽略的目录
_IGNORE_DIRS = {
    "__pycache__", ".git", "node_modules", ".venv", "venv",
    ".mypy_cache", ".pytest_cache", "dist", "build", ".tox",
    "_redundant_backup", ".windsurf",
}

_EXT_LANG = {
    ".py": "Python", ".js": "JavaScript", ".ts": "TypeScript",
    ".html": "HTML", ".css": "CSS", ".md": "Markdown",
    ".json": "JSON", ".toml": "TOML", ".yaml": "YAML", ".yml": "YAML",
    ".sh": "Shell", ".sql": "SQL",
}


@dataclass
class AnalysisResult:
    project_id: str
    project_root: str
    commit: str = ""
    timestamp: str = ""
    stages_completed: list[str] = field(default_factory=list)
    inventory: dict[str, Any] = field(default_factory=dict)
    code_analysis: dict[str, Any] = field(default_factory=dict)
    domain: dict[str, Any] = field(default_factory=dict)
    architecture: dict[str, Any] = field(default_factory=dict)
    dependencies: dict[str, Any] = field(default_factory=dict)
    questions: list[dict] = field(default_factory=list)
    confidence: list[dict] = field(default_factory=list)


class ProjectAnalyzer:
    """5 阶段项目分析器。"""

    def __init__(self, root: str | Path, project_id: str = "lucidmind"):
        self.root = Path(root).resolve()
        self.project_id = project_id
        self._specs_dir = self.root / "data" / "projects" / project_id / "specs"
        self._specs_dir.mkdir(parents=True, exist_ok=True)

    def run_full(self, incremental: bool = True) -> AnalysisResult:
        """运行完整 5 阶段分析。"""
        result = AnalysisResult(
            project_id=self.project_id,
            project_root=str(self.root),
            commit=self._git_commit(),
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

        # Check incremental
        if incremental:
            last = self._load_last_commit()
            if last and last == result.commit:
                logger.info("No new commits since last analysis, skipping.")
                return result

        self._stage_scout(result)
        self._stage_archaeologist(result)
        self._stage_detective(result)
        self._stage_writer(result)
        self._stage_reviewer(result)

        self._save_last_commit(result.commit)
        self._write_all_specs(result)
        logger.info(f"Analysis complete: {len(result.stages_completed)} stages")
        return result

    # ── Stage 1: Scout ──

    def _stage_scout(self, r: AnalysisResult) -> None:
        """表面扫描: 文件清单、语言统计、目录结构。"""
        files = []
        lang_counter: Counter = Counter()
        dir_tree: dict[str, int] = defaultdict(int)
        total_lines = 0

        for f in self._walk_files():
            rel = str(f.relative_to(self.root))
            ext = f.suffix.lower()
            lang = _EXT_LANG.get(ext, "Other")
            try:
                size = f.stat().st_size
                lines = f.read_text("utf-8", errors="ignore").count("\n") + 1
            except Exception:
                size, lines = 0, 0
            files.append({"path": rel, "lang": lang, "size": size, "lines": lines})
            lang_counter[lang] += lines
            total_lines += lines
            parts = rel.split("/")
            if len(parts) > 1:
                dir_tree[parts[0]] += 1

        r.inventory = {
            "total_files": len(files),
            "total_lines": total_lines,
            "languages": dict(lang_counter.most_common()),
            "top_dirs": dict(sorted(dir_tree.items(), key=lambda x: -x[1])[:15]),
            "files": files[:500],  # cap for large projects
        }
        r.stages_completed.append("scout")

    # ── Stage 2: Archaeologist ──

    def _stage_archaeologist(self, r: AnalysisResult) -> None:
        """核心模块深读: import 图、类/函数提取。"""
        modules: list[dict] = []
        import_graph: dict[str, list[str]] = {}

        for f in self._walk_files(ext=".py"):
            rel = str(f.relative_to(self.root))
            try:
                content = f.read_text("utf-8", errors="ignore")
            except Exception:
                continue
            imports = self._extract_imports(content)
            classes = re.findall(r'^class\s+(\w+)', content, re.MULTILINE)
            functions = re.findall(r'^def\s+(\w+)', content, re.MULTILINE)
            modules.append({
                "path": rel,
                "classes": classes,
                "functions": functions[:20],
                "import_count": len(imports),
            })
            import_graph[rel] = imports

        # Identify core modules (most imported)
        import_targets: Counter = Counter()
        for deps in import_graph.values():
            for d in deps:
                import_targets[d] += 1

        r.code_analysis = {
            "modules": modules[:200],
            "import_graph_size": len(import_graph),
            "most_imported": dict(import_targets.most_common(20)),
            "total_classes": sum(len(m["classes"]) for m in modules),
            "total_functions": sum(len(m["functions"]) for m in modules),
        }
        r.stages_completed.append("archaeologist")

    # ── Stage 3: Detective ──

    def _stage_detective(self, r: AnalysisResult) -> None:
        """业务规则和约束: 配置、环境变量、API 路由、硬编码。"""
        env_vars: set[str] = set()
        api_routes: list[dict] = []
        config_files: list[str] = []
        hardcoded: list[dict] = []

        for f in self._walk_files():
            rel = str(f.relative_to(self.root))
            if f.name in ("policy.json", "security_config.json", "memory_config.json",
                          ".env", ".env.example", "pyproject.toml", "package.json"):
                config_files.append(rel)

            if f.suffix != ".py":
                continue
            try:
                content = f.read_text("utf-8", errors="ignore")
            except Exception:
                continue
            # Environment variables
            for m in re.finditer(r'os\.(?:environ|getenv)\s*[\[\(]\s*["\'](\w+)', content):
                env_vars.add(m.group(1))
            # API routes
            for m in re.finditer(r'@(?:router|app)\.(get|post|put|delete|patch)\s*\(\s*["\']([^"\']+)', content):
                api_routes.append({"method": m.group(1).upper(), "path": m.group(2), "file": rel})
            # Hardcoded secrets/URLs (basic heuristic)
            for m in re.finditer(r'(?:password|secret|api_key|token)\s*=\s*["\']([^"\']{8,})', content, re.I):
                hardcoded.append({"file": rel, "hint": m.group(0)[:60]})

        r.domain = {
            "env_vars": sorted(env_vars),
            "api_routes": api_routes,
            "config_files": config_files,
            "hardcoded_secrets": hardcoded[:10],
            "route_count": len(api_routes),
        }
        r.stages_completed.append("detective")

    # ── Stage 4: Writer ──

    def _stage_writer(self, r: AnalysisResult) -> None:
        """规格和架构: 架构摘要、依赖列表、模块职责。"""
        # Dependencies from requirements/pyproject
        deps = self._parse_dependencies()

        # Architecture summary from directory structure
        top_dirs = list(r.inventory.get("top_dirs", {}).keys())
        module_roles: dict[str, str] = {}
        role_hints = {
            "api": "REST API 端点", "ports": "抽象接口层",
            "adapters": "适配器实现", "memory": "记忆系统",
            "execution": "任务执行", "checkup": "体检/诊断",
            "governance": "治理策略", "skills": "技能插件",
            "project_state": "项目状态", "reports": "报告生成",
            "tests": "测试套件", "docs": "文档",
            "frontend-v2": "Web 前端", "identity": "身份系统",
        }
        for d in top_dirs:
            module_roles[d] = role_hints.get(d, "未分类")

        # Mermaid architecture diagram
        mermaid = self._generate_mermaid(top_dirs, r.code_analysis.get("most_imported", {}))

        r.architecture = {
            "module_roles": module_roles,
            "mermaid_diagram": mermaid,
            "layer_count": len(top_dirs),
        }
        r.dependencies = {
            "python": deps,
            "total": len(deps),
        }
        r.stages_completed.append("writer")

    # ── Stage 5: Reviewer ──

    def _stage_reviewer(self, r: AnalysisResult) -> None:
        """Gap 和问题: 缺失测试、无文档模块、风险标注。"""
        questions = []
        confidence = []

        # Check test coverage gaps
        modules_with_tests = set()
        test_files = [f for f in self._walk_files(ext=".py")
                      if "test" in f.name.lower()]
        for tf in test_files:
            try:
                content = tf.read_text("utf-8", errors="ignore")
                for m in re.finditer(r'from\s+([\w.]+)\s+import', content):
                    modules_with_tests.add(m.group(1).split(".")[0])
            except Exception:
                pass

        all_modules = {m["path"].split("/")[0] for m in r.code_analysis.get("modules", [])
                       if "/" in m["path"]}
        untested = all_modules - modules_with_tests - {"tests", "docs", "_redundant_backup"}
        if untested:
            questions.append({
                "category": "testing",
                "text": f"以下模块缺少测试覆盖: {', '.join(sorted(untested))}",
                "severity": "medium",
            })

        # Check for missing docstrings in core files
        undocumented = []
        for m in r.code_analysis.get("modules", []):
            if m["classes"] and not any("core" in m["path"] or "brain" in m["path"]
                                       for _ in [1]):
                continue
            # simplified: just flag files with many functions but in core paths
            if ("brain" in m["path"] or "api/" in m["path"]) and len(m["functions"]) > 5:
                undocumented.append(m["path"])
        if undocumented:
            questions.append({
                "category": "documentation",
                "text": f"核心模块可能需要更完善文档: {', '.join(undocumented[:5])}",
                "severity": "low",
            })

        # Check required specs exist
        required_specs = ["inventory.md", "architecture.md", "dependencies.md"]
        for spec in required_specs:
            path = self._specs_dir / spec
            confidence.append({
                "spec": spec,
                "status": C_CONFIRMED if path.exists() else C_GAP,
                "note": "已生成" if path.exists() else "待生成",
            })

        # Hardcoded secrets warning
        if r.domain.get("hardcoded_secrets"):
            questions.append({
                "category": "security",
                "text": f"检测到 {len(r.domain['hardcoded_secrets'])} 处疑似硬编码密钥",
                "severity": "high",
            })

        # API without auth check
        route_count = r.domain.get("route_count", 0)
        if route_count > 10:
            questions.append({
                "category": "security",
                "text": f"项目有 {route_count} 个 API 路由，建议检查认证覆盖",
                "severity": "medium",
            })

        # Confidence summary
        inv = r.inventory
        confidence.append({
            "spec": "inventory",
            "status": C_CONFIRMED,
            "note": f"{inv.get('total_files', 0)} 文件, {inv.get('total_lines', 0)} 行",
        })
        confidence.append({
            "spec": "code-analysis",
            "status": C_CONFIRMED if r.code_analysis.get("total_classes", 0) > 0 else C_INFERRED,
            "note": f"{r.code_analysis.get('total_classes', 0)} 类, {r.code_analysis.get('total_functions', 0)} 函数",
        })
        gap_count = sum(1 for c in confidence if c["status"] == C_GAP)
        confirmed_count = sum(1 for c in confidence if c["status"] == C_CONFIRMED)
        confidence.append({
            "spec": "overall",
            "status": C_CONFIRMED if gap_count == 0 else C_INFERRED,
            "note": f"{confirmed_count} confirmed, {gap_count} gaps, {len(questions)} questions",
        })

        r.questions = questions
        r.confidence = confidence
        r.stages_completed.append("reviewer")

    # ── Output ──

    def _write_all_specs(self, r: AnalysisResult) -> None:
        """将分析结果写入 specs 目录。"""
        self._write_spec("inventory.md", self._render_inventory(r))
        self._write_spec("code-analysis.md", self._render_code_analysis(r))
        self._write_spec("domain.md", self._render_domain(r))
        self._write_spec("architecture.md", self._render_architecture(r))
        self._write_spec("dependencies.md", self._render_dependencies(r))
        self._write_spec("questions.md", self._render_questions(r))
        self._write_spec("confidence-report.md", self._render_confidence(r))
        # Save raw JSON for programmatic access
        raw_path = self._specs_dir / "analysis.json"
        raw_path.write_text(json.dumps({
            "project_id": r.project_id,
            "commit": r.commit,
            "timestamp": r.timestamp,
            "stages": r.stages_completed,
            "stats": {
                "files": r.inventory.get("total_files", 0),
                "lines": r.inventory.get("total_lines", 0),
                "classes": r.code_analysis.get("total_classes", 0),
                "functions": r.code_analysis.get("total_functions", 0),
                "routes": r.domain.get("route_count", 0),
                "questions": len(r.questions),
            },
        }, ensure_ascii=False, indent=2), encoding="utf-8")

    def _write_spec(self, name: str, content: str) -> None:
        (self._specs_dir / name).write_text(content, encoding="utf-8")

    # ── Renderers ──

    def _render_inventory(self, r: AnalysisResult) -> str:
        inv = r.inventory
        lines = [
            f"# 项目清单 — {self.project_id}",
            f"\n> 生成时间: {r.timestamp}  |  Commit: `{r.commit}`",
            f"\n## 概览\n",
            f"- **文件总数**: {inv.get('total_files', 0)}",
            f"- **代码总行数**: {inv.get('total_lines', 0)}",
            f"\n## 语言分布\n",
            "| 语言 | 行数 |",
            "|------|------|",
        ]
        for lang, count in inv.get("languages", {}).items():
            lines.append(f"| {lang} | {count:,} |")
        lines.append(f"\n## 目录结构\n")
        for d, count in inv.get("top_dirs", {}).items():
            lines.append(f"- `{d}/` — {count} 文件")
        return "\n".join(lines) + "\n"

    def _render_code_analysis(self, r: AnalysisResult) -> str:
        ca = r.code_analysis
        lines = [
            f"# 代码分析 — {self.project_id}",
            f"\n> Commit: `{r.commit}`",
            f"\n## 统计\n",
            f"- **模块数**: {len(ca.get('modules', []))}",
            f"- **类总数**: {ca.get('total_classes', 0)}",
            f"- **函数总数**: {ca.get('total_functions', 0)}",
            f"\n## 最常被引用的模块\n",
            "| 模块 | 被引用次数 |",
            "|------|-----------|",
        ]
        for mod, count in ca.get("most_imported", {}).items():
            lines.append(f"| `{mod}` | {count} |")
        return "\n".join(lines) + "\n"

    def _render_domain(self, r: AnalysisResult) -> str:
        dom = r.domain
        lines = [
            f"# 业务规则 — {self.project_id}",
            f"\n## 环境变量 ({len(dom.get('env_vars', []))})\n",
        ]
        for v in dom.get("env_vars", []):
            lines.append(f"- `{v}`")
        lines.append(f"\n## API 路由 ({dom.get('route_count', 0)})\n")
        lines.append("| 方法 | 路径 | 文件 |")
        lines.append("|------|------|------|")
        for rt in dom.get("api_routes", []):
            lines.append(f"| {rt['method']} | `{rt['path']}` | `{rt['file']}` |")
        lines.append(f"\n## 配置文件\n")
        for cf in dom.get("config_files", []):
            lines.append(f"- `{cf}`")
        if dom.get("hardcoded_secrets"):
            lines.append(f"\n## ⚠️ 疑似硬编码密钥\n")
            for h in dom["hardcoded_secrets"]:
                lines.append(f"- `{h['file']}`: `{h['hint']}`")
        return "\n".join(lines) + "\n"

    def _render_architecture(self, r: AnalysisResult) -> str:
        arch = r.architecture
        lines = [
            f"# 架构 — {self.project_id}",
            f"\n## 模块职责\n",
            "| 模块 | 职责 |",
            "|------|------|",
        ]
        for mod, role in arch.get("module_roles", {}).items():
            lines.append(f"| `{mod}/` | {role} |")
        lines.append(f"\n## 架构图\n")
        lines.append("```mermaid")
        lines.append(arch.get("mermaid_diagram", "graph LR\n  A[项目] --> B[待分析]"))
        lines.append("```")
        return "\n".join(lines) + "\n"

    def _render_dependencies(self, r: AnalysisResult) -> str:
        deps = r.dependencies
        lines = [
            f"# 依赖 — {self.project_id}",
            f"\n## Python 依赖 ({deps.get('total', 0)})\n",
            "| 包名 | 版本约束 |",
            "|------|---------|",
        ]
        for d in deps.get("python", []):
            lines.append(f"| `{d['name']}` | {d.get('version', '*')} |")
        return "\n".join(lines) + "\n"

    def _render_questions(self, r: AnalysisResult) -> str:
        lines = [
            f"# 问题与风险 — {self.project_id}",
            f"\n> {len(r.questions)} 个问题\n",
        ]
        severity_icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}
        for q in r.questions:
            icon = severity_icon.get(q["severity"], "⚪")
            lines.append(f"- {icon} **[{q['category']}]** {q['text']}")
        return "\n".join(lines) + "\n"

    def _render_confidence(self, r: AnalysisResult) -> str:
        lines = [
            f"# 置信度报告 — {self.project_id}",
            f"\n> {r.timestamp}\n",
            "| 产物 | 状态 | 说明 |",
            "|------|------|------|",
        ]
        for c in r.confidence:
            lines.append(f"| {c['spec']} | {c['status']} | {c['note']} |")
        return "\n".join(lines) + "\n"

    # ── Helpers ──

    def _walk_files(self, ext: str | None = None):
        for dirpath, dirnames, filenames in os.walk(self.root):
            dirnames[:] = [d for d in dirnames if d not in _IGNORE_DIRS]
            for fn in filenames:
                if fn.startswith("."):
                    continue
                p = Path(dirpath) / fn
                if ext and p.suffix.lower() != ext:
                    continue
                yield p

    def _extract_imports(self, content: str) -> list[str]:
        imports = []
        for m in re.finditer(r'^(?:from|import)\s+([\w.]+)', content, re.MULTILINE):
            imports.append(m.group(1).split(".")[0])
        return imports

    def _parse_dependencies(self) -> list[dict]:
        deps = []
        req = self.root / "requirements.txt"
        if req.exists():
            for line in req.read_text("utf-8", errors="ignore").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or line.startswith("-"):
                    continue
                m = re.match(r'^([a-zA-Z0-9_-]+)\s*([><=!~].*)?', line)
                if m:
                    deps.append({"name": m.group(1), "version": (m.group(2) or "").strip()})
        return deps

    def _generate_mermaid(self, dirs: list[str], most_imported: dict) -> str:
        lines = ["graph TD"]
        for d in dirs[:12]:
            lines.append(f"  {d}[{d}]")
        # Add edges for top import relationships
        seen = set()
        for mod, count in list(most_imported.items())[:10]:
            parts = mod.split(".")
            src = parts[0] if parts else mod
            if src in dirs:
                for d in dirs:
                    if d != src and d in str(most_imported):
                        edge = f"{d}-->{src}"
                        if edge not in seen:
                            lines.append(f"  {d} --> {src}")
                            seen.add(edge)
        return "\n".join(lines)

    def _git_commit(self) -> str:
        try:
            r = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                cwd=self.root, capture_output=True, text=True, timeout=2,
            )
            return r.stdout.strip() if r.returncode == 0 else ""
        except Exception:
            return ""

    def _load_last_commit(self) -> str | None:
        p = self._specs_dir / ".last_commit"
        return p.read_text("utf-8").strip() if p.exists() else None

    def _save_last_commit(self, commit: str) -> None:
        (self._specs_dir / ".last_commit").write_text(commit, encoding="utf-8")


def validate_specs(specs_dir: Path) -> list[dict]:
    """规格验证: 检查产物完整性。"""
    required = [
        "inventory.md", "code-analysis.md", "domain.md",
        "architecture.md", "dependencies.md", "questions.md",
        "confidence-report.md",
    ]
    results = []
    for name in required:
        path = specs_dir / name
        exists = path.exists()
        size = path.stat().st_size if exists else 0
        results.append({
            "file": name,
            "exists": exists,
            "size": size,
            "status": C_CONFIRMED if exists and size > 50 else C_GAP,
        })
    # Check mermaid in architecture
    arch = specs_dir / "architecture.md"
    if arch.exists():
        content = arch.read_text("utf-8", errors="ignore")
        has_mermaid = "```mermaid" in content
        results.append({
            "file": "architecture.md (mermaid)",
            "exists": has_mermaid,
            "size": 0,
            "status": C_CONFIRMED if has_mermaid else C_INFERRED,
        })
    return results
