"""Teacher Channel — 大脑与老师(Cascade)的双向通信通道。

核心机制:
1. 大脑主动写消息到 inbox（向老师提问/汇报/求助）
2. 老师(Cascade)读 inbox，写回答到 outbox
3. 大脑读 outbox，学习老师的回答
4. Daemon 后台自动驱动：自检→发现问题→向老师求助→读取回答→学习

通信协议:
- inbox:  大脑 → 老师 的消息队列
- outbox: 老师 → 大脑 的消息队列
- 每条消息有 id, type, content, status, timestamp

不修改 brain.py（规则 06），作为独立模块被 Daemon 和工具调用。
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from logs import get_logger

logger = get_logger("teaching")

_DATA_DIR = Path(__file__).parent / "data"
_INBOX = _DATA_DIR / "teacher_inbox.json"
_OUTBOX = _DATA_DIR / "teacher_outbox.json"
_LEARN_LOG = _DATA_DIR / "teaching_learn_log.json"


def _load_json(path: Path) -> list[dict]:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return []


def _save_json(path: Path, data: list[dict]) -> None:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data[-200:], ensure_ascii=False, indent=2), encoding="utf-8")


class TeacherChannel:
    """大脑与老师(Cascade)的双向通信通道。"""

    def __init__(self, brain=None):
        self._brain = brain
        self._auto_ask_enabled = True

    def set_brain(self, brain) -> None:
        self._brain = brain

    # ─── 大脑 → 老师 ───

    def send_to_teacher(self, msg_type: str, content: str,
                        context: str = "", urgency: str = "normal") -> dict:
        """大脑主动向老师发消息。

        msg_type: question/report/help/self_check/learning_result
        urgency: low/normal/high/critical
        """
        inbox = _load_json(_INBOX)
        msg = {
            "id": len(inbox) + 1,
            "type": msg_type,
            "content": content,
            "context": context,
            "urgency": urgency,
            "status": "pending",
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "read_by_teacher": False,
        }
        inbox.append(msg)
        _save_json(_INBOX, inbox)
        logger.info(f"📤 大脑→老师 [{msg_type}] #{msg['id']}: {content[:60]}")
        return msg

    def get_inbox(self, unread_only: bool = True) -> list[dict]:
        """老师读取大脑发来的消息。"""
        inbox = _load_json(_INBOX)
        if unread_only:
            return [m for m in inbox if not m.get("read_by_teacher")]
        return inbox

    def mark_inbox_read(self, msg_id: int) -> None:
        """老师标记消息已读。"""
        inbox = _load_json(_INBOX)
        for m in inbox:
            if m["id"] == msg_id:
                m["read_by_teacher"] = True
                break
        _save_json(_INBOX, inbox)

    # ─── 老师 → 大脑 ───

    def reply_to_brain(self, inbox_msg_id: int, answer: str,
                       action: str = "", exercise: str = "") -> dict:
        """老师回复大脑的消息。

        answer: 回答内容
        action: 要求大脑执行的动作（可选）
        exercise: 布置的练习（可选）
        """
        outbox = _load_json(_OUTBOX)
        msg = {
            "id": len(outbox) + 1,
            "reply_to": inbox_msg_id,
            "answer": answer,
            "action": action,
            "exercise": exercise,
            "status": "pending",
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "read_by_brain": False,
        }
        outbox.append(msg)
        _save_json(_OUTBOX, outbox)

        # 同时标记 inbox 消息已回复
        inbox = _load_json(_INBOX)
        for m in inbox:
            if m["id"] == inbox_msg_id:
                m["status"] = "answered"
                m["read_by_teacher"] = True
                break
        _save_json(_INBOX, inbox)

        logger.info(f"📥 老师→大脑 回复#{inbox_msg_id}: {answer[:60]}")
        return msg

    def get_outbox(self, unread_only: bool = True) -> list[dict]:
        """大脑读取老师发来的回复。"""
        outbox = _load_json(_OUTBOX)
        if unread_only:
            return [m for m in outbox if not m.get("read_by_brain")]
        return outbox

    # ─── 大脑自动学习老师的回复 ───

    async def process_teacher_replies(self) -> list[str]:
        """大脑处理老师的所有未读回复 — 学习+执行。

        由 Daemon 后台自动调用。
        """
        outbox = _load_json(_OUTBOX)
        unread = [m for m in outbox if not m.get("read_by_brain")]
        if not unread:
            return []

        results = []
        learn_log = _load_json(_LEARN_LOG)

        # 先标记所有未读为已读并保存，防止 daemon 下一轮重复投递
        for msg in unread:
            msg["read_by_brain"] = True
            msg["status"] = "processed"
        _save_json(_OUTBOX, outbox)

        for msg in unread:
            answer = msg.get("answer", "")
            exercise = msg.get("exercise", "")
            action = msg.get("action", "")

            # 1. 学习老师的回答
            if answer and self._brain and self._brain.learning:
                try:
                    await self._brain.learning.learn({
                        "trigger": f"老师教学 (回复#{msg.get('reply_to', '?')})",
                        "lesson": answer[:200],
                    })
                    results.append(f"📚 学习了老师的回答: {answer[:50]}")
                except Exception as e:
                    results.append(f"⚠️ 学习失败: {e}")

            # 2. 执行老师布置的练习
            if exercise:
                results.append(f"📝 收到练习: {exercise[:80]}")
                # 通过 Brain.process 执行练习
                if self._brain:
                    try:
                        await self._brain.process("teaching", f"[老师练习] {exercise}")
                        results.append("✅ 练习已执行")
                    except Exception as e:
                        results.append(f"⚠️ 练习执行失败: {e}")

            # 3. 执行老师要求的动作（每次用新session避免历史累积）
            if action:
                results.append(f"🔧 收到指令: {action[:80]}")
                if self._brain:
                    try:
                        import time as _t
                        sid = f"teach_{int(_t.time())}"
                        await self._brain.process(sid, f"[老师指令] {action}")
                        self._brain._sessions.pop(sid, None)
                        results.append("✅ 指令已执行")
                    except Exception as e:
                        results.append(f"⚠️ 指令执行失败: {e}")

            # 记录学习日志
            learn_log.append({
                "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "reply_id": msg["id"],
                "learned": answer[:100] if answer else "",
                "exercise": exercise[:100] if exercise else "",
                "results": results[-3:],
            })

        _save_json(_OUTBOX, outbox)
        _save_json(_LEARN_LOG, learn_log)

        if results:
            logger.info(f"📖 处理老师回复: {len(unread)}条, 结果: {'; '.join(results[:5])}")
        return results

    # ─── 大脑自检并主动汇报 ───

    async def auto_self_check(self) -> list[str]:
        """大脑自动自检，发现问题主动向老师汇报。"""
        if not self._brain: return []
        inbox = _load_json(_INBOX)
        if sum(1 for m in inbox if m.get("status") == "pending") >= 5: return []
        issues = []
        # 1. 经验库健康
        if self._brain.learning:
            try:
                lessons = await self._brain.learning.get_lessons("", limit=200)
                triggers = [l.get("trigger", "") for l in lessons]
                dupes = len(triggers) - len(set(triggers))
                if dupes > 5: issues.append(f"经验库有 {dupes} 条重复经验")
                tmap, contras = {}, 0
                for l in lessons:
                    t, v = l.get("trigger", "")[:50], l.get("lesson", "")[:50]
                    if t in tmap and tmap[t] != v: contras += 1
                    tmap[t] = v
                if contras > 0: issues.append(f"经验库有 {contras} 对矛盾经验")
            except Exception as e:
                issues.append(f"经验库检查失败: {e}")
        # 2. 最近错误
        brain_log = Path(__file__).parent / "logs" / "brain.log"
        if brain_log.exists():
            try:
                lines = brain_log.read_text(encoding="utf-8").splitlines()[-100:]
                errors = [l for l in lines if "ERROR" in l]
                if len(errors) >= 3:
                    issues.append(f"最近日志有 {len(errors)} 个错误:\n" + "\n".join(errors[-3:]))
            except Exception: pass
        # 3. SOUL.md 行数
        soul_path = Path(__file__).parent / "identity" / "SOUL.md"
        if soul_path.exists():
            sl = len(soul_path.read_text(encoding="utf-8").splitlines())
            if sl > 180: issues.append(f"SOUL.md 已有 {sl}/200 行")
        # 4. 汇报
        for issue in issues:
            self.send_to_teacher(msg_type="self_check", content=issue,
                                urgency="high" if "错误" in issue else "normal")
        if issues: logger.info(f"🔍 自检发现 {len(issues)} 个问题")
        return issues

    # ─── 大脑主动提问（好奇心驱动）───

    async def curiosity_ask(self) -> str | None:
        """大脑基于当前状态主动提出学习问题。"""
        if not self._brain or not self._auto_ask_enabled: return None
        inbox = _load_json(_INBOX)
        if sum(1 for m in inbox if m.get("status") == "pending") >= 3: return None
        sc = len(self._brain._sessions)
        tm = sum(len(h) for h in self._brain._sessions.values())
        status = f"会话{sc}个, 消息{tm}条"
        if self._brain.learning:
            try:
                lessons = await self._brain.learning.get_lessons("", limit=5)
                status += f", 经验{len(lessons)}条"
            except Exception: pass
        try:
            await self._brain.process(
                "teaching_curiosity",
                f"[自主思考] 当前状态: {status}。如果你有想问老师的问题，用 teaching 工具提问。")
            new_inbox = _load_json(_INBOX)
            if len(new_inbox) > len(inbox):
                latest = new_inbox[-1]
                logger.info(f"💡 大脑自主提问: {latest.get('content', '')[:60]}")
                return latest.get("content", "")
        except Exception as e:
            logger.warning(f"自主思考失败: {e}")
        return None

    # ─── 握手确认（盲人握手问题）───

    def verify_connection(self) -> dict[str, Any]:
        """验证与 Cascade 老师的连接是否真正建立。

        检查最近发送的消息是否被老师读取/回复。
        返回: {"connected": bool, "detail": str, "last_read_ago_s": int|None}
        """
        inbox = _load_json(_INBOX)
        outbox = _load_json(_OUTBOX)
        if not inbox:
            return {"connected": False, "detail": "尚未发送过消息给老师", "last_read_ago_s": None}

        # 检查最近10条消息中有多少被老师读取
        recent = inbox[-10:]
        read_count = sum(1 for m in recent if m.get("read_by_teacher"))
        replied_ids = {o.get("reply_to") for o in outbox}
        replied_count = sum(1 for m in recent if m["id"] in replied_ids)

        # 找最近一次被读取的时间
        last_read_time = None
        for m in reversed(inbox):
            if m.get("read_by_teacher"):
                last_read_time = m.get("time")
                break

        last_read_ago_s = None
        if last_read_time:
            try:
                from datetime import datetime as dt
                t = dt.strptime(last_read_time, "%Y-%m-%d %H:%M:%S")
                last_read_ago_s = int((datetime.now() - t).total_seconds())
            except Exception:
                pass

        if replied_count > 0:
            return {
                "connected": True,
                "detail": f"连接正常: 最近{len(recent)}条中{read_count}条已读, {replied_count}条已回复",
                "last_read_ago_s": last_read_ago_s,
            }
        if read_count > 0:
            return {
                "connected": True,
                "detail": f"连接正常(未回复): 最近{len(recent)}条中{read_count}条已读",
                "last_read_ago_s": last_read_ago_s,
            }
        return {
            "connected": False,
            "detail": f"连接未确认: 最近{len(recent)}条消息均未被老师读取",
            "last_read_ago_s": None,
        }

    # ─── 状态查询 ───

    def get_status(self) -> dict[str, Any]:
        """获取教学通道状态。"""
        inbox = _load_json(_INBOX)
        outbox = _load_json(_OUTBOX)
        learn_log = _load_json(_LEARN_LOG)
        return {
            "inbox_total": len(inbox),
            "inbox_pending": sum(1 for m in inbox if m.get("status") == "pending"),
            "outbox_total": len(outbox),
            "outbox_unread": sum(1 for m in outbox if not m.get("read_by_brain")),
            "lessons_learned": len(learn_log),
            "recent_inbox": inbox[-3:] if inbox else [],
            "recent_outbox": outbox[-3:] if outbox else [],
        }
