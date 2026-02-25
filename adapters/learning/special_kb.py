"""特别行为数据库 — 把外部大模型的优质回答缓存给本地模型复用。

核心设计原则：
1. Brain 自己判断问题是否可缓存（不用关键词模板）
   - 分析回答内容的特征：含实时数据/日期/价格 → 动态，不缓存
   - 纯知识/方法/概念 → 静态，可缓存
2. 答案可更新 — 更好的回答替换旧的，用户纠正后降质量
3. 动态问题永不缓存，即使被问多次

判断方法（语义级，不是关键词模板）：
- 回答本身就是证据：含具体日期/温度/价格/实时数据 → 时效性内容
- 问题本身就是证据：问的是"现在/今天/最新/当前" → 时效性查询
- 两者结合分析，不依赖固定模板
"""

import hashlib
import json
import os
import re
import time
from pathlib import Path
from typing import Any

from logs import get_logger

logger = get_logger("special_kb")

_KB_DIR = Path(__file__).parent.parent.parent / "data"
_KB_FILE = _KB_DIR / "special_kb.json"


def _normalize(text: str) -> str:
    t = text.strip().lower()
    t = re.sub(r'[^\w\s]', '', t)
    return re.sub(r'\s+', ' ', t).strip()


def _hash(text: str) -> str:
    return hashlib.md5(_normalize(text).encode()).hexdigest()[:16]


def _similarity(a: str, b: str) -> float:
    wa = set(re.findall(r'\w+', a.lower()))
    wb = set(re.findall(r'\w+', b.lower()))
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / len(wa | wb)


def _is_temporal(question: str, answer: str) -> bool:
    """判断问答对是否具有时效性（动态内容）。

    核心原则：分析问题的"主语意图"，不是偶然出现的词。
    - 短问题（<50字）中出现时间词 → 大概率是在问实时信息
    - 长问题（>50字）中偶然出现时间词 → 可能只是举例/引用，需要更强信号
    - 时间词 + 状态查询词同时出现 → 强信号
    - 知识类问题特征 → 降低时效性判断
    """
    q = question.lower()
    a = answer.lower()
    q_len = len(q)

    # === 问题特征分析 ===
    temporal_q_signals = 0
    has_time_anchor = bool(re.search(
        r'(今天|现在|当前|此刻|目前|最近|最新|刚才|实时|today|now|current|latest|recent|live)', q
    ))
    has_state_query = bool(re.search(
        r'(天气|气温|温度|股[票价]|汇率|价格|多少钱|比分|新闻|热搜|排行|weather|stock|price|score|news)', q
    ))
    has_knowledge = bool(re.search(
        r'(是什么|什么是|区别|原理|怎么做|如何|教程|概念|定义|分析|方案|架构|设计|优缺点|建议|what is|how to|difference|explain|design|analyze)', q
    ))

    # 短问题：时间词权重高（"今天天气怎么样" = 10字，意图明确）
    # 长问题：时间词权重低（可能只是举例引用）
    time_weight = 2 if q_len < 50 else 1

    if has_time_anchor:
        temporal_q_signals += time_weight
    if has_state_query:
        temporal_q_signals += 2
    # 时间词+状态查询同时出现 → 额外加分（强信号）
    if has_time_anchor and has_state_query:
        temporal_q_signals += 1
    # 知识类问题 → 大幅降低
    if has_knowledge:
        temporal_q_signals -= 3

    # === 回答特征分析 ===
    temporal_a_signals = 0
    if re.search(r'20\d{2}[-/年]\d{1,2}[-/月]\d{1,2}', a):
        temporal_a_signals += 1
    if re.search(r'(\d+\.?\d*\s*[°℃℉%]|\$\d+|¥\d+|￥\d+)', a):
        temporal_a_signals += 1
    if re.search(r'(截至|截止|as of|目前为止|据最新)', a):
        temporal_a_signals += 2

    score = temporal_q_signals + temporal_a_signals
    # 阈值：需要足够强的信号才判定为动态
    is_temp = score >= 3
    if is_temp:
        logger.debug(f"时效性判断: score={score} (q_sig={temporal_q_signals}, a_sig={temporal_a_signals}, len={q_len}) → 动态")
    return is_temp


