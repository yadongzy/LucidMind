"""S44: 自我评估 — 每次回复后自动评分+改进建议。

Brain 回复后，用 LLM 快速评估回复质量，
发现问题时自动记录到经验库，驱动持续改进。

不修改 brain.py（规则 06），通过 BrainDaemon 或 hook 调用。
"""
import asyncio
import time
from typing import Any

from logs import get_logger

logger = get_logger("self_eval")


async def evaluate_reply(user_input: str, reply: str, llm,
                         thinking: str = "") -> dict[str, Any]:
    """评估一次回复的质量。

    Returns: {"score": 1-10, "strengths": [...], "weaknesses": [...],
              "suggestion": str, "should_learn": bool}
    """
    if not llm or not reply or len(reply) < 5:
        return {"score": 0, "strengths": [], "weaknesses": [],
                "suggestion": "", "should_learn": False}

    prompt = f"""评估以下AI回复的质量（1-10分）。

用户问题: {user_input[:200]}
AI回复: {reply[:400]}

评分维度:
1. 准确性 — 信息是否正确
2. 完整性 — 是否回答了用户的问题
3. 简洁性 — 是否简洁不啰嗦
4. 有用性 — 是否真正帮到用户

输出格式（严格JSON）:
{{"score": 8, "strengths": ["准确"], "weaknesses": ["略长"], "suggestion": "可以更简洁"}}
只返回JSON，不要其他文字。"""

    try:
        resp = await asyncio.wait_for(
            llm.chat([{"role": "user", "content": prompt}], tools=None),
            timeout=8.0
        )
        content = resp.get("content", "").strip()
        import re
        content = re.sub(r"<think>.*?</think>\s*", "", content, flags=re.DOTALL).strip()
        if "```" in content:
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        import json
        result = json.loads(content.strip())
        result["should_learn"] = result.get("score", 10) < 7
        logger.info(f"自评: {result.get('score', '?')}/10 — {result.get('suggestion', '')[:50]}")
        return result
    except asyncio.TimeoutError:
        logger.warning("自评超时")
    except Exception as e:
        logger.warning(f"自评失败: {e}")
    return {"score": 0, "strengths": [], "weaknesses": [],
            "suggestion": "", "should_learn": False}


async def auto_learn_from_eval(eval_result: dict, user_input: str,
                               learning_adapter) -> bool:
    """低分回复自动记录到经验库。"""
    if not eval_result.get("should_learn") or not learning_adapter:
        return False
    weaknesses = eval_result.get("weaknesses", [])
    suggestion = eval_result.get("suggestion", "")
    if not weaknesses and not suggestion:
        return False
    try:
        lesson = f"弱点: {', '.join(weaknesses[:3])}。改进: {suggestion[:100]}"
        await learning_adapter.learn({
            "trigger": user_input[:80],
            "lesson": lesson,
        })
        logger.info(f"自评学习: {lesson[:60]}")
        return True
    except Exception as e:
        logger.warning(f"自评学习失败: {e}")
        return False
