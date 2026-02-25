"""Broadcast Stream Adapter — 将 Brain 输出广播到所有 WebSocket 连接。

用于 Cron 任务执行：Brain 处理结果需要推送给所有在线用户。
"""

import json
from typing import Any

from ports.stream_port import StreamPort
from logs import get_logger

logger = get_logger("stream.broadcast")


class BroadcastStreamAdapter(StreamPort):
    """广播流适配器：收集 Brain 输出并通过 WebSocket 广播。"""

    def __init__(self, ws_channel, job_name: str = "", job_id: str = ""):
        self._ws = ws_channel
        self._job_name = job_name
        self._job_id = job_id
        self._chunks: list[str] = []
        self._tool_calls: list[str] = []

    async def emit(self, event_type: str, data: Any) -> None:
        """收集流式事件，关键事件实时广播。"""
        if event_type == "token":
            if data:
                self._chunks.append(str(data))
        elif event_type == "tool_call":
            self._tool_calls.append(str(data))
        elif event_type == "complete":
            full_text = "".join(self._chunks)
            if full_text.strip():
                await self._broadcast_result(full_text)
                self._save_run_log(full_text, "ok")
        elif event_type == "error":
            await self._broadcast_result(f"❌ 任务执行出错: {data}")
            self._save_run_log(str(data), "error")

    async def _broadcast_result(self, text: str):
        """将结果作为 cron_result 消息广播到所有连接。"""
        msg = json.dumps({
            "type": "cron_result",
            "data": {
                "job_name": self._job_name,
                "content": text,
                "tool_calls": self._tool_calls,
            }
        }, ensure_ascii=False)
        try:
            await self._ws.broadcast(msg)
            logger.info(f"📡 Cron结果已广播: {self._job_name} ({len(text)}字)")
        except Exception as e:
            logger.error(f"📡 广播失败: {e}")

    def _save_run_log(self, result: str, status: str):
        """将执行结果保存到 cron job 的运行历史中。"""
        if not self._job_id:
            return
        try:
            import time
            from api.cron import _jobs, _save_jobs
            for job in _jobs:
                if job.get("id") == self._job_id:
                    runs = job.setdefault("runs", [])
                    runs.append({
                        "ts": time.time(),
                        "status": status,
                        "result": result[:500],
                        "tools": self._tool_calls[:5],
                    })
                    # 只保留最近 10 次
                    job["runs"] = runs[-10:]
                    _save_jobs()
                    break
        except Exception as e:
            logger.debug(f"保存运行日志失败: {e}")

    def get_result(self) -> str:
        """获取完整输出文本。"""
        return "".join(self._chunks)
