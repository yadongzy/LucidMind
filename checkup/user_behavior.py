"""User Behavior Perception — 用户行为感知模块。

不只是统计，而是从行为中发现模式 → 主动生成改进建议。

感知维度:
1. 频繁操作检测（同一功能/查询 ≥3 次 → 建议优化）
2. 错误热点（用户频繁遇到的问题 → 建议修复）
3. 未使用能力（已有功能但用户不知道 → 建议推介）
4. 使用趋势（时段、话题偏好 → 个性化）
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path

from logs import get_logger

logger = get_logger("checkup.user_behavior")

_DATA_DIR = Path(__file__).parent.parent / "data" / "behavior"


@dataclass
class BehaviorPattern:
    """检测到的用户行为模式。"""
    pattern_type: str       # frequent_query | error_hotspot | unused_feature | peak_hours
    description: str
    evidence: list[str] = field(default_factory=list)
    suggestion: str = ""
    confidence: float = 0.0  # 0.0 - 1.0
    created_at: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ImprovementSuggestion:
    """主动改进建议。"""
    id: str
    title: str
    description: str
    source_pattern: str         # 来自哪个行为模式
    severity: str = "L2"        # L0-L4
    executor: str = "codex_patch"  # codex_patch | local_cli | manual
    status: str = "proposed"    # proposed | approved | rejected | executed
    user_response: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


class UserBehaviorAnalyzer:
    """用户行为分析器。从反思统计中提取可操作的模式。"""

    def __init__(self, data_dir: Path | None = None):
        self._dir = data_dir or _DATA_DIR
        self._dir.mkdir(parents=True, exist_ok=True)

    def analyze(self, reflection_stats: dict | None = None) -> list[BehaviorPattern]:
        """分析用户行为，返回检测到的模式列表。"""
        stats = reflection_stats or self._load_reflection_stats()
        if not stats:
            return []

        patterns = []
        patterns.extend(self._detect_frequent_queries(stats))
        patterns.extend(self._detect_error_hotspots(stats))
        patterns.extend(self._detect_peak_hours(stats))
        patterns.extend(self._detect_repeated_questions(stats))

        if patterns:
            logger.info(f"检测到 {len(patterns)} 个用户行为模式")
        return patterns

    def generate_suggestions(self, patterns: list[BehaviorPattern]) -> list[ImprovementSuggestion]:
        """从行为模式生成改进建议。"""
        suggestions = []
        for i, p in enumerate(patterns):
            if p.confidence < 0.5:
                continue
            suggestions.append(ImprovementSuggestion(
                id=f"SUG-{i+1:03d}",
                title=p.description[:60],
                description=p.suggestion,
                source_pattern=p.pattern_type,
                severity="L1" if p.pattern_type in ("frequent_query", "peak_hours") else "L2",
                executor="codex_patch" if p.pattern_type == "error_hotspot" else "manual",
            ))
        return suggestions

    def _detect_frequent_queries(self, stats: dict) -> list[BehaviorPattern]:
        """检测频繁查询/操作。"""
        patterns = []
        topic_counts = stats.get("topic_counts", {})
        for topic, count in topic_counts.items():
            if count >= 3:
                patterns.append(BehaviorPattern(
                    pattern_type="frequent_query",
                    description=f"用户频繁查询: '{topic}' ({count}次)",
                    evidence=[f"topic_counts[{topic}]={count}"],
                    suggestion=f"考虑为 '{topic}' 创建快捷入口或自动化脚本",
                    confidence=min(count / 5, 1.0),
                    created_at=time.time(),
                ))
        return patterns

    def _detect_error_hotspots(self, stats: dict) -> list[BehaviorPattern]:
        """检测错误热点。"""
        patterns = []
        tool_loops = stats.get("tool_loop_warnings", 0)
        if tool_loops >= 2:
            patterns.append(BehaviorPattern(
                pattern_type="error_hotspot",
                description=f"工具循环发生 {tool_loops} 次",
                evidence=[f"tool_loop_warnings={tool_loops}"],
                suggestion="检查工具调用逻辑，可能有参数解析或重试策略问题",
                confidence=min(tool_loops / 5, 1.0),
                created_at=time.time(),
            ))
        return patterns

    def _detect_peak_hours(self, stats: dict) -> list[BehaviorPattern]:
        """检测使用高峰时段。"""
        hourly = stats.get("hourly_activity", {})
        if not hourly:
            return []
        total = sum(hourly.values())
        if total < 10:
            return []
        peak = max(hourly, key=hourly.get)
        peak_pct = hourly[peak] / total
        if peak_pct > 0.3:
            return [BehaviorPattern(
                pattern_type="peak_hours",
                description=f"用户最活跃时段: {peak}:00 ({peak_pct:.0%} 的活动)",
                evidence=[f"hourly[{peak}]={hourly[peak]}/{total}"],
                suggestion=f"可在 {peak}:00 前后安排定时体检和建议推送",
                confidence=peak_pct,
                created_at=time.time(),
            )]
        return []

    def _detect_repeated_questions(self, stats: dict) -> list[BehaviorPattern]:
        """检测重复提问频率。"""
        repeated = stats.get("repeated_questions", 0)
        total = stats.get("total_messages", 1)
        if repeated >= 3:
            ratio = repeated / total
            return [BehaviorPattern(
                pattern_type="frequent_query",
                description=f"重复提问率 {ratio:.1%} ({repeated}/{total})",
                evidence=[f"repeated_questions={repeated}"],
                suggestion="改进回答质量或增加对话记忆功能，减少用户重复提问",
                confidence=min(ratio * 5, 1.0),
                created_at=time.time(),
            )]
        return []

    def _load_reflection_stats(self) -> dict:
        """从 data/reflection_stats.json 加载。"""
        stats_file = self._dir.parent / "reflection_stats.json"
        if stats_file.exists():
            try:
                return json.loads(stats_file.read_text("utf-8"))
            except (json.JSONDecodeError, OSError):
                pass
        return {}
