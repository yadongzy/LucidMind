"""轻量任务分解器 — 混合模式的 Scheduler 角色。

复杂任务自动拆分为可独立执行的子任务，每个子任务通过 task_dispatcher 入队。
利用已有的 estimate_query_complexity() 判断是否需要分解，
仅 complex 级别任务触发 LLM 分解，避免浪费 token。

设计原则（对标 SAS 模式的 Scheduler）:
1. 规则优先：先用关键词/长度判断复杂度，只有 complex 才调 LLM
2. 轻量 LLM：分解 prompt 精简，只需输出子任务列表
3. 防递归：子任务标记 decomposed=True，不会被再次分解
4. 父子关联：子任务带 parent_id，全部完成后恢复父任务
"""
from logs import get_logger
from brain_perf import estimate_query_complexity
from brain_config import COMPLEXITY_MULTI_STEP_KEYWORDS

logger = get_logger("decomposer")

# 子任务数量上限（防 LLM 过度拆分）
MAX_SUBTASKS = 5
# 触发分解的最小内容长度（CJK字符信息密度高，40字≈英文80词）
MIN_DECOMPOSE_LENGTH = 40

_DECOMPOSE_PROMPT = (
    "你是任务分解专家。将以下复杂任务拆分为2-5个独立的子步骤，每个子步骤应可独立执行。\n"
    "只输出子步骤列表，每行一个，以数字编号开头。不要解释。\n\n"
    "任务: {content}\n\n"
    "子步骤:"
)


def should_decompose(task: dict) -> bool:
    """判断任务是否需要分解。

    条件：
    1. 未被分解过（防递归）
    2. 非学习/自检任务（这些任务不适合分解）
    3. 复杂度为 complex 或包含多步骤关键词
    4. 内容足够长
    """
    if task.get("decomposed"):
        return False
    if task.get("type") in ("learn",):
        return False
    if task.get("source") in ("self_check", "task_driven"):
        return False

    content = task.get("content", "")
    if len(content) < MIN_DECOMPOSE_LENGTH:
        return False

    complexity = estimate_query_complexity(content, None)
    if complexity == "complex":
        return True

    # 包含多个多步骤关键词也触发
    multi_count = sum(1 for kw in COMPLEXITY_MULTI_STEP_KEYWORDS if kw in content)
    if multi_count >= 2:
        return True

    return False


async def decompose_task(brain, task: dict) -> list[dict]:
    """用 LLM 将复杂任务分解为子任务列表。

    Args:
        brain: Brain 实例（用于调用 LLM）
        task: 待分解的任务

    Returns:
        子任务字典列表，每个包含 content 字段。
        如果分解失败，返回空列表（由调用方直接执行原任务）。
    """
    import task_dispatcher as td

    content = task.get("content", "")
    tid = task["id"]

    try:
        prompt = _DECOMPOSE_PROMPT.format(content=content[:500])
        # 使用 brain 的 LLM 直接调用（轻量，不走完整 process）
        response = await brain.llm.chat(
            messages=[{"role": "user", "content": prompt}],
            tools=None,
        )

        reply = ""
        if isinstance(response, dict):
            reply = response.get("content", "") or ""
        elif hasattr(response, "content"):
            reply = response.content or ""
        else:
            reply = str(response)

        subtasks = _parse_subtasks(reply)

        if not subtasks or len(subtasks) < 2:
            logger.debug(f"分解结果不足2步，跳过分解: {tid}")
            return []

        if len(subtasks) > MAX_SUBTASKS:
            subtasks = subtasks[:MAX_SUBTASKS]

        # 标记原任务为阻塞（等待所有子任务完成）
        td.block_task(tid, f"已分解为{len(subtasks)}个子任务")

        created = []
        for i, sub_content in enumerate(subtasks, 1):
            sub = td.enqueue(
                content=f"[子任务{i}/{len(subtasks)}] {sub_content}",
                task_type=task.get("type", "task"),
                priority=task.get("priority", "P2"),
                source=task.get("source", "system"),
                parent_id=tid,
                timeout_s=task.get("timeout_s", 120),
            )
            created.append(sub)

        # 批量标记子任务不可再分解（1次I/O代替N次）
        sub_ids = {s["id"] for s in created}
        store = td.load_store()
        for t in store["tasks"]:
            if t["id"] in sub_ids:
                t["decomposed"] = True
        td.save_store(store)

        logger.info(
            f"🔀 任务分解: {tid} → {len(created)}个子任务 "
            f"[{', '.join(s['id'] for s in created)}]"
        )
        return created

    except Exception as e:
        logger.warning(f"任务分解失败: {tid} error={e}")
        return []


def _parse_subtasks(text: str) -> list[str]:
    """解析 LLM 输出的子任务列表。

    支持格式：
    1. xxx
    2. xxx
    - xxx
    * xxx
    """
    lines = text.strip().splitlines()
    subtasks = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        # 去除编号前缀
        for prefix in ("1.", "2.", "3.", "4.", "5.", "6.", "7.", "8.", "9.", "10.",
                        "- ", "* ", "• "):
            if line.startswith(prefix):
                line = line[len(prefix):].strip()
                break
        if len(line) >= 3:  # 太短的不算有效子任务（CJK 3字即可表达完整意图）
            subtasks.append(line)
    return subtasks
