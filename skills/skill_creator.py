"""Skill Creator — Agent 找不到 skill 时自己创建。

对标 OpenClaw skill-creator/SKILL.md (371行):
- 根据工具需求描述，自动生成 manifest.json + main.py
- 生成后经过 skill_scanner 安全扫描
- 扫描通过后热加载进系统

闭环链路:
  大脑需要工具 → 搜索 PluginHub
    ├─ 找到 → 自动安装 → 热加载 → 重试      （A3）
    └─ 没找到 → Skill Creator 生成 → 扫描 → 热加载  （A5）
"""

import json
import pathlib
from typing import Any

from logs import get_logger

logger = get_logger("skill-creator")

_SKILLS_DIR = pathlib.Path(__file__).parent

# ─────────────────── Skill 模板 ───────────────────

_MANIFEST_TEMPLATE = {
    "name": "",
    "version": "1.0.0",
    "description": "",
    "tools": [],
    "platform": "all",
    "dependencies": [],
    "enabled": True,
}

_MAIN_PY_TEMPLATE = '''"""Auto-generated skill: {name}

{description}
"""

import json
from typing import Any


def get_tools() -> list[dict]:
    """返回工具定义列表。"""
    return [
{tool_defs}
    ]


async def execute(tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
    """执行工具调用。"""
{execute_body}
'''

_TOOL_DEF_TEMPLATE = '''        {{
            "type": "function",
            "function": {{
                "name": "{tool_name}",
                "description": "{tool_desc}",
                "parameters": {{
                    "type": "object",
                    "properties": {properties_json},
                    "required": {required_json}
                }}
            }}
        }}'''

_EXECUTE_CASE_TEMPLATE = '''    if tool_name == "{tool_name}":
        # TODO: 实现 {tool_name} 的具体逻辑
        return {{"success": True, "result": f"{tool_name} executed with params: {{params}}"}}
'''


async def create_skill_with_llm(
    name: str,
    description: str,
    tools: list[dict[str, Any]],
    llm=None,
    scan_before_load: bool = True,
) -> dict:
    """P2b: 用 LLM 生成完整 skill 实现代码（非 stub）。

    如果 LLM 不可用或生成失败，回退到 create_skill() 生成 stub。
    """
    if not llm:
        return create_skill(name, description, tools, scan_before_load)

    try:
        tool_specs = json.dumps(tools, ensure_ascii=False, indent=2)
        prompt = (
            f"请为一个名为 '{name}' 的Python工具插件生成完整的 main.py 代码。\n\n"
            f"描述: {description}\n\n"
            f"工具定义:\n{tool_specs}\n\n"
            f"要求:\n"
            f"1. 必须包含 get_tools() 函数，返回 OpenAI function calling 格式的工具列表\n"
            f"2. 必须包含 async def execute(tool_name, params) 函数\n"
            f"3. 实现真实功能逻辑（不要只返回 stub/placeholder）\n"
            f"4. 只用 Python 标准库，不要第三方依赖\n"
            f"5. 只输出纯 Python 代码，不要 markdown 代码块标记\n"
            f"6. 代码必须可以直接运行\n"
        )
        response = await llm.chat(
            [{"role": "user", "content": prompt}],
            tools=None,
        )
        code = response.get("content", "").strip()
        # 清理 markdown 代码块标记
        if code.startswith("```"):
            lines = code.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            code = "\n".join(lines)
        # 验证代码包含必要函数
        if "def get_tools" in code and "async def execute" in code:
            skill_dir = _SKILLS_DIR / name
            if skill_dir.exists():
                return {"success": False, "error": f"Skill {name} 已存在"}
            skill_dir.mkdir(parents=True, exist_ok=True)
            # manifest
            manifest = {**_MANIFEST_TEMPLATE, "name": name, "description": description,
                        "tools": [t["name"] for t in tools]}
            (skill_dir / "manifest.json").write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
            (skill_dir / "main.py").write_text(code, encoding="utf-8")
            logger.info(f"🤖 LLM Skill 已创建: {name} ({len(code)} chars)")
            # 安全扫描
            scan = None
            if scan_before_load:
                from skills.skill_scanner import scan_skill_directory
                scan = scan_skill_directory(skill_dir)
                if scan["block"]:
                    import shutil
                    shutil.rmtree(skill_dir, ignore_errors=True)
                    return {"success": False, "error": f"安全扫描未通过: {scan['summary']}", "scan": scan}
            # 热加载
            from skills import hot_reload
            hot_reload()
            return {"success": True, "path": str(skill_dir), "tools": [t["name"] for t in tools],
                    "scan": scan, "llm_generated": True}
        else:
            logger.warning(f"LLM 生成的代码缺少必要函数，回退 stub")
    except Exception as e:
        logger.warning(f"LLM skill 创建失败({e})，回退 stub")

    return create_skill(name, description, tools, scan_before_load)


