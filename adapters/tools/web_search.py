"""Web Search Tool Adapter — 多引擎网络搜索 + 自动 Fallback。

搜索引擎优先级（全部免费，无需 API Key）：
1. DuckDuckGo (ddgs) — 首选，速度快
2. Google (googlesearch-python) — DDG 不可用时自动切换
3. Brave HTML — 直接抓取 Brave 搜索页面
4. SearXNG — 自建元搜索引擎（如已部署）

每个引擎独立超时，失败自动切换下一个，总超时受 asyncio 控制。
"""

import asyncio
import functools
import os
import re
import time
from typing import Any
from urllib.parse import quote_plus

from ports.tool_port import ToolPort
from logs import get_logger

logger = get_logger("tools")

_MAX_RESULTS = 10

# 引擎健康状态追踪（运行时）
_engine_health: dict[str, dict] = {}
_ENGINE_COOLDOWN = 120  # 连续失败后冷却时间（秒）


def _format_results(raw: list[dict], source: str) -> dict[str, Any]:
    """统一格式化搜索结果。"""
    if not raw:
        return {"success": True, "result": "未找到相关结果", "error": None}
    lines = []
    for i, r in enumerate(raw, 1):
        title = r.get("title", "无标题")
        url = r.get("url", r.get("href", r.get("link", "")))
        body = r.get("body", r.get("snippet", r.get("description", "")))
        if len(body) > 200:
            body = body[:200] + "..."
        lines.append(f"{i}. {title}\n   {url}\n   {body}")
    result_text = "\n\n".join(lines)
    logger.info(f"[{source}] 搜索完成: {len(raw)}条结果")
    return {"success": True, "result": result_text, "error": None}


def _is_engine_cooling(name: str) -> bool:
    """检查引擎是否在冷却期。"""
    h = _engine_health.get(name, {})
    if h.get("failures", 0) >= 2:
        if time.time() - h.get("last_fail", 0) < _ENGINE_COOLDOWN:
            return True
        h["failures"] = 0  # 冷却结束，重置
    return False


def _mark_engine_fail(name: str):
    h = _engine_health.setdefault(name, {"failures": 0, "last_fail": 0})
    h["failures"] += 1
    h["last_fail"] = time.time()


def _mark_engine_ok(name: str):
    _engine_health[name] = {"failures": 0, "last_fail": 0}


# ── 引擎 1: DuckDuckGo ───────────────────────────────

def _search_ddg(query: str, max_results: int) -> list[dict]:
    """DuckDuckGo 搜索（同步）。"""
    try:
        from ddgs import DDGS
    except ImportError:
        try:
            from duckduckgo_search import DDGS
        except ImportError:
            raise ImportError("ddgs not installed")

    with DDGS(timeout=10) as ddgs:
        results = ddgs.text(query, max_results=max_results)
    return [{"title": r.get("title", ""), "url": r.get("href", r.get("link", "")),
             "body": r.get("body", r.get("snippet", ""))} for r in (results or [])]


# ── 引擎 2: Google (googlesearch-python) ─────────────

def _search_google(query: str, max_results: int) -> list[dict]:
    """Google 搜索 via googlesearch-python（同步，无需 API Key）。"""
    try:
        from googlesearch import search as gsearch
    except ImportError:
        raise ImportError("googlesearch-python not installed")

    results = []
    for url in gsearch(query, num_results=max_results, lang="zh-CN", sleep_interval=0):
        results.append({"title": url.split("/")[-1] or url, "url": url, "body": ""})
        if len(results) >= max_results:
            break
    return results


# ── 引擎 3: Brave HTML 抓取 ──────────────────────────

def _search_brave(query: str, max_results: int) -> list[dict]:
    """Brave Search HTML 抓取（同步，无需 API Key）。"""
    import httpx

    url = f"https://search.brave.com/search?q={quote_plus(query)}&source=web"
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }
    resp = httpx.get(url, headers=headers, timeout=10, follow_redirects=True)
    resp.raise_for_status()
    html = resp.text

    results = []
    # 解析 Brave 搜索结果（简单正则，不依赖 BeautifulSoup）
    # Brave 的结果在 <div class="snippet ..."> 块中
    snippets = re.findall(
        r'<a[^>]*href="(https?://[^"]+)"[^>]*>\s*<span[^>]*>([^<]*)</span>',
        html
    )
    for href, title in snippets[:max_results]:
        if "brave.com" in href or not title.strip():
            continue
        results.append({"title": title.strip(), "url": href, "body": ""})

    # 备用解析：寻找 data-pos 标记的结果
    if not results:
        blocks = re.findall(r'<a[^>]*class="[^"]*result-header[^"]*"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', html, re.DOTALL)
        for href, title_html in blocks[:max_results]:
            title = re.sub(r'<[^>]+>', '', title_html).strip()
            if title and "brave.com" not in href:
                results.append({"title": title, "url": href, "body": ""})

    return results


