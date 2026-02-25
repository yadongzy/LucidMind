"""S28: 错误恢复增强 — auto-compaction + session reset + 对话修复。

对标 OpenClaw: auto-compaction → session reset → retry 链路。
Brain 在异常时调用此模块进行恢复，不修改 brain.py 核心逻辑。
"""
import json
from pathlib import Path
from typing import Any

from logs import get_logger

logger = get_logger("recovery")

_DATA_DIR = Path(__file__).parent.parent / "data"


class RecoveryManager:
    """对话恢复管理器。"""

    def __init__(self, memory_adapter=None):
        self._memory = memory_adapter
        self._recovery_log = _DATA_DIR / "recovery_log.json"
        self._log_entries: list[dict] = []
        self._load_log()

    def _load_log(self):
        try:
            if self._recovery_log.exists():
                self._log_entries = json.loads(self._recovery_log.read_text(encoding="utf-8"))
        except Exception:
            self._log_entries = []

    def _save_log(self):
        try:
            self._recovery_log.write_text(json.dumps(self._log_entries[-50:], ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            logger.warning(f"恢复日志保存失败: {e}")

    async def auto_compact(self, session_id: str, history: list[dict], max_msgs: int = 30) -> list[dict]:
        """自动压缩：截断过长历史，保留最近消息。"""
        if len(history) <= max_msgs:
            return history
        removed = len(history) - max_msgs
        compacted = history[-max_msgs:]
        # 在开头插入摘要标记
        compacted.insert(0, {"role": "system", "content": f"[自动压缩] 已移除 {removed} 条旧消息以释放上下文空间。"})
        self._log_entries.append({"type": "auto_compact", "session": session_id, "removed": removed})
        self._save_log()
        logger.info(f"[{session_id}] 自动压缩: 移除 {removed} 条, 保留 {max_msgs} 条")
        return compacted

    async def session_reset(self, session_id: str) -> dict[str, Any]:
        """会话重置：清空历史，保留记忆。"""
        if self._memory:
            try:
                # 备份当前历史
                history = await self._memory.get_context(session_id)
                if history:
                    backup_path = _DATA_DIR / "sessions" / f"{session_id}_backup.json"
                    backup_path.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")
                    logger.info(f"[{session_id}] 历史已备份: {len(history)} 条 → {backup_path}")
                # 清空会话
                session_path = _DATA_DIR / "sessions" / f"{session_id}.json"
                if session_path.exists():
                    session_path.write_text("[]", encoding="utf-8")
            except Exception as e:
                logger.error(f"[{session_id}] 会话重置失败: {e}")
                return {"success": False, "error": str(e)}

        self._log_entries.append({"type": "session_reset", "session": session_id})
        self._save_log()
        logger.info(f"[{session_id}] 会话已重置")
        return {"success": True, "message": f"会话 {session_id} 已重置，历史已备份"}

    async def diagnose_error(self, error: Exception, context: dict) -> dict[str, str]:
        """诊断错误并建议恢复策略。"""
        err_str = str(error).lower()
        if "context_length" in err_str or "too many tokens" in err_str:
            return {"strategy": "auto_compact", "reason": "上下文超长，需要压缩历史"}
        if "rate_limit" in err_str or "429" in err_str:
            return {"strategy": "wait_retry", "reason": "速率限制，等待后重试"}
        if "timeout" in err_str or "connection" in err_str:
            return {"strategy": "retry", "reason": "网络问题，直接重试"}
        if "invalid" in err_str and "json" in err_str:
            return {"strategy": "session_reset", "reason": "对话数据损坏，需要重置"}
        return {"strategy": "log_and_continue", "reason": f"未知错误: {error}"}
