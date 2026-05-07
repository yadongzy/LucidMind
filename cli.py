"""LucidMind CLI — 命令行入口。

用法:
  lucidmind start              启动 Web 服务
  lucidmind chat               CLI 交互模式
  lucidmind create-plugin NAME 创建插件模板
"""

import argparse
import json
import sys
from pathlib import Path


_ROOT = Path(__file__).parent
_SKILLS_DIR = _ROOT / "skills"


# --- create-plugin 子命令 ---


def _cmd_create_plugin(args):
    """创建插件模板目录。"""
    name = args.name.strip().replace("-", "_").replace(" ", "_")
    if not name or not name.isidentifier():
        print(f"❌ 无效的插件名: {name}（需要是合法的 Python 标识符）")
        sys.exit(1)

    target = _SKILLS_DIR / name
    if target.exists():
        print(f"❌ 插件目录已存在: {target}")
        sys.exit(1)

    description = args.description or f"{name} 插件"
    author = args.author or "LucidMind User"

    # 解析工具名列表
    if args.tools:
        tool_names = [t.strip() for t in args.tools.split(",") if t.strip()]
    else:
        tool_names = [f"{name}_run"]

    # 生成文件
    target.mkdir(parents=True)

    # 1. manifest.json
    manifest = {
        "name": name,
        "version": "1.0.0",
        "description": description,
        "author": author,
        "entry": "main.py",
        "tools": tool_names,
        "platform": [],
        "dependencies": [],
        "enabled": True,
    }
    (target / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # 2. main.py (ToolPort 类模板)
    class_name = "".join(w.capitalize() for w in name.split("_")) + "Adapter"
    main_py = _generate_main_py(name, class_name, description, tool_names)
    (target / "main.py").write_text(main_py, encoding="utf-8")

    # 3. README.md
    readme = _generate_readme(name, description, tool_names)
    (target / "README.md").write_text(readme, encoding="utf-8")

    print(f"\n✅ 插件已创建: {target}")
    print("   manifest.json — 插件元数据")
    print("   main.py       — ToolPort 类 + 工具定义")
    print("   README.md     — 插件文档")
    print(f"\n工具列表: {', '.join(tool_names)}")
    print("\n下一步:")
    print(f"  1. 编辑 {target / 'main.py'} 实现你的插件逻辑")
    print("  2. 重启 LucidMind 或调用 POST /api/plugins/reload 热加载")
    print("  3. 查看 docs/plugin-guide.md 了解更多")


def _generate_main_py(name: str, class_name: str, description: str,
                      tool_names: list[str]) -> str:
    """生成 ToolPort 类模板（与现有插件一致）。"""
    # 工具定义
    tool_defs = []
    for tn in tool_names:
        tool_defs.append(f'''            {{"type": "function", "function": {{
                "name": "{tn}",
                "description": "{tn} — TODO: 填写描述",
                "parameters": {{"type": "object", "properties": {{
                    "input": {{"type": "string", "description": "输入参数"}},
                }}, "required": ["input"]}},
            }}}}''')
    tools_str = ",\n".join(tool_defs)

    # execute 分支
    cases = []
    for i, tn in enumerate(tool_names):
        prefix = "if" if i == 0 else "elif"
        cases.append(
            f'        {prefix} tool_name == "{tn}":\n'
            f'            inp = params.get("input", "")\n'
            f'            # TODO: 实现 {tn} 的具体逻辑\n'
            f'            return {{"success": True, "result": f"{tn}: {{inp}}"}}'
        )
    cases_str = "\n".join(cases)

    return f'''"""{
    name} — {description}

ToolPort 插件模板。编辑此文件实现你的插件逻辑。
参考: docs/plugin-guide.md
"""

from typing import Any

from ports.tool_port import ToolPort


class {class_name}(ToolPort):
    """{description}"""

    def list_tools(self) -> list[dict[str, Any]]:
        return [
{tools_str}
        ]

    async def execute(self, tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
{cases_str}
        return {{"success": False, "error": f"未知工具: {{tool_name}}"}}
'''


def _generate_readme(name: str, description: str, tool_names: list[str]) -> str:
    """生成 README.md。"""
    tools_list = "\n".join(f"- `{tn}` — TODO: 填写描述" for tn in tool_names)
    return f"""# {name}

{description}

## 工具

{tools_list}

## 开发

1. 编辑 `main.py` 实现工具逻辑
2. 调用 `POST /api/plugins/reload` 或重启 LucidMind 热加载
3. 在对话中测试工具

## 参考

- [Plugin Guide](../../docs/plugin-guide.md)
- [ToolPort 接口](../../ports/tool_port.py)
"""


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
    print("  LucidMind CLI v3.1.1")
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
    port = args.port or 8765
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
    p_start.add_argument("--port", type=int, default=8765, help="端口 (默认 8765)")
    p_start.add_argument("--reload", action="store_true", help="开发模式热重载")

    # chat
    sub.add_parser("chat", help="CLI 交互模式")

    # create-plugin
    p_cp = sub.add_parser("create-plugin", help="创建插件模板")
    p_cp.add_argument("name", help="插件名称 (如 my_tool)")
    p_cp.add_argument("--description", "-d", default="", help="插件描述")
    p_cp.add_argument("--author", "-a", default="", help="作者名")
    p_cp.add_argument("--tools", "-t", default="",
                      help="工具名列表，逗号分隔 (如 search,create,delete)")

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
