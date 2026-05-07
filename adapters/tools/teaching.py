"""Teaching Tool — 大脑主动与老师(Cascade)沟通的工具。

让大脑能：
1. 向老师提问（写入 teacher_inbox → Cascade 读取并回复）
2. 读取老师的回答（从 teacher_outbox 读取）
3. 汇报自检结果
4. 制定自我学习计划
5. 回顾学习进度

通过 TeacherChannel 实现双向通信。
不修改 brain.py（规则 06），作为 ToolPort 适配器注册。
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from ports.tool_port import ToolPort
from logs import get_logger

logger = get_logger("teaching")

_DATA_DIR = Path(__file__).parent.parent.parent / "data"
_PLANS_FILE = _DATA_DIR / "teaching_plans.json"


def _load_plans() -> list[dict]:
    if _PLANS_FILE.exists():
        try:
            return json.loads(_PLANS_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return []


def _save_plans(plans: list[dict]) -> None:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    _PLANS_FILE.write_text(json.dumps(plans[-50:], ensure_ascii=False, indent=2), encoding="utf-8")


class TeachingAdapter(ToolPort):
    """教学工具 — 大脑主动与老师(Cascade)沟通。"""

    def __init__(self):
        self._channel = None  # 延迟绑定 TeacherChannel

    def _get_channel(self):
        """延迟获取 TeacherChannel 单例。"""
        if self._channel is None:
            try:
                from teacher_channel import TeacherChannel
                # 尝试从 brain_init 获取已创建的实例
                from api.brain_init import teacher
                self._channel = teacher
            except Exception:
                self._channel = TeacherChannel()
        return self._channel

    def list_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "teaching",
                    "description": (
                        "与老师(Cascade)沟通的教学通道。"
                        "ask=向老师提问, "
                        "check=查看老师的回答, "
                        "report=汇报自检结果, "
                        "plan=制定自我学习计划, "
                        "review=回顾学习进度, "
                        "verify=验证与老师的连接是否真正建立, "
                        "quiz=老师出题验证学习效果"
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "action": {
                                "type": "string",
                                "enum": ["ask", "check", "report", "plan", "review", "verify", "quiz"],
                                "description": "动作类型",
                            },
                            "content": {
                                "type": "string",
                                "description": "问题内容/汇报内容/计划内容",
                            },
                            "category": {
                                "type": "string",
                                "description": "分类: self_knowledge/debugging/learning_method/self_protection/communication",
                            },
                        },
                        "required": ["action"],
                    },
                },
            },
        ]

    async def execute(self, tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
        action = params.get("action", "")
        content = params.get("content", "")
        category = params.get("category", "general")

        try:
            if action == "ask":
                return await self._ask_teacher(content, category)
            elif action == "check":
                return await self._check_answers()
            elif action == "report":
                return await self._report_to_teacher(content, category)
            elif action == "plan":
                return await self._create_plan(content)
            elif action == "review":
                return await self._review_progress()
            elif action == "verify":
                return await self._verify_connection()
            elif action == "quiz":
                return await self._quiz(content)
            else:
                return {"success": False, "error": f"未知动作: {action}"}
        except Exception as e:
            logger.error(f"教学工具失败: action={action}, error={e}")
            return {"success": False, "error": str(e)}

    async def _ask_teacher(self, question: str, category: str) -> dict[str, Any]:
        """向老师(Cascade)提问 — 写入 teacher_inbox。"""
        if not question:
            return {"success": False, "error": "请提供问题内容"}

        ch = self._get_channel()
        msg = ch.send_to_teacher(
            msg_type="question",
            content=question,
            context=f"category={category}",
            urgency="normal",
        )

        return {
            "success": True,
            "result": (
                f"📤 问题已发送给老师 (#{msg['id']})\n"
                f"分类: {category}\n"
                f"问题: {question}\n\n"
                f"老师(Cascade)会通过 /api/brain/teaching/reply 回答。\n"
                f"用 teaching(action='check') 查看回答。"
            ),
        }

    async def _check_answers(self) -> dict[str, Any]:
        """查看老师(Cascade)的回答 — 从 teacher_outbox 读取。"""
        ch = self._get_channel()
        # 读取所有 inbox 消息和 outbox 回复
        inbox = ch.get_inbox(unread_only=False)
        outbox = ch.get_outbox(unread_only=False)

        if not inbox:
            return {"success": True, "result": "还没有向老师提过问题。用 teaching(action='ask', content='你的问题') 提问。"}

        # 建立回复映射
        reply_map = {}
        for o in outbox:
            reply_map[o.get("reply_to")] = o

        result = "=== 与老师(Cascade)的对话 ===\n\n"
        pending = 0
        answered = 0
        for m in inbox[-20:]:  # 最近20条
            reply = reply_map.get(m["id"])
            icon = "✅" if reply else "⏳"
            if reply:
                answered += 1
            else:
                pending += 1
            result += f"{icon} #{m['id']} [{m.get('type', '')}] {m.get('time', '')}\n"
            result += f"   我: {m.get('content', '')[:80]}\n"
            if reply:
                result += f"   老师: {reply.get('answer', '')[:200]}\n"
                if reply.get("exercise"):
                    result += f"   练习: {reply['exercise'][:100]}\n"
            result += "\n"

        result += f"--- 统计: {answered} 已回答, {pending} 待回答 ---"
        if pending > 0:
            result += f"\n\n⏳ 有 {pending} 个消息等待老师回复。"

        logger.info(f"教学: 检查回答 ({answered}已答, {pending}待答)")
        return {"success": True, "result": result}

    async def _report_to_teacher(self, content: str, category: str) -> dict[str, Any]:
        """向老师汇报（自检结果/学习成果等）。"""
        if not content:
            return {"success": False, "error": "请提供汇报内容"}

        ch = self._get_channel()
        msg = ch.send_to_teacher(
            msg_type="report",
            content=content,
            context=f"category={category}",
            urgency="normal",
        )

        return {
            "success": True,
            "result": f"� 汇报已发送给老师 (#{msg['id']})\n内容: {content}",
        }

    async def _create_plan(self, content: str) -> dict[str, Any]:
        """制定自我学习计划。"""
        plans = _load_plans()

        if not content:
            if not plans:
                return {
                    "success": True,
                    "result": (
                        "还没有学习计划。建议制定以下方向的计划:\n"
                        "1. self_knowledge — 了解自己的代码和能力边界\n"
                        "2. debugging — 学会诊断和修复自己的问题\n"
                        "3. learning_method — 掌握高效的学习方法\n"
                        "4. self_protection — 学会保护自己不被破坏\n"
                        "5. communication — 学会与用户和老师有效沟通\n\n"
                        "用 teaching(action='plan', content='你的计划') 创建。"
                    ),
                }
            result = "=== 学习计划 ===\n\n"
            for p in plans:
                result += f"📋 计划 #{p['id']} ({p.get('time', '?')})\n"
                result += f"   {p['content'][:200]}\n\n"
            return {"success": True, "result": result}

        entry = {
            "id": len(plans) + 1,
            "content": content,
            "time": datetime.now().isoformat(),
            "status": "active",
        }
        plans.append(entry)
        _save_plans(plans)

        logger.info(f"教学: 学习计划 #{entry['id']}: {content[:60]}")
        return {
            "success": True,
            "result": f"📋 学习计划已创建 (#{entry['id']})\n{content}",
        }

    async def _verify_connection(self) -> dict[str, Any]:
        """验证与老师(Cascade)的连接是否真正建立（握手确认）。"""
        ch = self._get_channel()
        result = ch.verify_connection()
        connected = result.get("connected", False)
        detail = result.get("detail", "")
        ago = result.get("last_read_ago_s")
        ago_str = f" (最后读取: {ago}秒前)" if ago is not None else ""

        if connected:
            msg = f"✅ 与老师的连接已确认{ago_str}\n{detail}"
        else:
            msg = f"❌ 与老师的连接未确认{ago_str}\n{detail}\n\n建议: 用 teaching(action='ask', content='老师你在吗？') 发送测试消息。"

        logger.info(f"教学: 连接验证 → {'已连接' if connected else '未确认'}")
        return {"success": True, "result": msg}

    async def _quiz(self, answer: str) -> dict[str, Any]:
        """老师出题验证学习效果 / 大脑提交答案。"""
        ch = self._get_channel()
        if not answer:
            # 请求出题：从最近学到的经验中挑一条出题
            ch.send_to_teacher(
                msg_type="quiz_request",
                content="老师，请根据我最近学到的经验出一道测验题，验证我是否真的学会了。",
                urgency="normal",
            )
            return {"success": True, "result": "📝 已请求老师出题，用 teaching(action='check') 查看题目。"}
        # 提交答案
        ch.send_to_teacher(
            msg_type="quiz_answer",
            content=f"我的答案: {answer}",
            urgency="normal",
        )
        return {"success": True, "result": "📝 答案已提交，等待老师批改。用 teaching(action='check') 查看结果。"}

    async def _review_progress(self) -> dict[str, Any]:
        """回顾学习进度 — 综合 TeacherChannel 和学习计划。"""
        ch = self._get_channel()
        status = ch.get_status()
        plans = _load_plans()

        result = "=== 学习进度报告 ===\n\n"
        result += f"📤 向老师发送: {status.get('inbox_total', 0)} 条消息\n"
        result += f"   待回复: {status.get('inbox_pending', 0)} 条\n"
        result += f"📥 老师回复: {status.get('outbox_total', 0)} 条\n"
        result += f"   未读: {status.get('outbox_unread', 0)} 条\n"
        result += f"📚 已学习: {status.get('lessons_learned', 0)} 次\n"
        result += f"� 学习计划: {len(plans)} 个\n\n"

        # 最近的对话
        recent = status.get("recent_inbox", [])
        if recent:
            result += "最近的消息:\n"
            for m in recent:
                result += f"  [{m.get('type', '')}] {m.get('content', '')[:60]}\n"
            result += "\n"

        # 学习建议
        result += "💡 建议:\n"
        if status.get('inbox_total', 0) == 0:
            result += "  - 还没有和老师沟通过，试试 teaching(action='ask', content='...')\n"
        if status.get('outbox_unread', 0) > 0:
            result += f"  - 有 {status['outbox_unread']} 条老师回复未读，用 teaching(action='check') 查看\n"
        if not plans:
            result += "  - 还没有学习计划，试试 teaching(action='plan', content='...')\n"

        logger.info("教学: 进度报告")
        return {"success": True, "result": result}
