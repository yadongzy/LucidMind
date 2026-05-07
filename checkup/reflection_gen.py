"""REFLECTION.md Auto-Generator — 自动生成项目反思文档。

综合体检结果、进化日志、用户行为模式，生成 REFLECTION.md:
- 系统做了什么好
- 系统做了什么不好
- 下一步应该改进什么
- 用户行为洞察

灵感来源: The Code Agent Orchestra (Addy Osmani) 的 REFLECTION.md 模式。
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from logs import get_logger

logger = get_logger("checkup.reflection_gen")

_PROJECT_ROOT = Path(__file__).parent.parent
_REFLECTION_PATH = _PROJECT_ROOT / "REFLECTION.md"


def generate_reflection(
    checkup_report: dict | None = None,
    evolution_stats: dict | None = None,
    behavior_patterns: list[dict] | None = None,
    suggestions: list[dict] | None = None,
) -> str:
    """生成 REFLECTION.md 内容。"""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        f"# REFLECTION.md — LucidMind 自省报告",
        f"",
        f"> 自动生成于 {now}",
        f"> 此文件由进化引擎自动更新，反映系统当前状态和改进方向。",
        f"",
    ]

    # 1. 健康状态
    lines.append("## 1. 系统健康")
    lines.append("")
    if checkup_report:
        score = checkup_report.get("score", 0)
        icon = "🟢" if score >= 80 else "🟡" if score >= 60 else "🔴"
        lines.append(f"{icon} **健康分数: {score}/100**")
        lines.append("")
        checks = checkup_report.get("checks", [])
        for c in checks:
            status_icon = {"pass": "✅", "warn": "⚠️", "fail": "❌", "skip": "⏭️"}.get(c["status"], "❓")
            lines.append(f"- {status_icon} {c['name']}: {c['message']}")
        lines.append("")
    else:
        lines.append("_未运行体检_")
        lines.append("")

    # 2. 进化记录
    lines.append("## 2. 近期进化")
    lines.append("")
    if evolution_stats:
        total = evolution_stats.get("total", 0)
        success = evolution_stats.get("success", 0)
        rate = evolution_stats.get("success_rate", 0)
        lines.append(f"- **总进化次数**: {total}")
        lines.append(f"- **成功率**: {rate:.0%} ({success}/{total})")
        lines.append("")
    else:
        lines.append("_暂无进化记录_")
        lines.append("")

    # 3. 做得好的
    lines.append("## 3. 做得好的 ✅")
    lines.append("")
    good_things = _extract_good(checkup_report, evolution_stats)
    if good_things:
        for g in good_things:
            lines.append(f"- {g}")
    else:
        lines.append("- _待积累数据_")
    lines.append("")

    # 4. 需要改进的
    lines.append("## 4. 需要改进的 ⚠️")
    lines.append("")
    bad_things = _extract_bad(checkup_report, behavior_patterns)
    if bad_things:
        for b in bad_things:
            lines.append(f"- {b}")
    else:
        lines.append("- _无明显问题_")
    lines.append("")

    # 5. 用户行为洞察
    lines.append("## 5. 用户行为洞察")
    lines.append("")
    if behavior_patterns:
        for p in behavior_patterns:
            lines.append(f"- **{p.get('pattern_type', '?')}**: {p.get('description', '')}")
            if p.get("suggestion"):
                lines.append(f"  - 建议: {p['suggestion']}")
    else:
        lines.append("_暂无行为数据_")
    lines.append("")

    # 6. 改进建议队列
    lines.append("## 6. 改进建议队列")
    lines.append("")
    if suggestions:
        lines.append("| ID | 标题 | 级别 | 执行器 | 状态 |")
        lines.append("|---|---|---|---|---|")
        for s in suggestions:
            lines.append(f"| {s.get('id','')} | {s.get('title','')} | {s.get('severity','')} | {s.get('executor','')} | {s.get('status','')} |")
    else:
        lines.append("_暂无待处理建议_")
    lines.append("")

    # 7. 下一步
    lines.append("## 7. 下一步行动")
    lines.append("")
    next_actions = _suggest_next_actions(checkup_report, evolution_stats, behavior_patterns)
    for a in next_actions:
        lines.append(f"- [ ] {a}")
    lines.append("")

    return "\n".join(lines)


def save_reflection(**kwargs) -> Path:
    """生成并保存 REFLECTION.md。"""
    content = generate_reflection(**kwargs)
    _REFLECTION_PATH.write_text(content, encoding="utf-8")
    logger.info(f"REFLECTION.md 已更新 ({len(content)} chars)")
    return _REFLECTION_PATH


def _extract_good(checkup: dict | None, evo: dict | None) -> list[str]:
    """提取做得好的。"""
    good = []
    if checkup:
        for c in checkup.get("checks", []):
            if c["status"] == "pass":
                good.append(f"{c['name']}: {c['message']}")
    if evo and evo.get("success_rate", 0) > 0.7:
        good.append(f"进化成功率高: {evo['success_rate']:.0%}")
    return good


def _extract_bad(checkup: dict | None, patterns: list[dict] | None) -> list[str]:
    """提取需改进的。"""
    bad = []
    if checkup:
        for c in checkup.get("checks", []):
            if c["status"] in ("fail", "warn"):
                bad.append(f"{c['name']}: {c['message']}")
    if patterns:
        for p in patterns:
            if p.get("confidence", 0) > 0.5:
                bad.append(p.get("description", ""))
    return bad


def _suggest_next_actions(checkup: dict | None, evo: dict | None,
                          patterns: list[dict] | None) -> list[str]:
    """生成下一步行动列表。"""
    actions = []
    if checkup:
        score = checkup.get("score", 100)
        if score < 80:
            actions.append(f"提升健康分数至 ≥80 (当前 {score})")
        for c in checkup.get("checks", []):
            if c["status"] == "fail":
                actions.append(f"修复: {c['name']} — {c['message']}")
    if evo and evo.get("total", 0) == 0:
        actions.append("完成首次自动修复闭环")
    if patterns:
        for p in patterns:
            if p.get("suggestion"):
                actions.append(p["suggestion"])
    if not actions:
        actions.append("继续保持系统健康")
    return actions[:10]
