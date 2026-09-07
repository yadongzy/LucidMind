"""S20: 子代理工具 — 将复杂任务拆分为子任务并行执行。

Brain 通过 Tool Port 调用子代理，无需修改核心。
子代理本质是：将一个大任务拆成多个小 prompt，并行调 LLM，汇总结果。
"""
import asyncio
from typing import Any

from ports.tool_port import ToolPort
from logs import get_logger

logger = get_logger("tools")


class SubAgentAdapter(ToolPort):
    """子代理工具：拆分复杂任务为子任务并行执行。"""

    def __init__(self, llm=None):
        self._llm = llm

    def set_llm(self, llm):
        """延迟注入 LLM（避免循环依赖）。"""
        self._llm = llm

    def list_tools(self) -> list[dict[str, Any]]:
        return [{
            "type": "function",
            "function": {
                "name": "decompose_task",
                "description": "将复杂任务拆分为多个子任务并行执行。适用于：多步骤任务、需要从多个角度分析的问题、需要同时处理多个文件的操作。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "task": {"type": "string", "description": "要拆分的复杂任务描述"},
                        "subtasks": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "拆分后的子任务列表（2-5个）",
                        },
                    },
                    "required": ["task", "subtasks"],
                },
            },
        }]

    async def execute(self, tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
        if tool_name != "decompose_task":
            return {"success": False, "result": None, "error": f"未知工具: {tool_name}"}
        if not self._llm:
            return {"success": False, "result": None, "error": "LLM 未初始化"}

        task = params.get("task", "")
        subtasks = params.get("subtasks", [])
        if not subtasks:
            return {"success": False, "result": None, "error": "子任务列表为空"}

        logger.info(f"子代理启动: 主任务='{task[:60]}', {len(subtasks)}个子任务")

        # 并行执行所有子任务
        async def run_subtask(idx, st):
            try:
                messages = [
                    {"role": "system", "content": f"你是一个专注的子代理。主任务: {task}\n你只负责完成以下子任务，简洁回答:"},
                    {"role": "user", "content": st},
                ]
                result = await self._llm.chat(messages)
                content = result.get("content", "") if isinstance(result, dict) else str(result)
                logger.info(f"子任务{idx+1}完成: {st[:40]} → {len(content)}字")
                return {"subtask": st, "result": content, "success": True}
            except Exception as e:
                logger.warning(f"子任务{idx+1}失败: {e}")
                return {"subtask": st, "result": str(e), "success": False}

        results = await asyncio.gather(*[run_subtask(i, st) for i, st in enumerate(subtasks)])

        # 汇总
        summary_parts = []
        for r in results:
            status = "✅" if r["success"] else "❌"
            summary_parts.append(f"{status} {r['subtask']}:\n{r['result'][:500]}")

        succeeded = sum(1 for r in results if r["success"])
        summary = f"子代理完成 {succeeded}/{len(results)} 个子任务:\n\n" + "\n\n---\n\n".join(summary_parts)
        logger.info(f"子代理汇总: {succeeded}/{len(results)} 成功")

        return {"success": succeeded > 0, "result": summary, "error": None}
