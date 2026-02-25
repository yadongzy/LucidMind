"""S33: Goal System — 目标驱动，让大脑有追求。

长期目标 + 短期任务队列，驱动 Brain 的行为选择。
- 长期目标: 变得更聪明、更有用、减少错误
- 短期目标: 用户任务、学习新技能、优化经验
- 目标可以被用户设定，也可以由 Brain 自主生成

不修改 brain.py（规则 06）。
"""
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from logs import get_logger

logger = get_logger("goals")

_GOALS_PATH = Path(__file__).parent.parent / "data" / "goals.json"


class GoalSystem:
    """目标管理系统。"""

    def __init__(self):
        self._goals: list[dict] = []
        self._load()

    def _load(self):
        try:
            if _GOALS_PATH.exists():
                self._goals = json.loads(_GOALS_PATH.read_text(encoding="utf-8"))
        except Exception:
            self._goals = []
        # 确保有默认长期目标
        if not any(g.get("type") == "long_term" for g in self._goals):
            self._goals.extend([
                {"id": "lt_1", "type": "long_term", "content": "变得更聪明 — 从每次交互中学习", "status": "active", "created": datetime.now().isoformat()},
                {"id": "lt_2", "type": "long_term", "content": "减少错误 — 同样的错误不犯第二次", "status": "active", "created": datetime.now().isoformat()},
                {"id": "lt_3", "type": "long_term", "content": "更好地理解用户 — 记住偏好和习惯", "status": "active", "created": datetime.now().isoformat()},
            ])
            self._save()

    def _save(self):
        try:
            _GOALS_PATH.parent.mkdir(parents=True, exist_ok=True)
            _GOALS_PATH.write_text(json.dumps(self._goals, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            logger.warning(f"目标保存失败: {e}")

    def add_goal(self, content: str, goal_type: str = "short_term", priority: str = "medium") -> dict:
        """添加目标。"""
        goal = {
            "id": f"g_{len(self._goals)+1}",
            "type": goal_type,
            "content": content,
            "priority": priority,
            "status": "active",
            "created": datetime.now().isoformat(),
            "progress": [],
        }
        self._goals.append(goal)
        self._save()
        logger.info(f"🎯 新目标: [{goal_type}] {content[:60]}")
        return goal

    def complete_goal(self, goal_id: str, result: str = "") -> bool:
        """完成目标。"""
        for g in self._goals:
            if g["id"] == goal_id:
                g["status"] = "completed"
                g["completed_at"] = datetime.now().isoformat()
                if result: g["result"] = result
                self._save()
                logger.info(f"✅ 目标完成: {g['content'][:40]}")
                return True
        return False

    def update_progress(self, goal_id: str, note: str) -> bool:
        """更新目标进度。"""
        for g in self._goals:
            if g["id"] == goal_id:
                g.setdefault("progress", []).append({"time": datetime.now().isoformat(), "note": note})
                self._save()
                return True
        return False

    def get_active_goals(self) -> list[dict]:
        """获取所有活跃目标。"""
        return [g for g in self._goals if g.get("status") == "active"]

    def get_context_for_brain(self) -> str:
        """生成注入 Brain system prompt 的目标上下文。"""
        active = self.get_active_goals()
        if not active:
            return ""
        lines = ["## 当前目标"]
        for g in active[:5]:
            icon = "🎯" if g["type"] == "long_term" else "📌"
            lines.append(f"- {icon} [{g['type']}] {g['content']}")
        return "\n".join(lines)

    def auto_generate_goals(self, session_stats: dict) -> list[dict]:
        """基于会话统计自动生成短期目标。"""
        new_goals = []
        total_msgs = session_stats.get("total_messages", 0)
        error_count = session_stats.get("errors", 0)

        if error_count > 3 and not any("减少错误" in g["content"] for g in self.get_active_goals()):
            new_goals.append(self.add_goal("分析最近的错误模式，找出根因", "short_term", "high"))

        if total_msgs > 50 and not any("整理" in g["content"] for g in self.get_active_goals()):
            new_goals.append(self.add_goal("整理经验库，合并重复经验", "short_term", "medium"))

        return new_goals

    def get_all(self) -> list[dict]:
        return self._goals
