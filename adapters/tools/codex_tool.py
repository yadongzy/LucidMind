"""Codex Tool — 让 Brain 能通过对话调用 Codex CLI 执行代码任务。

功能:
- codex_explain: 只读分析/解释代码
- codex_review: 代码审查
- codex_patch: 代码修复/修改（需安全确认）
- codex_heal: 触发自愈引擎（体检+诊断+修复）
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ports.tool_port import ToolPort
from logs import get_logger
from skills.codex_cli.runner import CodexCliRunner, resolve_codex_executable

logger = get_logger("tools.codex")

_ROOT = Path(__file__).parent.parent.parent


class CodexToolAdapter(ToolPort):
    """Codex 工具适配器 — 让 LLM 能直接调用 Codex CLI。"""

    def __init__(self):
        self._codex_path = resolve_codex_executable()
        self._codex_available = bool(self._codex_path)
        if self._codex_available:
            logger.info(f"✅ Codex CLI 已检测到，Codex 工具已启用: {self._codex_path}")
        else:
            logger.warning("⚠️ Codex CLI 未安装，Codex 工具将降级为只读模式")

    def list_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "codex",
                    "description": (
                        "调用 Codex CLI 执行代码任务。"
                        "支持: explain(解释代码), review(代码审查), patch(修复代码), heal(自愈体检)。"
                        "当用户要求修复代码、分析项目、代码审查、或使用 Codex 时调用此工具。"
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "action": {
                                "type": "string",
                                "enum": ["explain", "review", "patch", "heal"],
                                "description": (
                                    "操作类型: "
                                    "explain=解释代码/项目结构, "
                                    "review=审查代码质量和风险, "
                                    "patch=修复/修改代码(需确认), "
                                    "heal=运行自愈引擎(体检+诊断+修复)"
                                ),
                            },
                            "target": {
                                "type": "string",
                                "description": "目标文件或目录路径(相对项目根目录)，默认为整个项目",
                                "default": ".",
                            },
                            "instruction": {
                                "type": "string",
                                "description": "具体指令：要解释什么、审查什么、修复什么",
                            },
                        },
                        "required": ["action", "instruction"],
                    },
                },
            }
        ]

    async def execute(self, tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
        if tool_name != "codex":
            return {"success": False, "result": None, "error": f"未知工具: {tool_name}"}

        action = params.get("action", "explain")
        target = params.get("target", ".")
        instruction = params.get("instruction", "")

        try:
            if action == "heal":
                result = self._run_heal()
            elif action in ("explain", "review", "patch"):
                result = self._run_codex(action, target, instruction)
            else:
                return {"success": False, "result": None, "error": f"不支持的操作: {action}"}
            return {"success": True, "result": result, "error": None}
        except Exception as e:
            return {"success": False, "result": None, "error": str(e)}

    def _run_heal(self) -> str:
        """运行自愈引擎。"""
        try:
            from checkup.self_heal import SelfHealEngine
            engine = SelfHealEngine(_ROOT)
            result = engine.heal(trigger="brain_codex_tool")
            d = result.to_dict()
            return (
                f"🏥 自愈结果:\n"
                f"- 分数: {d['original_score']} → {d['final_score']} "
                f"({'✅ 提升' if d['improved'] else '⏸️ 未变化'})\n"
                f"- 修复: {d['repairs_succeeded']}/{d['repairs_attempted']} 成功\n"
                f"- 修复文件: {', '.join(d['files_healed']) or '无'}\n"
                f"- 回滚: {', '.join(d['rollbacks']) or '无'}\n"
                f"- 耗时: {d['duration_ms']:.0f}ms"
            )
        except Exception as e:
            logger.error(f"自愈失败: {e}")
            return f"❌ 自愈失败: {e}"

    def _run_codex(self, action: str, target: str, instruction: str) -> str:
        """通过 Codex CLI 执行代码任务。"""
        if not self._codex_available:
            return (
                f"⚠️ Codex CLI 未安装。请先安装:\n"
                f"  npm install -g @openai/codex\n\n"
                f"降级方案: 我会直接用 AI 分析来回答你的问题。\n\n"
                f"你的请求: [{action}] {instruction}\n目标: {target}"
            )

        try:
            codex = CodexCliRunner(_ROOT, executable=self._codex_path or "codex")

            if action == "explain":
                result = codex.explain(target, instruction)
            elif action == "review":
                result = codex.review(target, instruction)
            elif action == "patch":
                result = codex.patch(target, instruction, approved=True)
            else:
                return f"不支持的操作: {action}"

            if result.success:
                output = result.stdout.strip()
                if len(output) > 3000:
                    output = output[:3000] + "\n... [输出已截断]"
                return f"✅ Codex {action} 完成:\n\n{output}"
            else:
                error = result.error or result.stderr
                return f"❌ Codex {action} 失败: {error[:500]}"

        except Exception as e:
            logger.error(f"Codex 调用异常: {e}")
            return f"❌ Codex 调用异常: {e}"
