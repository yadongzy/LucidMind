"""微调数据收集管道 — 自动记录大模型高质量对话，用于未来微调本地模型。

当外部大模型成功回复时，自动收集 (messages, response) 对。
格式兼容 OpenAI fine-tune API。
上限 10000 条，FIFO 淘汰。
"""

import json
from pathlib import Path
from datetime import datetime

from logs import get_logger
from atomic_persistence import append_jsonl, atomic_write_text

logger = get_logger("finetune")
_DATA = Path(__file__).parent / "data"
_PAIRS_FILE = _DATA / "finetune_pairs.jsonl"
_MAX_PAIRS = 10000


def collect(messages: list[dict], response: dict, model: str):
    """收集一条高质量对话对。

    过滤条件：
    1. 回复长度 > 50 字
    2. 无错误标记
    3. 非工具调用（纯对话更适合微调）
    """
    content = response.get("content", "")
    if not content or len(content) < 50:
        return
    if response.get("tool_calls"):
        return
    if "error" in content.lower()[:20]:
        return

    # 提取有效的 user/assistant 消息对
    clean = []
    for m in messages:
        if m.get("role") in ("user", "assistant") and m.get("content"):
            clean.append({"role": m["role"], "content": m["content"][:2000]})
    if not clean:
        return
    # 加上本次回复
    clean.append({"role": "assistant", "content": content[:2000]})

    entry = {
        "messages": clean[-6:],  # 最多保留最近6条
        "model": model,
        "collected_at": datetime.now().isoformat(),
    }

    _DATA.mkdir(exist_ok=True)
    try:
        append_jsonl(_PAIRS_FILE, entry)
        _trim_if_needed()
        logger.debug(f"收集微调数据: {len(clean)}条消息, 模型={model}")
    except Exception as e:
        logger.warning(f"微调数据收集失败: {e}")


def _trim_if_needed():
    """超过上限时 FIFO 淘汰。"""
    if not _PAIRS_FILE.exists():
        return
    try:
        lines = _PAIRS_FILE.read_text("utf-8").splitlines()
        if len(lines) > _MAX_PAIRS:
            keep = lines[-_MAX_PAIRS:]
            atomic_write_text(_PAIRS_FILE, "\n".join(keep) + "\n")
            logger.info(f"微调数据淘汰: {len(lines)}→{len(keep)}")
    except Exception:
        pass


def get_stats() -> dict:
    """获取收集统计。"""
    if not _PAIRS_FILE.exists():
        return {"count": 0, "file": str(_PAIRS_FILE)}
    try:
        count = sum(1 for _ in open(_PAIRS_FILE, "r", encoding="utf-8"))
        size_kb = _PAIRS_FILE.stat().st_size / 1024
        return {"count": count, "size_kb": round(size_kb, 1), "file": str(_PAIRS_FILE)}
    except Exception:
        return {"count": 0, "file": str(_PAIRS_FILE)}


def export_for_finetune(output_path: str | None = None) -> str:
    """导出为 OpenAI fine-tune 兼容格式。"""
    if not _PAIRS_FILE.exists():
        return "无数据"
    out = Path(output_path) if output_path else _DATA / "finetune_export.jsonl"
    try:
        lines = _PAIRS_FILE.read_text("utf-8").splitlines()
        exported = []
        for line in lines:
            try:
                entry = json.loads(line)
                exported.append(json.dumps({"messages": entry["messages"]}, ensure_ascii=False))
            except Exception:
                continue
        atomic_write_text(out, "\n".join(exported) + "\n")
        return f"导出 {len(exported)} 条到 {out}"
    except Exception as e:
        return f"导出失败: {e}"
