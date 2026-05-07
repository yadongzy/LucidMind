"""Deep Research Tool — 深度研究能力。

让大脑具备系统性的网络研究能力，不是简单搜索，而是：
1. 分析问题 → 拆解为多个搜索方向
2. 并行搜索多个关键词
3. 读取关键文献内容
4. 对比分析 → 综合结论

参考 Cascade 的研究思考过程（图片中展示的）：
- "两条线并行：搜索网络文献 + 分析对标项目代码"
- "先深入读关键文献和核心代码"
- "非常关键的发现。让我继续深入"

不修改 brain.py（规则06）。作为独立工具注册到 CompositeToolAdapter。
"""

import asyncio
import functools
import urllib.request
import urllib.error
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from ports.tool_port import ToolPort
from logs import get_logger

logger = get_logger("research")

_pool = ThreadPoolExecutor(max_workers=3)


class DeepResearchAdapter(ToolPort):
    """深度研究工具 — 系统性网络研究+分析+综合。"""

    async def execute(self, tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
        if tool_name != "deep_research":
            return {"success": False, "result": None, "error": f"Unknown tool: {tool_name}"}
        topic = params.get("topic", "")
        if not topic.strip():
            return {"success": False, "result": None, "error": "topic不能为空"}
        action = params.get("action", "research")
        try:
            loop = asyncio.get_event_loop()
            if action == "search_multi":
                queries = params.get("queries", [topic])
                result = await loop.run_in_executor(_pool, functools.partial(_multi_search, queries))
            elif action == "read_url":
                url = params.get("url", "")
                result = await loop.run_in_executor(_pool, functools.partial(_read_url, url))
            elif action == "analyze":
                data = params.get("data", "")
                question = params.get("question", topic)
                result = _analyze_data(data, question)
            else:  # research = 完整研究流程
                result = await loop.run_in_executor(_pool, functools.partial(_full_research, topic))
            return {"success": True, "result": result}
        except Exception as e:
            return {"success": False, "result": None, "error": str(e)[:300]}

    def list_tools(self) -> list[dict[str, Any]]:
        return [{"type": "function", "function": {
            "name": "deep_research",
            "description": (
                "深度研究工具。系统性地搜索网络、读取文献、分析数据、综合结论。"
                "用于需要严谨分析的问题，不是简单搜索。"
                "研究方法论：1.拆解问题为多个搜索方向 2.并行搜索 3.读取关键文献 4.对比分析 5.综合结论"
            ),
            "parameters": {"type": "object", "properties": {
                "topic": {"type": "string", "description": "研究主题或问题"},
                "action": {"type": "string",
                           "enum": ["research", "search_multi", "read_url", "analyze"],
                           "description": "research=完整研究, search_multi=多方向搜索, read_url=读取网页, analyze=分析数据"},
                "queries": {"type": "array", "items": {"type": "string"},
                            "description": "search_multi时的多个搜索词"},
                "url": {"type": "string", "description": "read_url时的网页地址"},
                "data": {"type": "string", "description": "analyze时的待分析数据"},
                "question": {"type": "string", "description": "analyze时的分析问题"},
            }, "required": ["topic"]}
        }}]


def _ddgs_search(query: str, max_results: int = 5) -> list[dict]:
    """DuckDuckGo搜索（复用现有依赖）。"""
    try:
        from ddgs import DDGS
    except ImportError:
        try:
            from duckduckgo_search import DDGS
        except ImportError:
            return []
    try:
        with DDGS() as ddgs:
            return list(ddgs.text(query, max_results=max_results))
    except Exception as e:
        logger.warning(f"搜索失败 '{query}': {e}")
        return []


def _multi_search(queries: list[str]) -> str:
    """并行搜索多个关键词，合并结果。"""
    all_results = []
    for q in queries[:5]:  # 最多5个方向
        results = _ddgs_search(q, max_results=3)
        if results:
            all_results.append({"query": q, "results": results})
    if not all_results:
        return "所有搜索方向均无结果"
    lines = []
    for group in all_results:
        lines.append(f"\n### 搜索方向: {group['query']}")
        for i, r in enumerate(group["results"], 1):
            title = r.get("title", "")
            url = r.get("href", r.get("link", ""))
            body = r.get("body", r.get("snippet", ""))[:200]
            lines.append(f"  {i}. {title}\n     {url}\n     {body}")
    return "\n".join(lines)


def _read_url(url: str) -> str:
    """读取网页内容（纯文本提取）。"""
    if not url:
        return "URL为空"
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (LucidMind Research Bot)",
            "Accept": "text/html,application/xhtml+xml",
        })
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read()
            # 尝试多种编码
            for enc in ["utf-8", "gbk", "gb2312", "latin-1"]:
                try:
                    html = raw.decode(enc)
                    break
                except (UnicodeDecodeError, LookupError):
                    continue
            else:
                html = raw.decode("utf-8", errors="replace")
        # 提取纯文本
        text = _html_to_text(html)
        if len(text) > 3000:
            text = text[:3000] + "\n\n[... 内容已截断，共约{}字 ...]".format(len(text))
        return text if text.strip() else "页面无可提取文本内容"
    except Exception as e:
        return f"读取失败: {e}"


