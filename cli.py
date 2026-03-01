"""LucidMind CLI — 命令行入口。

用法:
  lucidmind start              启动 Web 服务
  lucidmind chat               CLI 交互模式
  lucidmind create-plugin NAME 创建插件模板
"""

import argparse
import json
import os
import sys
from pathlib import Path
from string import Template


_ROOT = Path(__file__).parent
_SKILLS_DIR = _ROOT / "skills"


# --- create-plugin 子命令 ---

_MANIFEST_TEMPLATE = Template("""{
  "name": "$name",
  "version": "1.0.0",
  "description": "$description",
  "author": "$author",
  "entry": "main.py",
  "tools": ["${name}_run"],
  "platform": [],
  "dependencies": [],
  "enabled": true
}
""")

_MAIN_TEMPLATE = Template('''"""$name — $description"""

import json
from typing import Any


def get_tools() -> list[dict]:
    """返回此插件提供的工具定义列表。"""
    return [
        {
            "type": "function",
            "function": {
                "name": "${name}_run",
                "description": "$description",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "input": {
                            "type": "string",
                            "description": "输入参数"
                        }
                    },
                    "required": ["input"]
                }
            }
        }
    ]


async def execute(tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
    """执行工具调用。"""
    if tool_name == "${name}_run":
        user_input = params.get("input", "")
        # TODO: 在此实现你的插件逻辑
        return {"success": True, "result": f"$name 收到输入: {user_input}"}
    return {"success": False, "error": f"未知工具: {tool_name}"}
''')


def _cmd_create_plugin(args):
    """创建插件模板目录。"""
    name = args.name.strip().replace("-", "_").replace(" ", "_")
    if not name:
        print("❌ 插件名不能为空")
        sys.exit(1)

    target = _SKILLS_DIR / name
    if target.exists():
        print(f"❌ 插件目录已存在: {target}")
        sys.exit(1)

    description = args.description or f"{name} 插件"
    author = args.author or "LucidMind User"

    target.mkdir(parents=True)
    ctx = {"name": name, "description": description, "author": author}

    (target / "manifest.json").write_text(
        _MANIFEST_TEMPLATE.safe_substitute(ctx), encoding="utf-8")
    (target / "main.py").write_text(
        _MAIN_TEMPLATE.safe_substitute(ctx), encoding="utf-8")

    print(f"✅ 插件已创建: {target}")
    print(f"   manifest.json — 插件元数据")
    print(f"   main.py       — 工具定义 + 执行逻辑")
    print(f"\n下一步:")
    print(f"  1. 编辑 {target / 'main.py'} 实现你的插件逻辑")
    print(f"  2. 重启 LucidMind 或调用 POST /api/plugins/reload 热加载")


# --- chat 子命令 ---

def _cmd_chat(args):
    """CLI 交互模式。"""
    import asyncio
    from dotenv import load_dotenv
    load_dotenv(_ROOT / ".env")

    from brain import Brain
    from adapters.llm.deepseek import DeepSeekAdapter
    from adapters.stream.cli_stream import CLIStreamAdapter
    from adapters.tools.shell import ShellAdapter
    from adapters.tools.file import FileAdapter
    from adapters.tools.web_search import WebSearchAdapter
    from adapters.tools.search_files import SearchFilesAdapter
    from adapters.tools.composite import CompositeToolAdapter
    from adapters.memory.json_memory import JSONMemoryAdapter
    from adapters.learning.memory_store_adapter import MemoryStoreLearningAdapter

    print("=" * 50)
    print("  LucidMind CLI v1.7")
    print("  透明思维的 AI Agent")
    print("  输入 /quit 退出, /think 切换思考显示")
    print("=" * 50)

    llm = DeepSeekAdapter()
    stream = CLIStreamAdapter(show_thinking=True)
    tools = CompositeToolAdapter([
        ShellAdapter(), FileAdapter(), WebSearchAdapter(), SearchFilesAdapter(),
    ])
    memory = JSONMemoryAdapter()
    learning = MemoryStoreLearningAdapter()

    brain = Brain(llm=llm, stream=stream, tools=tools, memory=memory, learning=learning)
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
            print(f"思考显示已{'开启' if stream._show_thinking else '关闭'}")
            continue
        loop.run_until_complete(brain.process(session_id, user_input))


# --- start 子命令 ---

def _cmd_start(args):
    """启动 Web 服务。"""
    import uvicorn
    host = args.host or "0.0.0.0"
    port = args.port or 8000
    uvicorn.run("api.main:app", host=host, port=port, reload=args.reload)


# --- 主入口 ---

def main():
    parser = argparse.ArgumentParser(
        prog="lucidmind",
        description="LucidMind — 清明心智，透明可扩展的 AI Agent",
    )
    sub = parser.add_subparsers(dest="command")

    # start
    p_start = sub.add_parser("start", help="启动 Web 服务")
    p_start.add_argument("--host", default="0.0.0.0", help="绑定地址 (默认 0.0.0.0)")
    p_start.add_argument("--port", type=int, default=8000, help="端口 (默认 8000)")
    p_start.add_argument("--reload", action="store_true", help="开发模式热重载")

    # chat
    sub.add_parser("chat", help="CLI 交互模式")

    # create-plugin
    p_cp = sub.add_parser("create-plugin", help="创建插件模板")
    p_cp.add_argument("name", help="插件名称 (如 my_tool)")
    p_cp.add_argument("--description", "-d", default="", help="插件描述")
    p_cp.add_argument("--author", "-a", default="", help="作者名")

    args = parser.parse_args()

    if args.command == "start":
        _cmd_start(args)
    elif args.command == "chat":
        _cmd_chat(args)
    elif args.command == "create-plugin":
        _cmd_create_plugin(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
