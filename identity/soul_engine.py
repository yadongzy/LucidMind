"""S32: Soul Engine — 动态灵魂，让 SOUL.md 可进化。

Brain 可以基于经验修改自己的行为规则：
- 发现反复犯错 → 自动在 SOUL 中加规则
- 发现有效模式 → 强化为习惯
- 用户反馈 → 调整性格参数

不修改 brain.py（规则 06），通过文件操作 SOUL.md。
"""
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from logs import get_logger

logger = get_logger("soul")

_SOUL_PATH = Path(__file__).parent / "SOUL.md"
_EVOLUTION_LOG = Path(__file__).parent / "soul_evolution.json"


class SoulEngine:
    """灵魂进化引擎。"""

    def __init__(self):
        self._evolution_log: list[dict] = []
        self._load_log()

    def _load_log(self):
        try:
            if _EVOLUTION_LOG.exists():
                self._evolution_log = json.loads(_EVOLUTION_LOG.read_text(encoding="utf-8"))
        except Exception:
            self._evolution_log = []

    def _save_log(self):
        try:
            _EVOLUTION_LOG.write_text(
                json.dumps(self._evolution_log[-100:], ensure_ascii=False, indent=2),
                encoding="utf-8")
        except Exception as e:
            logger.warning(f"进化日志保存失败: {e}")

    def get_soul(self) -> str:
        """读取当前灵魂。"""
        try:
            return _SOUL_PATH.read_text(encoding="utf-8")
        except Exception:
            return ""

    def evolve(self, trigger: str, new_rule: str, category: str = "Learned Rules") -> bool:
        """向 SOUL.md 添加一条进化规则。

        Args:
            trigger: 触发原因（如"用户多次纠正格式问题"）
            new_rule: 新规则内容
            category: 规则分类（默认 Learned Rules）
        """
        soul = self.get_soul()
        if not soul:
            logger.warning("SOUL.md 不存在，无法进化")
            return False

        # 检查是否已有类似规则（防重复 — 按行完整匹配，忽略首尾空白和列表符号）
        normalized_new = new_rule.strip().lstrip("- ").strip()
        for line in soul.splitlines():
            normalized_existing = line.strip().lstrip("- ").strip()
            if normalized_existing and normalized_new and normalized_existing == normalized_new:
                logger.info(f"规则已存在，跳过: {new_rule[:50]}")
                return False

        # 查找或创建 Learned Rules 段落
        section_header = f"## {category}"
        if section_header in soul:
            # 在已有段落末尾追加
            lines = soul.split("\n")
            insert_idx = None
            in_section = False
            for i, line in enumerate(lines):
                if line.strip() == section_header:
                    in_section = True
                elif in_section and line.startswith("## "):
                    insert_idx = i
                    break
            if insert_idx is None:
                insert_idx = len(lines)
            lines.insert(insert_idx, f"- {new_rule}")
            new_soul = "\n".join(lines)
        else:
            # 在文件末尾添加新段落
            new_soul = soul.rstrip() + f"\n\n{section_header}\n\n- {new_rule}\n"

        # 检查 SOUL.md 行数限制（规则10: 200行上限）
        if new_soul.count("\n") > 195:
            logger.warning("SOUL.md 接近200行上限，拒绝进化")
            return False

        # 写入
        try:
            _SOUL_PATH.write_text(new_soul, encoding="utf-8")
        except Exception as e:
            logger.error(f"SOUL.md 写入失败: {e}")
            return False

        # 记录进化日志
        entry = {
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "trigger": trigger,
            "rule": new_rule,
            "category": category,
        }
        self._evolution_log.append(entry)
        self._save_log()
        logger.info(f"🧬 灵魂进化: [{category}] {new_rule[:60]} (触发: {trigger[:40]})")
        return True

    def analyze_patterns(self, lessons: list[dict]) -> list[dict]:
        """分析经验库，发现可进化为灵魂规则的模式。

        按 category 聚合统计（而非精确 trigger 匹配），
        只推荐 effectiveness 已验证的高频类别。
        """
        suggestions = []
        # 按 category 聚合
        cat_lessons: dict[str, list[dict]] = {}
        for l in lessons:
            cat = l.get("category", "general")
            cat_lessons.setdefault(cat, []).append(l)

        for cat, group in cat_lessons.items():
            if cat == "general" or len(group) < 3:
                continue
            # 取 effectiveness 最高且已验证的经验作为规则建议
            verified = [l for l in group if l.get("effectiveness") is not None
                        and l.get("applied_count", 0) >= 1]
            if not verified:
                continue
            best = max(verified, key=lambda x: (x.get("effectiveness", 0), x.get("applied_count", 0)))
            if best.get("effectiveness", 0) < 0.5:
                continue
            suggestions.append({
                "trigger": f"[{cat}] {len(group)}条同类经验，最佳: {best.get('trigger', '')[:40]}",
                "count": len(group),
                "suggested_rule": best.get("lesson", "")[:100],
            })

        # 按数量排序，优先进化最频繁的类别
        suggestions.sort(key=lambda x: x["count"], reverse=True)
        return suggestions

    def get_evolution_history(self) -> list[dict]:
        """获取进化历史。"""
        return self._evolution_log[-20:]
