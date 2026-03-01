"""Brain Learning Mixin — 学习相关方法。

从 brain.py 拆分，保持 Brain 核心精简。
包含: 经验记录、经验检索、失败学习、反思闭环、用户纠正/教学检测。
"""

from logs import get_logger
from brain_config import (
    LESSON_CACHE_TTL_SEC, MIN_LEARNING_INPUT_LEN, CORRECTION_PROMOTE_MIN,
    INABILITY_KEYWORDS, LEARNING_TRIVIAL,
    CORRECTION_FALLBACK_KEYWORDS, TEACHING_FALLBACK_KEYWORDS,
    LEARNING_DETECT_SYSTEM, LEARNING_DETECT_PROMPT,
)

logger = get_logger("brain")


class BrainLearningMixin:
    """学习能力混入 — 让大脑能从经验中学习。"""

    async def _ace_reflect_and_merge(self, session_id: str) -> None:
        """ACE Reflector: 工具调用后异步反思并合并经验。Phase R6 将完整实现。"""
        try:
            from memory import reflect_on_session
            await reflect_on_session(session_id, self._history, self.learning)
        except ImportError:
            pass
        except Exception as e:
            logger.debug(f"[{session_id}] ACE reflect 跳过: {e}")

    async def _learn_pattern(self, sid: str, trigger: str, lesson: str, source: str = "auto") -> None:
        """记录成功/失败模式到经验库。"""
        try:
            await self.learning.learn({"trigger": trigger, "lesson": lesson, "source": source, "source_session": sid})
        except Exception as e:
            logger.warning(f"[{sid}] 学习失败: {e}")

    # P1: 经验检索缓存 — 同会话短时间内复用结果，避免重复 LLM 调用
    _lesson_cache: dict = {}  # session_id -> {"text": str, "ts": float, "ctx_hash": str}
    _LESSON_CACHE_TTL = LESSON_CACHE_TTL_SEC

    async def _get_relevant_lessons(self) -> str:
        """S8: 检索与当前对话相关的经验。追踪注入的经验ID用于有效性评估。
        P1: 带缓存，同会话60s内上下文未变时复用。"""
        if not self.learning or not self._history:
            return ""
        # 从最近20条消息中提取用户消息 + assistant回复摘要，拓宽检索上下文
        recent_user = [m["content"] for m in self._history[-20:]
                       if m.get("role") == "user" and m.get("content")][-4:]
        recent_asst = [m["content"][:60] for m in self._history[-10:]
                       if m.get("role") == "assistant" and m.get("content")][-2:]
        recent = recent_user + recent_asst
        if not recent:
            return ""

        # P1: 缓存检查 — 上下文指纹未变且未过期时直接返回
        import time as _t
        ctx_text = " ".join(recent)
        ctx_hash = str(hash(ctx_text))
        sid = self._current_sid
        cached = self._lesson_cache.get(sid)
        if cached and cached["ctx_hash"] == ctx_hash and (_t.time() - cached["ts"]) < self._LESSON_CACHE_TTL:
            logger.debug(f"[{sid}] 经验检索命中缓存")
            return cached["text"]

        try:
            lessons = await self.learning.get_lessons(ctx_text, limit=3)
        except Exception as e:
            logger.warning(f"经验检索失败: {e}")
            return ""
        if not lessons:
            self._lesson_cache[sid] = {"text": "", "ts": _t.time(), "ctx_hash": ctx_hash}
            return ""
        # P4: 追踪注入的经验ID，用于后续有效性更新
        self._last_injected_lesson_ids = [l.get("id") for l in lessons if l.get("id")]
        text = "\n".join(
            f"- 触发: {l.get('trigger','')[:80]}\n  教训: {l.get('lesson','')[:120]}"
            for l in lessons
        )
        # P1: 写入缓存
        self._lesson_cache[sid] = {"text": text, "ts": _t.time(), "ctx_hash": ctx_hash}
        return text

    async def _mark_lessons_effective(self, effective: bool) -> None:
        """P4: 标记最近注入的经验为有效/无效。由 process() 成功/失败后调用。"""
        ids = getattr(self, "_last_injected_lesson_ids", [])
        if not ids or not self.learning:
            return
        for lid in ids:
            try:
                await self.learning.mark_applied(lid)
                await self.learning.update_effectiveness(lid, effective)
            except Exception:
                pass
        self._last_injected_lesson_ids = []

    async def _learn_from_inability(self, sid: str, user_input: str, reply: str) -> None:
        """S59: 失败自学习闭环 — 不会→记录→向老师求助。

        不使用提示词模板束缚大脑（规则03）。
        大脑说不会时：记录失败事实 + 通知老师作为学习来源。
        """
        if not self.learning:
            return
        if not any(w in reply for w in INABILITY_KEYWORDS):
            return

        # 不再记录"回答了不会"的垃圾经验 — 只通知老师求助
        logger.info(f"[{sid}] 不会回答: {user_input[:60]}")

        # 向老师求助 — 老师是大脑不会时最大的帮助来源
        try:
            from teacher_channel import TeacherChannel
            from api.brain_init import teacher
            teacher.send_to_teacher(
                msg_type="help",
                content=f"我不会回答这个问题: {user_input[:150]}",
                context=f"我的回答: {reply[:100]}",
                urgency="high",
            )
            await self.stream.emit("info", "🆘 已向老师求助")
        except Exception:
            pass

    async def _learn_from_tool_failure(self, sid: str, tool: str, params: dict, error: str) -> None:
        """工具失败：仅记录日志，不再写入经验库（避免垃圾）。"""
        logger.info(f"[{sid}] 工具失败: {tool} → {error[:50]}")

    async def _detect_and_learn(self, session_id: str, user_input: str) -> None:
        """S8+S59: 检测用户纠正或主动教学，自动学习。"""
        if not self.learning:
            return
        # 过滤系统内部session — 只有真实用户对话才值得学习
        _system_sessions = {"boot_check", "daily_check", "self_check", "curiosity"}
        if session_id in _system_sessions or session_id.startswith("task_"):
            return
        # 获取上一条助手回复用于上下文
        prev = next(
            (m["content"][:200] for m in reversed(self._history[:-1])
             if m.get("role") == "assistant" and m.get("content")),
            ""
        )
        # 用 LLM 判断用户是否在纠正/教学，比关键词准确得多
        signal = await self._detect_learning_signal(user_input, prev)
        if not signal:
            return
        src = signal  # "correction" or "teaching"
        try:
            if prev:
                trigger = prev[:80].strip()
            else:
                trigger = user_input[:80].strip()
            lesson = user_input[:200].strip()
            await self.learning.learn({
                "trigger": trigger,
                "lesson": lesson,
                "source": src,
                "source_session": session_id,
            })
            label = "📚 已学会" if src == "teaching" else "📝 已纠正"
            await self.stream.emit("info", f"{label}: {lesson[:60]}")
            logger.info(f"[{session_id}] {src}: trigger='{trigger[:40]}' lesson='{lesson[:40]}'")
            # 高频纠正自动写入 USER.md（永久行为改变）
            if src == "correction":
                await self._maybe_promote_to_profile(lesson)
        except Exception as e:
            logger.warning(f"[{session_id}] 学习失败: {e}")

    async def _detect_learning_signal(self, user_input: str, prev_reply: str) -> str | None:
        """用 LLM 判断用户意图：correction / teaching / None。
        LLM 不可用时回退到关键词匹配。"""
        # 严格预筛：太短、纯肯定词、或明显无关的直接跳过（避免额外 LLM 调用）
        stripped = user_input.strip()
        if len(stripped) < MIN_LEARNING_INPUT_LEN:
            return None
        if stripped.lower() in LEARNING_TRIVIAL:
            return None
        # 尝试 LLM 检测
        if self.llm:
            try:
                prompt = LEARNING_DETECT_PROMPT + "\n\n"
                if prev_reply:
                    prompt += f"AI上一条回复: {prev_reply[:100]}\n"
                prompt += f"用户说: {user_input[:200]}\n\n意图:"
                resp = await self.llm.chat([
                    {"role": "system", "content": LEARNING_DETECT_SYSTEM},
                    {"role": "user", "content": prompt},
                ])
                result = resp.get("content", "").strip().lower()
                if "correction" in result:
                    return "correction"
                if "teaching" in result:
                    return "teaching"
                return None
            except Exception:
                pass
        # LLM 不可用时回退关键词匹配
        inp = user_input.lower()
        if any(s in inp for s in CORRECTION_FALLBACK_KEYWORDS):
            return "correction"
        if any(s in inp for s in TEACHING_FALLBACK_KEYWORDS):
            return "teaching"
        return None

    async def _maybe_promote_to_profile(self, lesson: str) -> None:
        """检查经验库中是否有相似纠正≥2次，如果是则写入 USER.md 永久化。"""
        if not self.learning:
            return
        try:
            similar = await self.learning.get_lessons(lesson, limit=5)
            corrections = [l for l in similar if l.get("source") == "correction"]
            if len(corrections) < CORRECTION_PROMOTE_MIN:
                return
            import pathlib
            # 优先写入 identity/USER.md，兼容旧 user_profile.md
            user_path = pathlib.Path(__file__).parent / "identity" / "USER.md"
            if not user_path.exists():
                user_path = pathlib.Path(__file__).parent / "user_profile.md"
            if not user_path.exists():
                return
            content = user_path.read_text(encoding="utf-8")
            # 避免重复写入
            if lesson[:50] in content:
                return
            rule = f"- {lesson[:150]}"
            content += f"\n{rule}\n"
            user_path.write_text(content, encoding="utf-8")
            logger.info(f"⭐ 纠正提升为永久规则: {lesson[:50]}")
            await self.stream.emit("info", f"⭐ 已写入永久规则: {lesson[:60]}")
        except Exception as e:
            logger.debug(f"提升规则失败: {e}")
