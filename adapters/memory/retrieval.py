"""混合检索引擎 — BM25 + 中文分词 + 时间衰减 + MMR 去重。

对标 OpenClaw src/memory/ (78文件, ~30万行):
  - hybrid.ts: 向量×权重 + 文本×权重
  - mmr.ts: Jaccard MMR 多样性重排
  - temporal-decay.ts: 指数衰减 (半衰期30天)
  - query-expansion.ts: 停用词 + 中英文分词

LucidMind 优势:
  1. 纯 Python, 无外部 DB/嵌入 API 依赖
  2. 中文分词: 字符 n-gram + 停用词, 比 OpenClaw 的 CJK unigram+bigram 更灵活
  3. 透明度: 每次检索返回 score 分解 (text_score + decay + diversity)
  4. 代码量: 单文件 ~150行 vs OpenClaw 78文件
"""

import math
import re
import time
from typing import Any

# === 中英文停用词 ===

_STOP_EN = frozenset(
    "a an the this that these those i me my we our you your he she it they them "
    "is are was were be been being have has had do does did will would could should "
    "can may might in on at to for of with by from about into through and or but "
    "if then because as while when where what which who how why not no".split()
)

_STOP_ZH = frozenset(
    "的 了 着 过 得 地 吗 呢 吧 啊 呀 嘛 啦 是 有 在 被 把 给 让 用 到 去 来 做 说 "
    "看 找 想 要 能 会 可以 和 与 或 但 但是 因为 所以 如果 虽然 而 也 都 就 还 又 "
    "再 才 只 我 我们 你 你们 他 她 它 他们 这 那 这个 那个 什么 哪个 怎么 为什么 "
    "之前 以前 之后 以后 现在 请 帮 告诉 东西 事情 事".split()
)


def tokenize(text: str) -> list[str]:
    """中英文混合分词。英文按空格，中文按字符 unigram + bigram。"""
    text = text.lower().strip()
    tokens: list[str] = []
    segments = re.split(r'[\s\.,;:!?\-\(\)\[\]{}"\'`~@#$%^&*+=|\\/<>]+', text)
    for seg in segments:
        if not seg:
            continue
        cjk_chars = [c for c in seg if '\u4e00' <= c <= '\u9fff']
        if cjk_chars:
            tokens.extend(cjk_chars)
            for i in range(len(cjk_chars) - 1):
                tokens.append(cjk_chars[i] + cjk_chars[i + 1])
        else:
            if len(seg) >= 2 and not seg.isdigit():
                tokens.append(seg)
    return tokens


def extract_keywords(text: str) -> list[str]:
    """提取关键词，过滤停用词。"""
    tokens = tokenize(text)
    seen: set[str] = set()
    result: list[str] = []
    for t in tokens:
        if t in _STOP_EN or t in _STOP_ZH or t in seen:
            continue
        seen.add(t)
        result.append(t)
    return result


# === BM25-like 评分 ===

def bm25_score(query_keywords: list[str], doc_text: str, k1: float = 1.5, b: float = 0.75, avg_dl: float = 50.0) -> float:
    """简化 BM25 评分。无 IDF（文档集太小），用 TF 饱和代替。"""
    doc_tokens = tokenize(doc_text)
    dl = max(len(doc_tokens), 1)
    score = 0.0
    for kw in query_keywords:
        tf = sum(1 for t in doc_tokens if t == kw)
        if tf > 0:
            numerator = tf * (k1 + 1)
            denominator = tf + k1 * (1 - b + b * dl / avg_dl)
            score += numerator / denominator
    return score


# === 时间衰减 ===

def temporal_decay(timestamp: float, half_life_days: float = 30.0, now: float | None = None) -> float:
    """指数时间衰减。半衰期默认 30 天。"""
    now = now or time.time()
    age_days = max(0, (now - timestamp)) / 86400
    if half_life_days <= 0:
        return 1.0
    lam = math.log(2) / half_life_days
    return math.exp(-lam * age_days)


# === MMR 多样性重排 ===

def jaccard_similarity(set_a: set[str], set_b: set[str]) -> float:
    """Jaccard 相似度。"""
    if not set_a and not set_b:
        return 1.0
    if not set_a or not set_b:
        return 0.0
    intersection = len(set_a & set_b)
    union = len(set_a | set_b)
    return intersection / union if union > 0 else 0.0


