"""LucidMind CLI — 命令行交互入口。

用法: python cli.py
"""

import asyncio
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# 加载环境变量
load_dotenv(Path(__file__).parent / ".env")

from brain import Brain
from adapters.llm.deepseek import DeepSeekAdapter
from adapters.stream.cli_stream import CLIStreamAdapter
from adapters.tools.shell import ShellAdapter
from adapters.tools.file import FileAdapter
from adapters.tools.web_search import WebSearchAdapter
from adapters.tools.search_files import SearchFilesAdapter
from adapters.tools.composite import CompositeToolAdapter
from adapters.memory.json_memory import JSONMemoryAdapter
from adapters.learning.json_lessons import JSONLessonsAdapter


def main():
    print("=" * 50)
    print("  LucidMind CLI v1.0")
    print("  透明思维的 AI Agent")
    print("  输入 /quit 退出, /think 切换思考显示")
    print("=" * 50)

    # 初始化组件
    llm = DeepSeekAdapter()
    stream = CLIStreamAdapter(show_thinking=True)
    tools = CompositeToolAdapter([
        ShellAdapter(),
        FileAdapter(),
        WebSearchAdapter(),
        SearchFilesAdapter(),
    ])
    memory = JSONMemoryAdapter()
    learning = JSONLessonsAdapter()

    brain = Brain(
        llm=llm,
        stream=stream,
        tools=tools,
        memory=memory,
        learning=learning,
    )

    session_id = "cli_session"
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    while True:
        try:
            user_input = input("\n🧑 你: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见！")
            break

        if not user_input:
            continue
        if user_input == "/quit":
            print("再见！")
            break
        if user_input == "/think":
            stream._show_thinking = not stream._show_thinking
            status = "开启" if stream._show_thinking else "关闭"
            print(f"思考显示已{status}")
            continue

        loop.run_until_complete(brain.process(session_id, user_input))


if __name__ == "__main__":
    main()
