"""Web Search Tool Adapter — 网络搜索。

对标 OpenAkita web.py + handlers/web_search.py + definitions/web_search.py (共549行)。
我们的优势: 单文件 + ToolPort 接口 + 结果截断 + 更简洁。
"""

import asyncio
import functools
from typing import Any

from ports.tool_port import ToolPort
from logs import get_logger

logger = get_logger("tools")

# 搜索结果上限
_MAX_RESULTS = 10


class WebSearchAdapter(ToolPort):
    """网络搜索工具适配器。使用 DuckDuckGo 搜索。"""

    def __init__(self, max_results: int = 5, timeout: int = 30):
        self.default_max_results = max_results
        self.timeout = timeout
        logger.info(f"初始化: 默认结果数={max_results}, 超时={timeout}s")

    def list_tools(self) -> list[dict[str, Any]]:
        """返回 LLM 可用的搜索工具定义。"""
        return [
            {
                "type": "function",
                "function": {
                    "name": "web_search",
                    "description": "使用 DuckDuckGo 搜索网页。用于查找最新信息、验证事实、查阅文档等。",
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
        """执行网页搜索。"""
        if not query.strip():
            return {"success": False, "result": None, "error": "搜索词为空"}

        max_results = min(max(1, max_results), _MAX_RESULTS)
        logger.info(f"搜索: '{query}', 最多{max_results}条")

        try:
            loop = asyncio.get_event_loop()
            result = await asyncio.wait_for(
                loop.run_in_executor(
                    None,
                    functools.partial(self._sync_search, query, max_results),
                ),
                timeout=self.timeout,
            )
            return result

        except asyncio.TimeoutError:
            logger.error(f"搜索超时: {self.timeout}s")
            return {
                "success": False,
                "result": None,
                "error": f"搜索超时 ({self.timeout}秒)",
            }
        except Exception as e:
            logger.error(f"搜索失败: {type(e).__name__}: {e}", exc_info=True)
            return {
                "success": False,
                "result": None,
                "error": f"{type(e).__name__}: {e}",
            }

    def _sync_search(self, query: str, max_results: int) -> dict[str, Any]:
        """同步执行搜索（在线程池中调用）。"""
        try:
            from ddgs import DDGS
        except ImportError:
            try:
                from duckduckgo_search import DDGS
            except ImportError:
                return {
                    "success": False,
                    "result": None,
                    "error": "缺少依赖: pip install ddgs",
                }

        with DDGS() as ddgs:
            raw_results = ddgs.text(query, max_results=max_results)

        if not raw_results:
            logger.info(f"搜索无结果: '{query}'")
            return {"success": True, "result": "未找到相关结果", "error": None}

        # 格式化结果
        lines = []
        for i, r in enumerate(raw_results, 1):
            title = r.get("title", "无标题")
            url = r.get("href", r.get("link", ""))
            body = r.get("body", r.get("snippet", ""))
            # 截断过长摘要
            if len(body) > 200:
                body = body[:200] + "..."
            lines.append(f"{i}. {title}\n   {url}\n   {body}")

        result_text = "\n\n".join(lines)
        logger.info(f"搜索完成: '{query}', {len(raw_results)}条结果")
        return {"success": True, "result": result_text, "error": None}
