"""Browser Tool Adapter — 浏览器自动化（Playwright）。

新 Adapter，不修改 brain.py（规则 06）。
提供：打开网页、截图、提取文本。
"""

import asyncio
from pathlib import Path
from typing import Any

from ports.tool_port import ToolPort
from logs import get_logger

logger = get_logger("tools.browser")

_SCREENSHOT_DIR = Path(__file__).parent.parent.parent / "data" / "screenshots"
_SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)


class BrowserToolAdapter(ToolPort):
    """浏览器工具：打开网页、截图、提取文本。"""

    def list_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "browse_url",
                    "description": "打开网页并提取文本内容，可选截图。url 是目标网址，screenshot 为 true 时保存截图。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "url": {"type": "string", "description": "要访问的网址"},
                            "screenshot": {"type": "boolean", "description": "是否截图"},
                        },
                        "required": ["url"],
                    },
                },
            },
        ]

    async def execute(self, tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
        if tool_name != "browse_url":
            return {"success": False, "error": f"Unknown tool: {tool_name}"}
        url = params.get("url", "")
        if not url:
            return {"success": False, "error": "URL is required"}
        take_screenshot = params.get("screenshot", False)

        try:
            from playwright.async_api import async_playwright

            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                await page.goto(url, timeout=15000, wait_until="domcontentloaded")

                title = await page.title()
                # 提取可见文本（限制长度防止撑爆上下文）
                text = await page.inner_text("body")
                text = text.strip()[:3000]

                screenshot_path = None
                if take_screenshot:
                    fname = url.replace("://", "_").replace("/", "_")[:40] + ".png"
                    screenshot_path = str(_SCREENSHOT_DIR / fname)
                    await page.screenshot(path=screenshot_path)

                await browser.close()

            result = f"标题: {title}\n\n内容摘要:\n{text}"
            if screenshot_path:
                result += f"\n\n截图已保存: {screenshot_path}"

            logger.info(f"浏览器访问: {url} — title={title}, text={len(text)} chars")
            return {"success": True, "result": result}

        except Exception as e:
            logger.error(f"浏览器工具失败: {url} — {e}")
            return {"success": False, "error": str(e)}
