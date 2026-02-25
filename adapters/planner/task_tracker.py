"""S57: 多轮任务追踪 — 规划器步骤跨对话持久化+逐步执行。

将 TaskPlan 持久化到 JSON 文件，每轮对话自动恢复进度，
当前步骤完成后自动推进到下一步。
不修改 brain.py（规则 06）。
"""
import json
import os
import time
from pathlib import Path
from typing import Any

from logs import get_logger

logger = get_logger("tracker")

DATA_DIR = Path(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))) / "data"
PLANS_DIR = DATA_DIR / "plans"


class TaskTracker:
    """多轮任务追踪器 — 持久化计划进度，跨对话恢复。"""

    def __init__(self):
        PLANS_DIR.mkdir(parents=True, exist_ok=True)

    def _path(self, session_id: str) -> Path:
        safe = session_id.replace("/", "_").replace("\\", "_")[:64]
        return PLANS_DIR / f"{safe}.json"

    def save_plan(self, session_id: str, plan_data: dict) -> None:
        """保存计划到文件。"""
        plan_data["updated_at"] = time.time()
        p = self._path(session_id)
        try:
            p.write_text(json.dumps(plan_data, ensure_ascii=False, indent=2), encoding="utf-8")
            logger.info(f"计划保存: session={session_id}, goal={plan_data.get('goal', '')[:40]}")
        except OSError as e:
            logger.error(f"计划保存失败: {e}")

    def load_plan(self, session_id: str) -> dict | None:
        """加载会话的活跃计划。"""
        p = self._path(session_id)
        if not p.exists():
            return None
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            if data.get("status") == "active":
                return data
            return None
        except (json.JSONDecodeError, OSError):
            return None

    def advance_step(self, session_id: str, step_id: int,
                     result: str = "", error: str = "") -> dict | None:
        """完成当前步骤，推进到下一步。返回更新后的计划。"""
        plan = self.load_plan(session_id)
        if not plan:
            return None
        steps = plan.get("steps", [])
        for s in steps:
            if s.get("id") == step_id:
                s["status"] = "done" if not error else "failed"
                s["result"] = result[:500]
                s["error"] = error[:200] if error else ""
                break
        # 检查是否全部完成
        pending = [s for s in steps if s["status"] == "pending"]
        if not pending:
            plan["status"] = "completed"
            logger.info(f"计划完成: session={session_id}")
        else:
            next_step = pending[0]
            next_step["status"] = "running"
            logger.info(f"推进到步骤 {next_step['id']}: {next_step.get('desc', '')[:40]}")
        self.save_plan(session_id, plan)
        return plan

    def get_current_step_context(self, session_id: str) -> str:
        """获取当前步骤的上下文提示（注入到 LLM 对话中）。"""
        plan = self.load_plan(session_id)
        if not plan:
            return ""
        steps = plan.get("steps", [])
        current = None
        for s in steps:
            if s["status"] in ("pending", "running"):
                current = s
                break
        if not current:
            return ""
        done = [s for s in steps if s["status"] == "done"]
        total = len(steps)
        ctx = f"\n[任务追踪] 目标: {plan['goal']}\n"
        ctx += f"当前步骤 ({current['id']}/{total}): {current.get('desc', '')}\n"
        if done:
            ctx += "已完成: " + "; ".join(
                f"#{s['id']}{s.get('desc', '')[:30]}" for s in done[-3:]
            ) + "\n"
        if current.get("tool"):
            ctx += f"建议工具: {current['tool']}\n"
        return ctx

    def cancel_plan(self, session_id: str) -> bool:
        """取消当前计划。"""
        p = self._path(session_id)
        if p.exists():
            plan = self.load_plan(session_id)
            if plan:
                plan["status"] = "cancelled"
                self.save_plan(session_id, plan)
                logger.info(f"计划取消: session={session_id}")
                return True
        return False

    def list_plans(self) -> list[dict]:
        """列出所有活跃计划（用于 API 展示）。"""
        result = []
        for f in PLANS_DIR.glob("*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                if data.get("status") == "active":
                    result.append({
                        "session": f.stem,
                        "goal": data.get("goal", ""),
                        "progress": f"{sum(1 for s in data.get('steps', []) if s['status'] == 'done')}/{len(data.get('steps', []))}",
                    })
            except Exception:
                pass
        return result