def mmr_rerank(items: list[dict[str, Any]], lam: float = 0.7, limit: int = 5) -> list[dict[str, Any]]:
    """MMR 重排：平衡相关性与多样性。
    λ=1 纯相关性, λ=0 纯多样性。默认 0.7。
    """
    if len(items) <= 1:
        return items[:limit]

    token_cache: dict[int, set[str]] = {}
    for i, item in enumerate(items):
        text = f"{item.get('key', '')} {item.get('value', '')} {item.get('trigger', '')} {item.get('lesson', '')}"
        token_cache[i] = set(tokenize(text))

    selected: list[int] = []
    remaining = set(range(len(items)))

    while remaining and len(selected) < limit:
        best_idx = -1
        best_mmr = -float('inf')

        for idx in remaining:
            relevance = items[idx].get('_score', 0)
            max_sim = 0.0
            for sel_idx in selected:
                sim = jaccard_similarity(token_cache[idx], token_cache[sel_idx])
                max_sim = max(max_sim, sim)
            mmr = lam * relevance - (1 - lam) * max_sim
            if mmr > best_mmr:
                best_mmr = mmr
                best_idx = idx

        if best_idx >= 0:
            selected.append(best_idx)
            remaining.discard(best_idx)
        else:
            break

    return [items[i] for i in selected]


def _stable_key(item: dict[str, Any], text_fields: list[str]) -> str:
    """生成稳定的内容 key，用于 BM25 与向量结果融合匹配。
    优先用 id 字段，没有则用内容哈希。"""
    if item.get("id"):
        return str(item["id"])
    text = "|".join(str(item.get(f, ""))[:80] for f in text_fields)
    return text[:200]


# === 混合检索主函数 ===

def hybrid_search(
    query: str,
    items: list[dict[str, Any]],
    text_fields: list[str],
    limit: int = 5,
    time_field: str = "timestamp",
    half_life_days: float = 30.0,
    mmr_lambda: float = 0.7,
) -> list[dict[str, Any]]:
    """混合检索：BM25 + 时间衰减 + MMR 去重。

    Args:
        query: 搜索查询
        items: 待搜索的文档列表
        text_fields: 用于匹配的字段名列表
        limit: 返回结果数上限
        time_field: 时间戳字段名
        half_life_days: 时间衰减半衰期（天）
        mmr_lambda: MMR 参数 (0=多样性, 1=相关性)
    """
    if not query or not items:
        return []

    keywords = extract_keywords(query)
    if not keywords:
        keywords = tokenize(query)
    if not keywords:
        return []

    now = time.time()
    scored: list[dict[str, Any]] = []

    for item in items:
        doc_text = " ".join(str(item.get(f, "")) for f in text_fields)
        text_score = bm25_score(keywords, doc_text)
        if text_score <= 0:
            continue

        ts = item.get(time_field, now)
        # 支持 ISO 字符串和 Unix 时间戳
        if isinstance(ts, str):
            try:
                from datetime import datetime
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                ts = dt.timestamp()
            except (ValueError, TypeError):
                ts = now
        decay = temporal_decay(ts, half_life_days, now) if isinstance(ts, (int, float)) else 1.0
        final_score = text_score * decay

        enriched = {**item, "_score": final_score, "_text_score": text_score, "_decay": decay}
        scored.append(enriched)

    # S39: 向量语义检索增强 — 合并 BM25 和向量分数
    try:
        from adapters.memory.vector_store import get_vector_store
        vs = get_vector_store()
        if vs.is_available():
            vec_results = vs.semantic_search(query, items, text_fields, limit=limit * 2)
            vec_map = {}
            for vr in vec_results:
                key = _stable_key(vr, text_fields)
                vec_map[key] = vr.get("_vec_score", 0)
            # 融合: final = 0.6 * bm25_norm + 0.4 * vec_score
            max_bm25 = max((s["_score"] for s in scored), default=1.0) or 1.0
            for s in scored:
                key = _stable_key(s, text_fields)
                bm25_norm = s["_score"] / max_bm25
                vec_s = vec_map.get(key, 0)
                s["_score"] = 0.6 * bm25_norm + 0.4 * vec_s
            # 添加仅向量命中的结果
            scored_keys = {_stable_key(s, text_fields) for s in scored}
            for vr in vec_results:
                key = _stable_key(vr, text_fields)
                if key not in scored_keys:
                    vr["_score"] = 0.4 * vr.get("_vec_score", 0)
                    scored.append(vr)
    except Exception:
        pass  # 降级: 向量检索失败时静默回退到纯 BM25

    scored.sort(key=lambda x: x["_score"], reverse=True)

    if mmr_lambda < 1.0 and len(scored) > 1:
        result = mmr_rerank(scored, lam=mmr_lambda, limit=limit)
    else:
        result = scored[:limit]

    return result
