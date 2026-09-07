"""示例插件 — 展示插件系统的基本格式。"""

TOOLS = [{
    "type": "function",
    "function": {
        "name": "hello_plugin",
        "description": "示例插件工具，返回问候语。用于验证插件系统是否正常工作。",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "要问候的名字"},
            },
            "required": ["name"],
        },
    },
}]


def execute(tool_name, params):
    name = params.get("name", "World")
    return {"success": True, "result": f"Hello, {name}! 这是来自插件系统的问候。🔌", "error": None}
