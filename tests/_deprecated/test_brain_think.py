"""让 Brain 自己分析 SpecialKB 智能路由问题 — 真实浏览器操作。"""
import sys
import time
from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding="utf-8")

BASE_URL = "http://127.0.0.1:8765"
TIMEOUT = 120_000

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        page.goto(BASE_URL)
        page.wait_for_selector("#status-indicator.online", timeout=15_000)
        print("[Brain] 浏览器已打开，WebSocket 已连接\n")

        prompt = (
            "我有一个架构问题想听听你的想法：\n"
            "外部大模型（如DeepSeek）调用费token，本地大模型（如qwen3:8b）回复慢但免费。\n"
            "我的方案是：外部模型回答过的问题，记录到一个'特别行为数据库'，"
            "下次同类问题由本地模型+缓存的优质回答来回答，省token又快。\n"
            "但有个关键问题：动态问题（今天天气、股票价格、最新新闻）不能缓存，"
            "而且不能用关键词模板来判断，要让大脑自己能分辨。\n"
            "请分析：1）这个方案的优缺点 2）你觉得怎么判断一个问题是否适合缓存？"
            "3）还有什么改进建议？"
        )

        # 在输入框打字并发送
        page.fill("#user-input", prompt)
        page.click("#send-btn")
        print("[Brain] 已在浏览器输入并点击发送")
        print(f"[Brain] 问题: {prompt[:80]}...\n")

        # 等待回复
        page.wait_for_selector("#messages .message.assistant", timeout=TIMEOUT)
        
        # 等一会让回复完全渲染
        time.sleep(3)
        
        reply = page.inner_text("#messages .message.assistant")
        print("=" * 60)
        print("Brain 的回答:")
        print("=" * 60)
        print(reply)
        print("=" * 60)
        print(f"\n回复长度: {len(reply)} 字符")

        # 检查是否有思考过程
        thinking_boxes = page.query_selector_all("#messages .thinking-box")
        if thinking_boxes:
            thinking = thinking_boxes[0].inner_text()
            print(f"\n思考过程 ({len(thinking)} 字符):")
            print(thinking[:500])

        browser.close()
        print("\n[Brain] 测试完成")

if __name__ == "__main__":
    main()