def create_skill(
    name: str,
    description: str,
    tools: list[dict[str, Any]],
    scan_before_load: bool = True,
) -> dict:
    """创建一个新的 skill。

    Args:
        name: skill 名称（将作为目录名）
        description: skill 描述
        tools: 工具定义列表，每个元素:
            {"name": "tool_name", "description": "...", "parameters": {"param1": "desc1", ...}}
        scan_before_load: 是否在热加载前执行安全扫描

    Returns:
        {"success": bool, "error": str|None, "path": str|None, "scan": dict|None}
    """
    if not name or not name.isidentifier():
        return {"success": False, "error": f"无效的 skill 名称: {name}（需要是合法的 Python 标识符）"}

    skill_dir = _SKILLS_DIR / name
    if skill_dir.exists():
        return {"success": False, "error": f"Skill {name} 已存在: {skill_dir}"}

    if not tools:
        return {"success": False, "error": "至少需要定义一个工具"}

    try:
        # 1. 生成 manifest.json
        manifest = {**_MANIFEST_TEMPLATE}
        manifest["name"] = name
        manifest["description"] = description
        manifest["tools"] = [t["name"] for t in tools]

        # 2. 生成 main.py
        tool_defs_str = ",\n".join(_generate_tool_def(t) for t in tools)
        execute_cases = "".join(_generate_execute_case(t) for t in tools)
        execute_body = execute_cases + '    return {"success": False, "error": f"未知工具: {tool_name}"}'

        main_py = _MAIN_PY_TEMPLATE.format(
            name=name,
            description=description,
            tool_defs=tool_defs_str,
            execute_body=execute_body,
        )

        # 3. 写入文件
        skill_dir.mkdir(parents=True, exist_ok=True)
        (skill_dir / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (skill_dir / "main.py").write_text(main_py, encoding="utf-8")
        logger.info(f"🛠️ Skill 已创建: {name} → {skill_dir} ({len(tools)} 个工具)")

        # 4. 安全扫描
        scan = None
        if scan_before_load:
            from skills.skill_scanner import scan_skill_directory
            scan = scan_skill_directory(skill_dir)
            if scan["block"]:
                import shutil
                shutil.rmtree(skill_dir, ignore_errors=True)
                logger.warning(f"🚫 Skill {name} 安全扫描未通过，已删除: {scan['summary']}")
                return {"success": False, "error": f"安全扫描未通过: {scan['summary']}", "scan": scan}

        # 5. 热加载
        from skills import hot_reload
        reload_result = hot_reload()
        logger.info(f"🛠️ Skill {name} 已创建并热加载: {reload_result}")
        return {
            "success": True,
            "path": str(skill_dir),
            "tools": [t["name"] for t in tools],
            "scan": scan,
        }

    except Exception as e:
        # 清理失败的目录
        if skill_dir.exists():
            import shutil
            shutil.rmtree(skill_dir, ignore_errors=True)
        logger.error(f"🛠️ Skill 创建失败: {name}: {e}")
        return {"success": False, "error": str(e)}


def _generate_tool_def(tool: dict) -> str:
    """生成单个工具的 OpenAI function 定义字符串。"""
    tool_name = tool["name"]
    tool_desc = tool.get("description", tool_name)
    params = tool.get("parameters", {})

    properties = {}
    required = []
    for pname, pdesc in params.items():
        if isinstance(pdesc, dict):
            properties[pname] = pdesc
        else:
            properties[pname] = {"type": "string", "description": str(pdesc)}
        required.append(pname)

    return _TOOL_DEF_TEMPLATE.format(
        tool_name=tool_name,
        tool_desc=tool_desc,
        properties_json=json.dumps(properties, ensure_ascii=False),
        required_json=json.dumps(required),
    )


def _generate_execute_case(tool: dict) -> str:
    """生成单个工具的 execute 分支。"""
    return _EXECUTE_CASE_TEMPLATE.format(tool_name=tool["name"])
