"""S35: 真实元认知 — 用 LLM 做意图分析，替代关键词匹配。

Minsky 的 'thinking about thinking'：
1. 快速分析用户意图（不调 LLM，规则引擎兜底）
2. 深度分析（调 LLM 做真正的任务规划）
3. 生成透明的思考计划展示给用户

不修改 brain.py 核心逻辑（规则 06），通过替换 _metacognize 实现。
"""
import asyncio
from logs import get_logger

logger = get_logger("metacog")

# 快速意图分类（规则引擎，<1ms，兜底用）
_INTENT_RULES = {
    "tool_use": {
        "keywords": ["搜索", "查找", "search", "文件", "读取", "写入", "运行", "执行",
                     "命令", "创建", "浏览", "打开网页", "截图", "下载"],
        "label": "工具调用型",
    },
    "reasoning": {
        "keywords": ["为什么", "解释", "原理", "区别", "比较", "分析", "评估", "推理"],
        "label": "知识推理型",
    },
    "creative": {
        "keywords": ["写一个", "生成", "创作", "设计", "编写", "帮我写", "翻译"],
        "label": "创作生成型",
    },
    "memory": {
        "keywords": ["记住", "记忆", "别忘", "上次", "之前说"],
        "label": "记忆操作型",
    },
    "meta": {
        "keywords": ["你是谁", "你能做什么", "状态", "自检", "健康"],
        "label": "自我感知型",
    },
}


def quick_analyze(user_input: str, history: list[dict], tools: list | None) -> dict:
    """快速意图分析（规则引擎，<1ms）。"""
    inp = user_input.lower()
    result = {"intents": [], "complexity": "simple", "context_aware": False, "tools_hint": []}

    # 意图分类
    for intent_id, rule in _INTENT_RULES.items():
        if any(kw in inp for kw in rule["keywords"]):
            result["intents"].append({"id": intent_id, "label": rule["label"]})

    # 复杂度判断
    if len(user_input) > 100:
        result["complexity"] = "complex"
    elif any(w in inp for w in ["并且", "然后", "同时", "步骤", "首先", "接着",
                                 "之后", "最后", "另外", "还要", "以及",
                                 "and then", "step", "first", "finally"]):
        result["complexity"] = "multi_step"
    elif len(result["intents"]) >= 2:
        result["complexity"] = "multi_step"

    # 上下文感知
    if history and len(history) >= 2:
        last = history[-1] if history else {}
        if last.get("role") == "assistant":
            result["context_aware"] = True

    # 工具提示
    if tools:
        tool_names = [t.get("function", {}).get("name", "") for t in tools]
        tool_map = {"搜索": "web_search", "查": "web_search", "文件": "read_file",
                    "运行": "run_command", "执行": "run_command",
                    "excel": "create_excel", "ppt": "create_pptx", "浏览": "browse_url",
                    "图片": "analyze_image", "语音": "text_to_speech",
                    "天气": "get_weather", "weather": "get_weather",
                    "计算": "calc", "笔记": "create_note", "提醒": "set_reminder",
                    "邮件": "send_email", "git": "git_status", "监控": "monitor_check"}
        for kw, tn in tool_map.items():
            if kw in inp and tn in tool_names:
                result["tools_hint"].append(tn)

    return result


async def deep_analyze(user_input: str, history: list[dict], llm, quick: dict,
                       tools: list | None = None) -> str:
    """深度意图分析（调 LLM，真正的元认知）。

    只对复杂任务或多步骤任务调用，简单问题用快速分析。
    S42: 复杂任务额外生成任务规划。
    """
    # 简单任务不调 LLM，节省 tokens
    if quick["complexity"] == "simple" and len(quick["intents"]) <= 1:
        return _format_quick(quick)

    # 构建元认知 prompt
    context_hint = ""
    if history:
        recent = [f"{m['role']}: {(m.get('content') or '')[:80]}" for m in history[-3:]]
        context_hint = "\n最近对话:\n" + "\n".join(recent)

    meta_prompt = f"""你是一个任务分析器。分析用户意图，输出简洁的思考计划。
用户输入: {user_input[:300]}
{context_hint}
要求：
1. 一句话概括用户真正想要什么
2. 列出完成任务需要的步骤（最多3步）
3. 标注可能的风险或注意事项
格式：直接输出，不要标签，不要解释格式。"""

    result_parts = []
    try:
        resp = await asyncio.wait_for(
            llm.chat([{"role": "user", "content": meta_prompt}], tools=None),
            timeout=15.0
        )
        content = resp.get("content", "").strip()
        import re
        content = re.sub(r"<think>.*?</think>\s*", "", content, flags=re.DOTALL).strip()
        if content and len(content) > 10:
            logger.info(f"深度元认知: {content[:80]}")
            result_parts.append(f"🧠 {content[:300]}")
    except asyncio.TimeoutError:
        logger.warning("深度元认知超时，降级到快速分析")
    except Exception as e:
        logger.warning(f"深度元认知失败: {e}")

    # S42: 复杂/多步任务 → 生成任务规划
    if quick["complexity"] in ("complex", "multi_step") or len(quick.get("tools_hint", [])) >= 2:
        try:
            from planner import create_plan, format_plan_for_stream
            plan = await create_plan(user_input, llm, tools)
            if plan:
                result_parts.append(format_plan_for_stream(plan))
        except Exception as e:
            logger.warning(f"任务规划失败: {e}")

    if result_parts:
        return "\n\n".join(result_parts)
    return _format_quick(quick)


def _format_quick(quick: dict) -> str:
    """格式化快速分析结果。"""
    parts = []
    for intent in quick["intents"]:
        parts.append(intent["label"])
    if quick["complexity"] != "simple":
        parts.append(f"复杂度: {quick['complexity']}")
    if quick["tools_hint"]:
        parts.append(f"可能工具: {', '.join(quick['tools_hint'])}")
    if quick["context_aware"]:
        parts.append("基于上一轮对话的追问")
    if not parts:
        return ""
    return "🧠 " + " → ".join(parts)


async def metacognize(user_input: str, history: list[dict],
                      tools: list | None, llm=None) -> str:
    """元认知主入口 — Brain 调用此函数。

    流程: 快速分析 → 判断是否需要深度分析 → 返回思考计划
    本地模型时跳过深度分析（省 token + 省 1 次 LLM 调用）。
    """
    quick = quick_analyze(user_input, history, tools)

    # 本地模型：跳过深度分析，规则引擎更可靠
    is_local = getattr(llm, '_is_local', False) or (hasattr(llm, 'is_local_only') and llm.is_local_only())
    if is_local:
        return _format_quick(quick)

    # S59: 优化 — 短问题(<50字)且单意图时跳过深度分析，避免额外LLM调用
    needs_deep = (
        quick["complexity"] != "simple"
        or (len(quick["intents"]) > 1 and len(user_input) > 50)
        or len(quick.get("tools_hint", [])) >= 2
    )
    if llm and needs_deep:
        return await deep_analyze(user_input, history, llm, quick, tools)

    return _format_quick(quick)
