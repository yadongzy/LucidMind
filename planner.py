"""S42: 对话规划器 — 多步任务自动拆解+执行+验证。

复杂任务 → LLM拆解为步骤 → 逐步执行 → 每步验证 → 汇总结果。
简单任务 → 直接跳过规划。

不修改 brain.py（规则 06），作为独立模块被 brain.py 调用。
"""
import json
import time
from typing import Any

from logs import get_logger

logger = get_logger("planner")


class TaskStep:
    """单个任务步骤。"""
    __slots__ = ("id", "description", "tool", "status", "result", "error")

    def __init__(self, id: int, description: str, tool: str = ""):
        self.id = id
        self.description = description
        self.tool = tool
        self.status = "pending"  # pending → running → done / failed
        self.result = ""
        self.error = ""

    def to_dict(self) -> dict:
        return {"id": self.id, "desc": self.description, "tool": self.tool,
                "status": self.status, "result": self.result[:200]}


class TaskPlan:
    """一个完整的任务计划。"""

    def __init__(self, goal: str, steps: list[TaskStep]):
        self.goal = goal
        self.steps = steps
        self.created_at = time.time()
        self.status = "active"  # active → completed / failed

    @property
    def progress(self) -> str:
        done = sum(1 for s in self.steps if s.status == "done")
        return f"{done}/{len(self.steps)}"

    @property
    def current_step(self) -> TaskStep | None:
        for s in self.steps:
            if s.status == "pending":
                return s
        return None

    def to_dict(self) -> dict:
        return {"goal": self.goal, "status": self.status,
                "progress": self.progress,
                "steps": [s.to_dict() for s in self.steps]}


def needs_planning(metacog: dict) -> bool:
    """判断是否需要规划（基于元认知结果）。"""
    complexity = metacog.get("complexity", "simple")
    tools_needed = metacog.get("tools_needed", [])
    return complexity in ("complex", "multi_step") or len(tools_needed) >= 2


async def create_plan(user_input: str, llm_adapter, tools: list[dict] | None = None) -> TaskPlan | None:
    """用 LLM 将复杂任务拆解为步骤计划。"""
    tool_names = [t["function"]["name"] for t in (tools or [])]
    prompt = f"""将以下用户任务拆解为具体执行步骤。

用户任务: {user_input}

可用工具: {', '.join(tool_names[:15])}

要求:
1. 每步一个动作，步骤数 ≤ 5
2. 每步指明用哪个工具（如果需要）
3. 返回 JSON 数组: [{{"step": "描述", "tool": "工具名或空"}}]
4. 只返回 JSON，不要其他文字"""

    try:
        messages = [{"role": "system", "content": "你是任务规划专家。只返回JSON。"},
                    {"role": "user", "content": prompt}]
        resp = await llm_adapter.chat(messages)
        content = resp.get("content", "")
        # 提取 JSON
        if "```" in content:
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        steps_data = json.loads(content.strip())
        if not isinstance(steps_data, list) or len(steps_data) == 0:
            return None
        steps = [TaskStep(i + 1, s.get("step", ""), s.get("tool", ""))
                 for i, s in enumerate(steps_data[:5])]
        plan = TaskPlan(goal=user_input, steps=steps)
        logger.info(f"📋 计划创建: {len(steps)} 步 — {user_input[:50]}")
        return plan
    except Exception as e:
        logger.warning(f"计划创建失败: {e}")
        return None


def format_plan_for_stream(plan: TaskPlan) -> str:
    """格式化计划用于思维流展示。"""
    lines = [f"📋 任务规划 ({plan.progress})"]
    for s in plan.steps:
        icon = {"pending": "⬜", "running": "🔄", "done": "✅", "failed": "❌"}.get(s.status, "⬜")
        tool_tag = f" [{s.tool}]" if s.tool else ""
        lines.append(f"  {icon} {s.id}. {s.description}{tool_tag}")
    return "\n".join(lines)


def format_step_context(plan: TaskPlan, step: TaskStep) -> str:
    """生成当前步骤的上下文提示，注入到 LLM 对话中。"""
    completed = [s for s in plan.steps if s.status == "done"]
    ctx = f"\n\n[任务规划] 目标: {plan.goal}\n"
    ctx += f"当前步骤 ({step.id}/{len(plan.steps)}): {step.description}\n"
    if completed:
        ctx += "已完成步骤:\n"
        for c in completed[-3:]:
            ctx += f"  ✅ {c.id}. {c.description} → {c.result[:80]}\n"
    if step.tool:
        ctx += f"建议工具: {step.tool}\n"
    return ctx
