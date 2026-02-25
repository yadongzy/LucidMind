"""Scheduler Tool Adapter — 定时任务管理。

委托 api/cron.py 作为单一数据源，本 Adapter 只是工具接口层。
"""

from typing import Any

from ports.tool_port import ToolPort
from logs import get_logger

logger = get_logger("tools")


class SchedulerAdapter(ToolPort):
    """定时任务管理工具。委托 api/cron.py 统一调度。"""

    async def execute(self, tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
        if tool_name != "scheduler":
            return {"success": False, "result": None, "error": f"Unknown tool: {tool_name}"}
        from api.cron import add_job, remove_job_by_name, get_jobs
        action = params.get("action", "list")
        try:
            if action == "list":
                jobs = get_jobs()
                if not jobs:
                    return {"success": True, "result": "没有定时任务"}
                lines = [f"共 {len(jobs)} 个任务:"]
                for j in jobs:
                    lines.append(f"  [{j.get('name','?')}] {j.get('schedule','?')} → {j.get('command','?')[:60]}")
                return {"success": True, "result": "\n".join(lines)}
            elif action == "add":
                name = params.get("name", "unnamed")
                schedule = params.get("schedule", "daily")
                command = params.get("command", "")
                job_type = params.get("job_type", "every")
                trigger_at = params.get("trigger_at", "")
                job = add_job(description=name, command=command,
                              schedule=schedule, name=name,
                              job_type=job_type, trigger_at=trigger_at)
                type_label = job.get('type', 'every')
                if type_label == 'cron':
                    return {"success": True, "result": f"已添加定时日程: {name} (id={job['id']}, cron={schedule})"}
                return {"success": True, "result": f"已添加任务: {name} (id={job['id']}, 每{job.get('interval_seconds',0)}秒)"}
            elif action == "remove":
                name = params.get("name", "")
                removed = remove_job_by_name(name)
                if removed:
                    return {"success": True, "result": f"已删除 {removed} 个任务"}
                return {"success": True, "result": f"未找到任务: {name}"}
            elif action == "status":
                jobs = get_jobs()
                enabled = sum(1 for j in jobs if j.get("enabled", True))
                return {"success": True, "result": f"总计 {len(jobs)} 个任务, {enabled} 个启用"}
            else:
                return {"success": False, "result": None, "error": f"Unknown action: {action}"}
        except Exception as e:
            return {"success": False, "result": None, "error": str(e)}

    def list_tools(self) -> list[dict[str, Any]]:
        return [{"type": "function", "function": {
            "name": "scheduler",
            "description": "定时任务管理。创建/查看/删除定时任务。",
            "parameters": {"type": "object", "properties": {
                "action": {"type": "string", "enum": ["list", "add", "remove", "status"],
                           "description": "list=查看任务, add=添加, remove=删除, status=运行状态"},
                "name": {"type": "string", "description": "任务名称（add/remove时必填）"},
                "schedule": {"type": "string", "description": "调度频率: hourly/daily/weekly/monthly 或 cron表达式如 '0 8 * * *'(每天8点)"},
                "command": {"type": "string", "description": "要执行的命令（add时必填）"},
                "job_type": {"type": "string", "enum": ["every", "cron"], "description": "任务类型: every=间隔重复, cron=cron表达式定时(如每天8点用cron)"},
                "trigger_at": {"type": "string", "description": "一次性触发时间ISO格式(at类型专用)"}

            }, "required": ["action"]}
        }}]