class SpecialKB:
    """特别行为数据库 — 只缓存静态知识，动态内容永不缓存。"""

    def __init__(self):
        _KB_DIR.mkdir(parents=True, exist_ok=True)
        self._entries: list[dict[str, Any]] = self._load()
        logger.info(f"SpecialKB 初始化: {len(self._entries)} 条记录")

    def _load(self) -> list[dict]:
        if _KB_FILE.exists():
            try:
                return json.loads(_KB_FILE.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass
        return []

    def _save(self):
        try:
            _KB_FILE.write_text(
                json.dumps(self._entries, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
        except OSError as e:
            logger.error(f"保存失败: {e}")

    def record(self, question: str, answer: str, model: str, quality: float = 0.7):
        """记录一次外部模型的回答。动态内容不记录。"""
        # 核心：Brain 自己判断是否时效性内容
        if _is_temporal(question, answer):
            logger.info(f"SpecialKB 跳过(动态内容): {question[:50]}...")
            return

        q_hash = _hash(question)

        # 查找已有记录 → 更新
        for entry in self._entries:
            if entry["hash"] == q_hash or _similarity(question, entry["question"]) > 0.7:
                entry["ask_count"] = entry.get("ask_count", 1) + 1
                entry["last_asked"] = time.time()
                # 答案更新：更好的回答替换旧的（更长更详细 或 质量更高）
                old_len = len(entry.get("answer", ""))
                if len(answer) > old_len * 1.2 or quality > entry.get("quality", 0):
                    entry["answer"] = answer[:3000]
                    entry["model"] = model
                    entry["updated_at"] = time.time()
                    logger.info(f"SpecialKB 答案更新: 旧{old_len}字→新{len(answer)}字")
                entry["quality"] = max(entry.get("quality", 0.5), quality)
                if entry["ask_count"] >= 2:
                    entry["cached"] = True
                self._save()
                logger.info(f"SpecialKB 更新: ask={entry['ask_count']}, cached={entry.get('cached')}")
                return

        # 新记录
        self._entries.append({
            "hash": q_hash,
            "question": question[:500],
            "answer": answer[:3000],
            "model": model,
            "quality": quality,
            "ask_count": 1,
            "cached": False,
            "temporal": False,
            "created_at": time.time(),
            "last_asked": time.time(),
            "updated_at": time.time(),
        })
        if len(self._entries) > 500:
            self._entries.sort(key=lambda e: e.get("quality", 0) * e.get("ask_count", 1), reverse=True)
            self._entries = self._entries[:400]
        self._save()
        logger.info(f"SpecialKB 新增(静态知识): {question[:50]}...")

    def lookup(self, question: str) -> dict | None:
        """查找缓存的优质回答。动态问题直接返回 None。"""
        # 问题本身就有时效性信号 → 不查缓存
        if _is_temporal(question, ""):
            return None

        q_hash = _hash(question)
        best = None
        best_sim = 0.0

        for entry in self._entries:
            if not entry.get("cached"):
                continue
            if entry["hash"] == q_hash:
                entry["ask_count"] = entry.get("ask_count", 0) + 1
                entry["last_asked"] = time.time()
                self._save()
                return entry
            sim = _similarity(question, entry["question"])
            if sim > 0.7 and sim > best_sim:
                best = entry
                best_sim = sim

        if best:
            best["ask_count"] = best.get("ask_count", 0) + 1
            best["last_asked"] = time.time()
            self._save()
        return best

    def update_answer(self, question: str, new_answer: str, model: str):
        """用户提供更好的回答时，更新缓存。"""
        q_hash = _hash(question)
        for entry in self._entries:
            if entry["hash"] == q_hash or _similarity(question, entry["question"]) > 0.7:
                entry["answer"] = new_answer[:3000]
                entry["model"] = model
                entry["quality"] = min(1.0, entry.get("quality", 0.5) + 0.15)
                entry["updated_at"] = time.time()
                self._save()
                logger.info(f"SpecialKB 手动更新答案: {question[:40]}...")
                return True
        return False

    def downgrade_quality(self, question: str):
        """用户纠正 → 降低质量分，质量太低则取消缓存。"""
        q_hash = _hash(question)
        for entry in self._entries:
            if entry["hash"] == q_hash or _similarity(question, entry["question"]) > 0.7:
                entry["quality"] = max(0.0, entry.get("quality", 0.5) - 0.2)
                if entry["quality"] < 0.3:
                    entry["cached"] = False  # 质量太差，取消缓存
                    logger.info(f"SpecialKB 取消缓存(质量过低): {question[:40]}...")
                self._save()
                return

    def boost_quality(self, question: str):
        """用户满意（无纠正）→ 提升质量分。"""
        q_hash = _hash(question)
        for entry in self._entries:
            if entry["hash"] == q_hash or _similarity(question, entry["question"]) > 0.7:
                entry["quality"] = min(1.0, entry.get("quality", 0.5) + 0.1)
                self._save()
                return

    def get_stats(self) -> dict:
        total = len(self._entries)
        cached = sum(1 for e in self._entries if e.get("cached"))
        avg_q = sum(e.get("quality", 0) for e in self._entries) / max(total, 1)
        return {
            "total_entries": total,
            "cached_entries": cached,
            "avg_quality": round(avg_q, 2),
            "total_asks_saved": sum(e.get("ask_count", 0) for e in self._entries),
        }