# ── 引擎 4: SearXNG ──────────────────────────────────

def _search_searxng(query: str, max_results: int) -> list[dict]:
    """SearXNG 元搜索引擎（同步）。需要部署 SearXNG 实例。"""
    import httpx

    base = os.getenv("SEARXNG_URL", "").rstrip("/")
    if not base:
        raise RuntimeError("SEARXNG_URL not set")

    resp = httpx.get(
        f"{base}/search",
        params={"q": query, "format": "json", "categories": "general", "language": "zh-CN"},
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    results = []
    for r in data.get("results", [])[:max_results]:
        results.append({
            "title": r.get("title", ""),
            "url": r.get("url", ""),
            "body": r.get("content", ""),
        })
    return results


# ── 引擎注册表 ───────────────────────────────────────

_ENGINES = [
    ("DuckDuckGo", _search_ddg),
    ("Google", _search_google),
    ("Brave", _search_brave),
    ("SearXNG", _search_searxng),
]


class WebSearchAdapter(ToolPort):
    """多引擎网络搜索适配器 — 自动 Fallback，全部免费无需 API Key。"""

    def __init__(self, max_results: int = 5, timeout: int = 15):
        self.default_max_results = max_results
        self.timeout = timeout
        engines = [name for name, _ in _ENGINES]
        logger.info(f"初始化: 引擎={engines}, 默认结果数={max_results}, 超时={timeout}s")

    def list_tools(self) -> list[dict[str, Any]]:
        """返回 LLM 可用的搜索工具定义。"""
        return [
            {
                "type": "function",
                "function": {
                    "name": "web_search",
                    "description": "搜索网页。用于查找最新信息、验证事实、查阅文档等。支持多引擎自动切换。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "搜索关键词",
                            },
                            "max_results": {
                                "type": "integer",
                                "description": "最大结果数（1-10，默认5）",
                            },
                        },
                        "required": ["query"],
                    },
                },
            },
        ]

    async def execute(self, tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
        """执行搜索工具。"""
        if tool_name == "web_search":
            return await self._web_search(
                params.get("query", ""),
                params.get("max_results", self.default_max_results),
            )
        return {"success": False, "result": None, "error": f"未知工具: {tool_name}"}

    async def _web_search(self, query: str, max_results: int) -> dict[str, Any]:
        """多引擎搜索 + 自动 Fallback。"""
        if not query.strip():
            return {"success": False, "result": None, "error": "搜索词为空"}

        max_results = min(max(1, max_results), _MAX_RESULTS)
        logger.info(f"搜索: '{query}', 最多{max_results}条")

        errors = []
        for engine_name, engine_fn in _ENGINES:
            if _is_engine_cooling(engine_name):
                logger.debug(f"[{engine_name}] 冷却中，跳过")
                errors.append(f"{engine_name}: 冷却中")
                continue

            try:
                loop = asyncio.get_event_loop()
                raw = await asyncio.wait_for(
                    loop.run_in_executor(
                        None,
                        functools.partial(engine_fn, query, max_results),
                    ),
                    timeout=self.timeout,
                )
                if raw:
                    _mark_engine_ok(engine_name)
                    result = _format_results(raw, engine_name)
                    result["engine"] = engine_name
                    return result
                else:
                    logger.info(f"[{engine_name}] 无结果，尝试下一个引擎")
                    errors.append(f"{engine_name}: 无结果")

            except asyncio.TimeoutError:
                _mark_engine_fail(engine_name)
                logger.warning(f"[{engine_name}] 超时({self.timeout}s)")
                errors.append(f"{engine_name}: 超时")
            except ImportError as e:
                logger.debug(f"[{engine_name}] 未安装: {e}")
                errors.append(f"{engine_name}: 未安装")
            except Exception as e:
                _mark_engine_fail(engine_name)
                logger.warning(f"[{engine_name}] 失败: {type(e).__name__}: {e}")
                errors.append(f"{engine_name}: {e}")

        err_summary = " | ".join(errors)
        logger.error(f"所有搜索引擎均失败: {err_summary}")
        return {
            "success": False,
            "result": None,
            "error": f"所有搜索引擎均失败: {err_summary}",
        }
