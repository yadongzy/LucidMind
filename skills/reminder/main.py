"""提醒技能 — 设置定时提醒，统一通过 Cron 系统管理。

用途：用户让大脑"5分钟后提醒我"或"下午3点提醒我开会"时调用。
提醒创建为 at 类型的 cron job，持久化存储，触发后自动入队任务。
"""

from datetime import datetime, timedelta
from typing import Any

from ports.tool_port import ToolPort
from logs import get_logger

logger = get_logger("skills.reminder")


class ReminderAdapter(ToolPort):
    """定时提醒工具（基于统一 Cron 系统）。"""

    def list_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "set_reminder",
                    "description": "设置一个定时提醒。支持秒级精度。用户说30秒就传seconds=30，说5分钟就传minutes=5，说15:30就传time=15:30",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "message": {"type": "string", "description": "提醒内容"},
                            "seconds": {"type": "integer", "description": "多少秒后提醒（最高优先级，用户说30秒就传30）"},
                            "minutes": {"type": "number", "description": "多少分钟后提醒（支持小数如0.5=30秒）"},
                            "time": {"type": "string", "description": "提醒时间，格式HH:MM（绝对时间）"},
                        },
                        "required": ["message"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "list_reminders",
                    "description": "查看所有待触发的提醒",
                    "parameters": {"type": "object", "properties": {}, "required": []},
                },
            },
        ]

    async def execute(self, tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
        if tool_name == "set_reminder":
            return self._set_reminder(params)
        elif tool_name == "list_reminders":
            return self._list_reminders()
        return {"success": False, "error": f"未知工具: {tool_name}"}

    def _set_reminder(self, params: dict) -> dict[str, Any]:
        message = params.get("message", "")
        if not message:
            return {"success": False, "error": "提醒内容不能为空"}

        now = datetime.now()
        seconds = params.get("seconds")
        minutes = params.get("minutes")
        time_str = params.get("time")

        if seconds:
            trigger_at = now + timedelta(seconds=int(seconds))
        elif minutes:
            trigger_at = now + timedelta(seconds=float(minutes) * 60)
        elif time_str:
            try:
                h, m = time_str.split(":")
                trigger_at = now.replace(hour=int(h), minute=int(m), second=0)
                if trigger_at <= now:
                    trigger_at += timedelta(days=1)
            except Exception:
                return {"success": False, "error": f"时间格式错误: {time_str}，请用 HH:MM"}
        else:
            return {"success": False, "error": "请指定 minutes 或 time 参数"}

        # 通过统一 Cron 系统创建 at 类型任务
        try:
            from api.cron import add_job
            job = add_job(
                description=f"⏰ {message}",
                command=message,
                trigger_at=trigger_at.isoformat(),
                job_type="at",
                name=f"reminder_{message[:20]}",
            )
        except Exception as e:
            return {"success": False, "error": f"创建定时任务失败: {e}"}

        delta = trigger_at - now
        total_secs = int(delta.total_seconds())
        mins = total_secs // 60
        secs = total_secs % 60
        if mins > 0:
            time_desc = f"{mins}分{secs}秒后" if secs else f"{mins}分钟后"
        else:
            time_desc = f"{secs}秒后"
        logger.info(f"⏰ 设置提醒: {message} ({time_desc}) → cron job {job['id']}")

        return {
            "success": True,
            "result": f"已设置提醒: {message}\n触发时间: {trigger_at.strftime('%H:%M:%S')}\n({time_desc})\n任务ID: {job['id']}",
        }

    def _list_reminders(self) -> dict[str, Any]:
        try:
            from api.cron import get_jobs
            jobs = get_jobs()
            pending = [j for j in jobs if j.get("type") == "at" and j.get("enabled")]
            if not pending:
                return {"success": True, "result": "没有待触发的提醒"}
            lines = []
            for j in pending:
                trigger_at = j.get("trigger_at", "")
                try:
                    t = datetime.fromisoformat(trigger_at)
                    lines.append(f"⏰ {t.strftime('%H:%M')} — {j.get('command', j.get('description', ''))}")
                except Exception:
                    lines.append(f"⏰ {trigger_at} — {j.get('command', '')}")
            return {"success": True, "result": "\n".join(lines)}
        except Exception as e:
            return {"success": False, "error": f"查询失败: {e}"}
