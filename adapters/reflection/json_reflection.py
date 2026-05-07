"""JSON Reflection Adapter — 自省能力实现。

核心功能：
1. 重复提问检测 — 用户问了相似问题时主动提醒
2. 工具循环检测 — 同一工具被反复调用时警告
3. 用户行为模式分析 — 统计用户偏好（话题、时段、工具使用）
4. 反思摘要 — 注入 system prompt，让 Brain 知道自己的表现
"""

import hashlib
import json
import os
import time
from collections import Counter
from pathlib import Path
from typing import Any

from ports.reflection_port import ReflectionPort
from logs import get_logger

logger = get_logger("reflection")


def _text_hash(text: str) -> str:
    """对文本做简单哈希，用于重复检测。"""
    normalized = text.strip().lower()
    # 去掉标点，只保留核心内容
    import re
    normalized = re.sub(r'[^\w\s]', '', normalized)
    normalized = re.sub(r'\s+', ' ', normalized).strip()
    return hashlib.md5(normalized.encode()).hexdigest()[:12]


def _similarity(a: str, b: str) -> float:
    """简单的 Jaccard 相似度。"""
    import re
    wa = set(re.findall(r'\w+', a.lower()))
    wb = set(re.findall(r'\w+', b.lower()))
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / len(wa | wb)


class JSONReflectionAdapter(ReflectionPort):
    """基于 JSON 的自省适配器。"""

    def __init__(self, data_dir: str | None = None):
        self.data_dir = Path(data_dir or os.path.join(
            os.path.dirname(__file__), "..", "..", "data"
        ))
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._stats_file = self.data_dir / "reflection_stats.json"
        self._stats = self._load_stats()
        # 会话级缓存
        self._session_messages: dict[str, list[dict]] = {}
        self._session_tool_calls: dict[str, list[dict]] = {}
        logger.info("自省适配器初始化完成")

    def _load_stats(self) -> dict:
        if self._stats_file.exists():
            try:
                return json.loads(self._stats_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass
        return {
            "total_messages": 0,
            "total_tool_calls": 0,
            "topic_counts": {},
            "repeated_questions": 0,
            "tool_loop_warnings": 0,
            "hourly_activity": {},
        }

    def _save_stats(self):
        try:
            self._stats_file.write_text(
                json.dumps(self._stats, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
        except OSError as e:
            logger.error(f"保存反思统计失败: {e}")

    async def on_user_message(self, session_id: str, message: str) -> dict[str, Any]:
        """分析用户消息：重复检测 + 行为模式。"""
        result: dict[str, Any] = {"repeated": False, "similar_count": 0}

        # 初始化会话缓存
        if session_id not in self._session_messages:
            self._session_messages[session_id] = []

        history = self._session_messages[session_id]

        # 重复检测：与历史消息比较相似度
        msg_hash = _text_hash(message)
        similar_count = 0
        for prev in history:
            if prev["hash"] == msg_hash:
                similar_count += 1
            elif _similarity(message, prev["text"]) > 0.6:
                similar_count += 1

        if similar_count >= 1:
            result["repeated"] = True
            result["similar_count"] = similar_count
            result["hint"] = f"用户已经问过 {similar_count} 次类似问题"
            self._stats["repeated_questions"] = self._stats.get("repeated_questions", 0) + 1
            logger.info(f"[{session_id}] 检测到重复提问 (第{similar_count+1}次): {message[:50]}")

        # 记录消息
        history.append({
            "text": message[:200],
            "hash": msg_hash,
            "time": time.time(),
        })
        # 只保留最近 50 条
        if len(history) > 50:
            history[:] = history[-50:]

        # 更新统计
        self._stats["total_messages"] = self._stats.get("total_messages", 0) + 1
        hour = time.strftime("%H")
        hourly = self._stats.get("hourly_activity", {})
        hourly[hour] = hourly.get(hour, 0) + 1
        self._stats["hourly_activity"] = hourly

        self._save_stats()
        return result

    async def on_tool_call(self, session_id: str, tool_name: str, params: dict) -> dict[str, Any]:
        """工具循环检测。"""
        result: dict[str, Any] = {"loop_detected": False}

        if session_id not in self._session_tool_calls:
            self._session_tool_calls[session_id] = []

        calls = self._session_tool_calls[session_id]
        call_hash = _text_hash(f"{tool_name}:{json.dumps(params, sort_keys=True)}")

        # 检测：最近 10 次调用中，同一工具+参数出现 >= 3 次
        recent = calls[-10:]
        same_count = sum(1 for c in recent if c["hash"] == call_hash)

        if same_count >= 3:
            result["loop_detected"] = True
            result["count"] = same_count
            result["warning"] = f"工具 {tool_name} 已用相同参数调用 {same_count} 次，可能陷入循环"
            self._stats["tool_loop_warnings"] = self._stats.get("tool_loop_warnings", 0) + 1
            logger.warning(f"[{session_id}] 工具循环检测: {tool_name} x{same_count}")

        # ping-pong 检测：A-B-A-B 交替模式
        if len(recent) >= 4:
            last4_hashes = [c["hash"] for c in recent[-4:]]
            if last4_hashes[0] == last4_hashes[2] and last4_hashes[1] == last4_hashes[3] and last4_hashes[0] != last4_hashes[1]:
                result["loop_detected"] = True
                result["pattern"] = "ping-pong"
                result["warning"] = "检测到 ping-pong 循环: 两个工具交替调用"
                logger.warning(f"[{session_id}] Ping-pong 循环检测")

        calls.append({"tool": tool_name, "hash": call_hash, "time": time.time()})
        if len(calls) > 30:
            calls[:] = calls[-30:]

        self._stats["total_tool_calls"] = self._stats.get("total_tool_calls", 0) + 1
        self._save_stats()
        return result

    async def get_reflection(self, session_id: str) -> str:
        """生成反思摘要，注入 system prompt。"""
        lines = []
        stats = self._stats

        total_msg = stats.get("total_messages", 0)
        total_tools = stats.get("total_tool_calls", 0)
        repeated = stats.get("repeated_questions", 0)
        loops = stats.get("tool_loop_warnings", 0)

        if total_msg > 0:
            lines.append(f"累计处理 {total_msg} 条消息, {total_tools} 次工具调用")

        if repeated > 0:
            lines.append(f"⚠ 检测到 {repeated} 次重复提问 — 反思: 是否回答不够清晰？是否需要主动总结？")

        if loops > 0:
            lines.append(f"⚠ 触发 {loops} 次工具循环警告 — 反思: 是否需要换策略？")

        # 会话级重复检测提示
        history = self._session_messages.get(session_id, [])
        if len(history) >= 2:
            recent_hashes = [m["hash"] for m in history[-5:]]
            hash_counts = Counter(recent_hashes)
            for h, count in hash_counts.items():
                if count >= 2:
                    # 找到重复的文本
                    for m in reversed(history):
                        if m["hash"] == h:
                            lines.append(f"⚠ 用户本次会话重复问了: '{m['text'][:40]}...' ({count}次) — 你之前的回答可能不够好，请改进")
                            break

        # 活跃时段分析
        hourly = stats.get("hourly_activity", {})
        if hourly:
            peak_hour = max(hourly, key=hourly.get)
            lines.append(f"用户最活跃时段: {peak_hour}:00")

        return "\n".join(lines) if lines else ""
