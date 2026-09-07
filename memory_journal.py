"""会话记忆持久化 — 每日自动总结对话，写入 data/memory/YYYY-MM-DD.md。

参考 OpenClaw 的 memory/YYYY-MM-DD.md 日记模式：
- 每天一个文件，记录当天的对话摘要
- 大脑空闲时自动触发总结
- 保留最近30天的日记文件
"""

import json
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

from logs import get_logger

logger = get_logger("memory_journal")

_MEMORY_DIR = Path(__file__).parent / "data" / "memory"
_MAX_DAYS = 30  # 保留最近30天


def _ensure_dir():
    _MEMORY_DIR.mkdir(parents=True, exist_ok=True)


def get_today_path() -> Path:
    _ensure_dir()
    return _MEMORY_DIR / f"{date.today().isoformat()}.md"


def append_entry(entry: str, category: str = "对话") -> None:
    """追加一条记忆条目到今日日记。"""
    _ensure_dir()
    path = get_today_path()
    now = datetime.now().strftime("%H:%M")
    line = f"- **{now}** [{category}] {entry}\n"
    if not path.exists():
        header = f"# 日记 — {date.today().isoformat()}\n\n"
        path.write_text(header + line, encoding="utf-8")
    else:
        with open(path, "a", encoding="utf-8") as f:
            f.write(line)


def save_conversation_summary(session_id: str, user_input: str,
                               assistant_reply: str, tools_used: list = None) -> None:
    """保存一次对话的摘要到今日日记。"""
    # 只保存有实质内容的对话
    if not user_input or len(user_input.strip()) < 3:
        return
    # 精简内容
    user_short = user_input[:100].replace("\n", " ")
    reply_short = (assistant_reply or "")[:100].replace("\n", " ")
    tools_str = ""
    if tools_used:
        tools_str = f" 工具: {', '.join(tools_used[:3])}"
    entry = f"用户: {user_short} → 回复: {reply_short}{tools_str}"
    append_entry(entry, "对话")


def save_event(event: str, category: str = "事件") -> None:
    """记录一个系统事件。"""
    append_entry(event, category)


def get_today_journal() -> str:
    """读取今日日记内容。"""
    path = get_today_path()
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def get_recent_journals(days: int = 7) -> list[dict]:
    """获取最近N天的日记列表。"""
    _ensure_dir()
    result = []
    today = date.today()
    for i in range(days):
        d = today - timedelta(days=i)
        path = _MEMORY_DIR / f"{d.isoformat()}.md"
        if path.exists():
            content = path.read_text(encoding="utf-8")
            lines = [l for l in content.split("\n") if l.startswith("- ")]
            result.append({
                "date": d.isoformat(),
                "entries": len(lines),
                "preview": lines[0][:80] if lines else "",
            })
    return result


def cleanup_old_journals() -> int:
    """清理超过 _MAX_DAYS 天的旧日记。"""
    _ensure_dir()
    cutoff = date.today() - timedelta(days=_MAX_DAYS)
    removed = 0
    for f in _MEMORY_DIR.glob("*.md"):
        try:
            file_date = date.fromisoformat(f.stem)
            if file_date < cutoff:
                f.unlink()
                removed += 1
        except (ValueError, OSError):
            pass
    if removed:
        logger.info(f"🗑️ 清理旧日记: {removed} 个文件")
    return removed
