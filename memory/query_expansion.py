"""Query Expansion — 查询扩展（对标 OpenClaw query-expansion.ts）。

改善中文搜索质量:
1. 可选 jieba 分词（无则回退到 n-gram）
2. CJK bigram/trigram 扩展
3. 同义词/近义词扩展
4. 停用词过滤
5. 会话式查询 → 关键词提取
"""

import re
from typing import Callable

from logs import get_logger

logger = get_logger("memory.query_expansion")

# ── 停用词 ──

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
    "之前 以前 之后 以后 现在 请 帮 告诉 东西 事情 事 一个 一些 很 非常 比较".split()
)

# ── 同义词映射（高频查询场景） ──

_SYNONYMS: dict[str, list[str]] = {
    "bug": ["错误", "问题", "缺陷", "故障"],
    "错误": ["bug", "问题", "缺陷"],
    "问题": ["bug", "错误", "issue"],
    "配置": ["设置", "config", "设定"],
    "设置": ["配置", "config"],
    "偏好": ["喜好", "偏爱", "习惯"],
    "项目": ["工程", "project"],
    "部署": ["发布", "deploy", "上线"],
    "测试": ["test", "验证", "检测"],
    "记忆": ["memory", "记录", "记住"],
    "学习": ["learn", "训练", "掌握"],
    "工具": ["tool", "插件", "plugin"],
    "文件": ["file", "文档", "document"],
    "搜索": ["search", "查找", "检索", "查询"],
    "用户": ["user", "使用者"],
    "密码": ["password", "口令", "密钥"],
    "数据库": ["database", "db", "存储"],
    "接口": ["api", "interface", "端口"],
    "性能": ["performance", "速度", "效率"],
    "安全": ["security", "安全性", "防护"],
}

# ── jieba 分词（可选） ──

_jieba_cut: Callable | None = None

def _get_jieba():
    """延迟加载 jieba，不可用时返回 None。"""
    global _jieba_cut
    if _jieba_cut is not None:
        return _jieba_cut
    try:
        import jieba
        jieba.setLogLevel(20)  # 抑制 jieba 日志
        _jieba_cut = jieba.lcut
        logger.info("jieba 分词已加载")
        return _jieba_cut
    except ImportError:
        logger.debug("jieba 未安装，使用 n-gram 回退分词")
        return None


def _is_cjk(char: str) -> bool:
    """判断是否为 CJK 字符。"""
    return '\u4e00' <= char <= '\u9fff'


def _ngram_tokenize(text: str) -> list[str]:
    """CJK n-gram 分词（jieba 不可用时的回退）。

    - CJK 段输出 bigram+trigram（单字是噪声关键词，且 trigram FTS 索引
      匹配不到 <3 字的查询词）
    - 中英混排段中的 ASCII 单词单独提取，不能整段丢弃
    """
    tokens: list[str] = []
    segments = re.split(r'[\s\.,;:!?\-\(\)\[\]{}"\'`~@#$%^&*+=|\\/<>，。！？；：、""''（）【】]+', text.lower())
    for seg in segments:
        if not seg:
            continue
        cjk_chars = [c for c in seg if _is_cjk(c)]
        if cjk_chars:
            # bigram
            for i in range(len(cjk_chars) - 1):
                tokens.append(cjk_chars[i] + cjk_chars[i + 1])
            # trigram (for better phrase matching)
            for i in range(len(cjk_chars) - 2):
                tokens.append(cjk_chars[i] + cjk_chars[i + 1] + cjk_chars[i + 2])
            # 段落太短（只有一个 CJK 字）时保留 unigram，否则什么都不剩
            if len(cjk_chars) == 1:
                tokens.append(cjk_chars[0])
        # 混排/纯英文段中的 ASCII 单词（"什么python框架" → "python"）
        for ascii_word in re.findall(r"[a-z0-9][a-z0-9_\-]*", seg):
            if len(ascii_word) >= 2 or ascii_word.isdigit():
                tokens.append(ascii_word)
    return tokens


def segment(text: str) -> list[str]:
    """智能分词: 优先 jieba，回退 n-gram。"""
    cut = _get_jieba()
    if cut:
        words = cut(text)
        # jieba 结果 + 额外 bigram（补充短词组合）
        result = [w.strip().lower() for w in words if w.strip() and len(w.strip()) >= 1]
        # 对纯 CJK 词追加 bigram
        cjk_words = [w for w in result if any(_is_cjk(c) for c in w)]
        if len(cjk_words) >= 2:
            for i in range(len(cjk_words) - 1):
                combo = cjk_words[i] + cjk_words[i + 1]
                if combo not in result:
                    result.append(combo)
        return result
    return _ngram_tokenize(text)


def expand_query(query: str, max_expansions: int = 5) -> list[str]:
    """扩展查询: 分词 + 停用词过滤 + 同义词。

    Args:
        query: 原始查询文本
        max_expansions: 最大同义词扩展数

    Returns:
        扩展后的关键词列表（去重，保序）
    """
    if not query or not query.strip():
        return []

    # 1. 分词
    tokens = segment(query)

    # 2. 停用词过滤
    filtered: list[str] = []
    seen: set[str] = set()
    for t in tokens:
        t_lower = t.lower()
        if t_lower in _STOP_EN or t_lower in _STOP_ZH or t_lower in seen:
            continue
        if len(t_lower) < 1:
            continue
        seen.add(t_lower)
        filtered.append(t_lower)

    # 3. 同义词扩展
    expansions: list[str] = []
    expansion_count = 0
    for term in filtered:
        syns = _SYNONYMS.get(term, [])
        for syn in syns:
            syn_lower = syn.lower()
            if syn_lower not in seen and expansion_count < max_expansions:
                seen.add(syn_lower)
                expansions.append(syn_lower)
                expansion_count += 1

    result = filtered + expansions
    return result


def build_fts5_query(query: str) -> str:
    """将用户查询转换为增强的 FTS5 查询语法。

    比原始 _fts5_query() 更强:
    - 分词后用 OR 连接
    - 加入同义词扩展
    - 对 CJK 文本用双引号包裹确保子串匹配
    """
    expanded = expand_query(query)
    if not expanded:
        # 回退到原始查询
        cleaned = re.sub(r'[^\w\s]', ' ', query)
        terms = [t.strip() for t in cleaned.split() if t.strip()]
        if not terms:
            return query
        return " OR ".join(f'"{t}"' for t in terms)

    return " OR ".join(f'"{t}"' for t in expanded)


def extract_search_keywords(query: str) -> list[str]:
    """从会话式查询中提取搜索关键词。

    例: "之前我们讨论过什么Python框架？" → ["讨论", "python", "框架"]
    """
    return expand_query(query, max_expansions=3)