def _html_to_text(html: str) -> str:
    """简单HTML转纯文本。"""
    html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r'<[^>]+>', ' ', html)
    html = re.sub(r'\s+', ' ', html)
    # 解码HTML实体
    html = html.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
    html = html.replace('&quot;', '"').replace('&#39;', "'").replace('&nbsp;', ' ')
    return html.strip()


def _analyze_data(data: str, question: str) -> str:
    """结构化分析数据（不调用LLM，纯规则提取）。"""
    lines = data.split("\n")
    stats = {
        "total_lines": len(lines),
        "non_empty": sum(1 for l in lines if l.strip()),
        "urls": len(re.findall(r'https?://\S+', data)),
        "numbers": len(re.findall(r'\d+\.?\d*%?', data)),
    }
    return (
        f"数据分析:\n"
        f"- 总行数: {stats['total_lines']}, 非空行: {stats['non_empty']}\n"
        f"- URL数: {stats['urls']}, 数字数据: {stats['numbers']}\n"
        f"- 问题: {question}\n"
        f"- 建议: 请结合以上数据和你的经验来回答问题。"
    )


def _full_research(topic: str) -> str:
    """完整研究流程：拆解→搜索→读取→综合。"""
    logger.info(f"开始深度研究: {topic}")
    # 1. 拆解为多个搜索方向
    queries = _decompose_topic(topic)
    logger.info(f"研究方向: {queries}")
    # 2. 并行搜索
    search_results = _multi_search(queries)
    # 3. 提取最相关的URL并读取
    urls = re.findall(r'https?://\S+', search_results)
    read_contents = []
    for url in urls[:2]:  # 最多读2个页面
        url = url.rstrip(')')  # 清理URL末尾
        content = _read_url(url)
        if content and "读取失败" not in content and len(content) > 100:
            read_contents.append(f"\n--- 来源: {url} ---\n{content[:800]}")
    # 4. 综合报告
    report = [
        f"# 深度研究报告: {topic}\n",
        "## 搜索结果",
        search_results,
    ]
    if read_contents:
        report.append("\n## 关键文献内容")
        report.extend(read_contents)
    report.append(
        "\n## 研究方法论提醒\n"
        "以上是搜索和文献数据。请你：\n"
        "1. 对比不同来源的观点\n"
        "2. 找出共识和分歧\n"
        "3. 结合LucidMind的实际情况给出建议\n"
        "4. 标注不确定的部分，不要编造"
    )
    result = "\n".join(report)
    # 防止返回内容过长导致LLM 400错误
    if len(result) > 2000:
        result = result[:2000] + "\n\n[... 内容已截断以适应模型上下文限制 ...]"
    logger.info(f"深度研究完成: {topic}, 结果长度={len(result)}")
    return result


def _decompose_topic(topic: str) -> list[str]:
    """将研究主题拆解为多个搜索方向。"""
    queries = [topic]
    # 添加学术方向
    if any(kw in topic for kw in ["AI", "agent", "模型", "算法", "架构", "memory", "记忆"]):
        queries.append(f"{topic} research paper 2024 2025")
    # 添加实践方向
    if any(kw in topic for kw in ["优化", "实现", "方案", "最佳实践", "best practice"]):
        queries.append(f"{topic} implementation guide")
    # 添加对比方向
    if any(kw in topic for kw in ["对比", "比较", "vs", "选择"]):
        queries.append(f"{topic} comparison benchmark")
    # 确保至少2个方向
    if len(queries) < 2:
        queries.append(f"{topic} best practices")
    return queries[:4]
