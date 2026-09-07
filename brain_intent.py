"""Brain 预执行意图检测 Mixin — 在 LLM 调用前拦截明确工具意图。

从 brain_tool_guard.py 拆出（ISS-008），职责单一化。
"""

import json
import re

from logs import get_logger

logger = get_logger("brain")


class BrainIntentMixin:
    """预执行意图检测。混入 Brain 类。"""

    _PRE_EXEC_PATTERNS = [
        {
            "re": r"(\d+)\s*秒后?(?:提醒|叫)我?(.+?)$",
            "tool": "set_reminder",
            "extract": lambda m: {"message": m.group(2).strip() or "提醒", "seconds": int(m.group(1))},
        },
        {
            "re": r"(\d+)\s*分钟?后?(?:提醒|叫)我?(.+?)$",
            "tool": "set_reminder",
            "extract": lambda m: {"message": m.group(2).strip() or "提醒", "minutes": int(m.group(1))},
        },
        {
            "re": r"(?:提醒|叫)我?(.+?)(?:在|，)?(\d{1,2}:\d{2})",
            "tool": "set_reminder",
            "extract": lambda m: {"message": m.group(1).strip() or "提醒", "time": m.group(2)},
        },
        {
            "re": r"每天\s*(?:早上|上午|下午|晚上)?\s*(\d{1,2})\s*[点:：]\s*(\d{0,2})\s*(?:给我|发送|推送|提醒我?|告诉我)(.+?)(?:[。.!！]?)$",
            "tool": "scheduler",
            "extract": lambda m: {
                "action": "add",
                "name": m.group(3).strip()[:30],
                "schedule": f"{int(m.group(2)) if m.group(2) else 0} {int(m.group(1))} * * *",
                "command": m.group(3).strip(),
                "job_type": "cron",
            },
        },
    ]

    async def _pre_execute_intent(self, session_id: str, user_input: str, _s=None) -> bool:
        """在 LLM 调用前检测明确意图并预执行工具。返回 True 表示已执行。"""
        _s = _s or self.stream
        for pat in self._PRE_EXEC_PATTERNS:
            m = re.search(pat["re"], user_input)
            if not m:
                continue
            tool_name = pat["tool"]
            params = pat["extract"](m)
            msg = params.get("message", "")
            msg = re.sub(r"^[你我]", "", msg).strip()
            if msg:
                params["message"] = msg
            logger.info(f"[{session_id}] 预执行: 检测到 {tool_name} 意图，直接执行")
            try:
                result = await self.tools.execute(tool_name, params, session_id=session_id)
                result_text = str(result.get("result") or result.get("error") or "")
                await _s.emit("tool_call", f"{tool_name}({json.dumps(params, ensure_ascii=False)})")
                await _s.emit("tool_result", result_text[:200])
                logger.info(f"[{session_id}] 预执行: {tool_name} 成功: {result_text[:80]}")
                self._history.append({"role": "assistant", "content": None, "tool_calls": [{
                    "id": f"pre_{tool_name}", "type": "function",
                    "function": {"name": tool_name, "arguments": json.dumps(params, ensure_ascii=False)},
                }]})
                self._history.append({"role": "tool", "tool_call_id": f"pre_{tool_name}", "content": result_text})
                return True
            except Exception as e:
                logger.error(f"[{session_id}] 预执行: {tool_name} 失败: {e}")
                return False
        return False
