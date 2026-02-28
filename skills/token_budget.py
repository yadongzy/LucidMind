"""Skills Token Budget — 工具定义的 Token 预算管理。

改进3: 当技能数量增长时，限制注入 LLM prompt 的工具定义总量。
避免超出模型 context window 或浪费 token。
"""

from logs import get_logger

logger = get_logger("skills.token_budget")

# 默认预算配置
MAX_TOOLS_IN_PROMPT = 80
MAX_TOOLS_PROMPT_CHARS = 30_000
MAX_PROMPT_SKILLS_CHARS = 15_000


def filter_tools_by_budget(
    tool_definitions: list[dict],
    max_tools: int = MAX_TOOLS_IN_PROMPT,
    max_chars: int = MAX_TOOLS_PROMPT_CHARS,
) -> list[dict]:
    """按预算过滤工具定义列表。

    优先保留靠前的工具（假设已按重要性排序）。
    返回在 token 预算内的工具子集。
    """
    if len(tool_definitions) <= max_tools:
        # 快速路径：数量在限制内，只检查字符数
        import json
        total = sum(len(json.dumps(t, ensure_ascii=False)) for t in tool_definitions)
        if total <= max_chars:
            return tool_definitions

    import json
    selected = []
    char_count = 0
    for t in tool_definitions:
        if len(selected) >= max_tools:
            break
        t_chars = len(json.dumps(t, ensure_ascii=False))
        if char_count + t_chars > max_chars:
            break
        selected.append(t)
        char_count += t_chars

    if len(selected) < len(tool_definitions):
        logger.info(f"📊 Token预算: {len(selected)}/{len(tool_definitions)} 工具 "
                     f"({char_count}/{max_chars} 字符)")
    return selected


def filter_prompt_skills(
    prompt_skills: list[dict],
    max_chars: int = MAX_PROMPT_SKILLS_CHARS,
) -> list[dict]:
    """按预算过滤 prompt 型技能的知识内容。

    prompt_skills: [{"name": "...", "prompt_content": "...", "prompt_tokens": N}, ...]
    返回在字符预算内的技能子集。
    """
    selected = []
    char_count = 0
    for skill in prompt_skills:
        content_len = skill.get("prompt_tokens", len(skill.get("prompt_content", "")))
        if char_count + content_len > max_chars:
            break
        selected.append(skill)
        char_count += content_len

    if len(selected) < len(prompt_skills):
        logger.info(f"📊 知识预算: {len(selected)}/{len(prompt_skills)} 知识技能 "
                     f"({char_count}/{max_chars} 字符)")
    return selected


def get_prompt_skills_content() -> str:
    """获取所有 prompt 型技能的内容，拼接为单个字符串（受预算限制）。"""
    from skills.registry import _registry

    prompt_skills = []
    for name, info in _registry.items():
        if info.get("kind") == "prompt" and info.get("status") == "loaded":
            prompt_skills.append({
                "name": name,
                "description": info.get("description", ""),
                "prompt_content": info.get("prompt_content", ""),
                "prompt_tokens": info.get("prompt_tokens", 0),
            })

    if not prompt_skills:
        return ""

    filtered = filter_prompt_skills(prompt_skills)

    parts = []
    for skill in filtered:
        parts.append(f"## 知识: {skill['name']}")
        if skill.get("description"):
            parts.append(f"> {skill['description']}")
        parts.append(skill["prompt_content"])
        parts.append("")

    return "\n".join(parts)
