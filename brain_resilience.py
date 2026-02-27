"""Brain Resilience Mixin — 自愈/重试/自检/压缩/消息清洗方法。

从 brain.py 拆分，保持 Brain 核心精简。
包含: LLM重试(Ralph)、工具重试、参数自适应、自检、历史压缩、消息清洗。

核心理念（第零条）：想尽一切办法完成任务 + 想尽一切办法保护自己。
"""

import asyncio
import os
import platform
import re

from logs import get_logger

logger = get_logger("brain")


class BrainResilienceMixin:
    """韧性能力混入 — 让大脑能自愈、重试、自检。"""

    async def _llm_call_with_retry(self, session_id: str, messages: list, tools,
                                    tool_choice: str | None = None,
                                    llm_override=None, _s=None) -> dict:
        """S7 Ralph: LLM 调用失败时自动重试，每次重试透明告知用户。
        tool_choice: "auto"/"required"/None — 控制是否强制工具调用
        llm_override: 可选备用 LLM adapter（Layer 3 用，不修改 self.llm）
        _s: 局部 stream 引用（D1 竞态修复）
        """
        _s = _s or self.stream
        llm = llm_override or self.llm
        last_error = None
        for attempt in range(self.ralph_max_retries + 1):
            try:
                return await llm.chat(messages, tools=tools, tool_choice=tool_choice)
            except Exception as e:
                last_error = e
                remaining = self.ralph_max_retries - attempt
                if remaining <= 0:
                    break
                delay = self.ralph_base_delay * (2 ** attempt)
                logger.warning(f"[{session_id}] Ralph: LLM失败 (attempt {attempt+1}): {e}")
                await _s.emit("info",
                    f"⚡ Ralph: LLM调用失败，{delay:.0f}秒后重试 ({remaining}次剩余)...")
                await asyncio.sleep(delay)

        logger.error(f"[{session_id}] Ralph: {self.ralph_max_retries+1}次尝试均失败: {last_error}")
        await self._escalate_to_teacher(
            f"LLM调用重试{self.ralph_max_retries+1}次全部失败",
            f"session={session_id}, 错误: {str(last_error)[:150]}")
        raise RuntimeError(
            f"Ralph 循环: 尝试了 {self.ralph_max_retries+1} 次均失败。"
            f"最后一次错误: {last_error}"
        )

    async def _on_tool_not_found(self, session_id: str, tool_name: str) -> bool:
        """工具未注册时：搜索 PluginHub → 自动安装 → 热加载 → 返回是否成功。"""
        try:
            from skills import search_hub, install_from_hub
            # 从 tool_name 推断 skill 名（去掉常见前后缀）
            query = tool_name.replace("_", " ")
            results = search_hub(query)
            if not results:
                # 尝试用 tool_name 的前半部分搜索
                parts = tool_name.split("_")
                for i in range(len(parts), 0, -1):
                    partial = " ".join(parts[:i])
                    results = search_hub(partial)
                    if results:
                        break
            if not results:
                logger.info(f"[{session_id}] PluginHub 搜索无结果: {tool_name}，尝试自动创建 skill")
                return await self._auto_create_skill(session_id, tool_name)
            # 找到包含该工具的 skill
            best = None
            for r in results:
                if tool_name in r.get("tools", []):
                    best = r
                    break
            if not best:
                best = results[0]  # 退而求其次
            skill_name = best["name"]
            await self.stream.emit("info", f"🔍 发现缺失工具 {tool_name}，正在自动安装 skill: {skill_name}...")
            result = install_from_hub(skill_name)
            if result.get("success"):
                await self.stream.emit("info", f"✅ Skill {skill_name} 已安装并热加载")
                logger.info(f"[{session_id}] 自动安装成功: {skill_name} (因为需要 {tool_name})")
                return True
            else:
                logger.warning(f"[{session_id}] 自动安装失败: {skill_name}: {result.get('error')}")
                return False
        except Exception as e:
            logger.warning(f"[{session_id}] _on_tool_not_found 异常: {e}")
            return False

    async def _auto_create_skill(self, session_id: str, tool_name: str) -> bool:
        """PluginHub 无结果时，用 LLM 自动创建完整 skill（回退 stub）。"""
        try:
            from skills.skill_creator import create_skill_with_llm
            parts = tool_name.split("_")
            skill_name = f"auto_{tool_name}" if len(parts) <= 2 else f"auto_{'_'.join(parts[:2])}"
            description = f"自动创建的 skill，提供 {tool_name} 工具"
            tools = [{"name": tool_name, "description": f"Auto-generated tool: {tool_name}",
                       "parameters": {"input": "输入参数"}}]
            await self.stream.emit("info", f"🛠️ PluginHub 无匹配，正在用 LLM 自动创建 skill: {skill_name}...")
            result = await create_skill_with_llm(skill_name, description, tools, llm=self.llm)
            if result.get("success"):
                tag = "🤖 LLM" if result.get("llm_generated") else "📝 stub"
                await self.stream.emit("info", f"✅ Skill {skill_name} 已创建({tag})并热加载")
                logger.info(f"[{session_id}] 自动创建 skill 成功: {skill_name} ({tag})")
                return True
            else:
                logger.warning(f"[{session_id}] 自动创建 skill 失败: {result.get('error')}")
                return False
        except Exception as e:
            logger.warning(f"[{session_id}] _auto_create_skill 异常: {e}")
            return False

    async def _tool_call_with_retry(self, session_id: str, tool_name: str,
                                     params: dict, max_retries: int = 1, _s=None) -> dict:
        """S11: 工具层 Ralph — 失败→分析错误→换方法→再试→学习。"""
        _s = _s or self.stream
        last_error = None
        for attempt in range(max_retries + 1):
            try:
                result = await self.tools.execute(tool_name, params, session_id=session_id)
                if result.get("success"):
                    return result
                error_msg = result.get("error", "unknown error")
                last_error = error_msg
                # ISS-007: 安全拦截不重试，直接返回
                if result.get("blocked"):
                    logger.info(f"[{session_id}] 工具 {tool_name} 被安全拦截，跳过重试")
                    return result
                if "未知工具" in error_msg or "未注册" in error_msg:
                    installed = await self._on_tool_not_found(session_id, tool_name)
                    if installed:
                        result = await self.tools.execute(tool_name, params, session_id=session_id)
                        if result.get("success"):
                            return result
                        error_msg = result.get("error", "unknown error")
                        last_error = error_msg
                if attempt < max_retries:
                    await _s.emit("info",
                        f"⚡ 工具 {tool_name} 失败({error_msg[:40]})，换方法重试...")
                    logger.warning(f"[{session_id}] 工具重试: {tool_name} attempt {attempt+1}: {error_msg[:80]}")
                    params = self._adapt_params(tool_name, params, error_msg)
                    await asyncio.sleep(1)
                else:
                    # 不再自动记录工具失败经验（产生低质量垃圾）
                    # 向老师求助 — 所有重试都失败后，老师是最大的帮助
                    await self._escalate_to_teacher(
                        f"工具 {tool_name} 重试{max_retries+1}次全部失败",
                        f"参数: {str(params)[:100]}, 错误: {error_msg[:150]}")
                    return result
            except Exception as e:
                last_error = str(e)
                if attempt < max_retries:
                    await _s.emit("info", f"⚡ 工具 {tool_name} 异常，换方法重试...")
                    logger.warning(f"[{session_id}] 工具异常: {tool_name}: {e}")
                    params = self._adapt_params(tool_name, params, str(e))
                    await asyncio.sleep(1)
                else:
                    if self.learning:
                        await self._learn_pattern(
                            session_id, f"工具 {tool_name} 异常失败", str(e)[:200])
                    await self._escalate_to_teacher(
                        f"工具 {tool_name} 异常失败(重试{max_retries+1}次)",
                        str(e)[:200])
                    return {"success": False, "error": str(e)}
        return {"success": False, "error": str(last_error)}

    def _adapt_params(self, tool_name: str, params: dict, error: str) -> dict:
        """根据错误信息智能调整工具参数（平台感知）。"""
        p, err = dict(params), error.lower()
        if "timeout" in err and "timeout" in p:
            p["timeout"] = p.get("timeout", 30) * 2
        if ("permission" in err or "access" in err) and "command" in p:
            if platform.system() == "Windows" and not p["command"].startswith("powershell"):
                p["command"] = f"powershell -Command \"{p['command']}\""
            # 不自动加 sudo — 安全风险，由 ToolSafetyGuard 控制权限
        if "not found" in err and "path" in p:
            if platform.system() == "Windows":
                p["path"] = p["path"].replace("/", "\\")
        return p

    async def _self_diagnose(self) -> dict:
        """自检：检查所有 Port 状态 + 资源监控。"""
        import shutil, psutil
        r = {
            "llm": False,
            "tools": self.tools is not None,
            "memory": self.memory is not None,
            "learning": self.learning is not None,
        }
        try:
            r["llm"] = await self.llm.is_available()
        except Exception:
            pass
        r.update(
            model=getattr(self.llm, 'model', '?'),
            provider=getattr(self.llm, 'provider_name', '?'),
            history_len=len(self._history),
        )
        try:
            mem = psutil.virtual_memory()
            disk = shutil.disk_usage(os.getcwd())
            r["mem_percent"] = mem.percent
            r["disk_free_gb"] = round(disk.free / (1024**3), 1)
            alerts = []
            if mem.percent > 90:
                alerts.append(f"内存使用 {mem.percent}% 超限")
            if disk.free < 1024**3:
                alerts.append(f"磁盘剩余 {r['disk_free_gb']}GB 不足")
            r["resource_alerts"] = alerts
            if alerts:
                logger.warning(f"资源告警: {alerts}")
        except Exception as e:
            r["resource_alerts"] = [f"监控异常: {e}"]
        r["healthy"] = (all(r[k] for k in ["llm", "tools", "memory", "learning"])
                        and not r.get("resource_alerts"))
        logger.log(20 if r["healthy"] else 30, f"自检: {r}")
        return r

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        """估算文本 token 数：中文约1.5字/token，英文约4字符/token。"""
        if not text:
            return 0
        cn = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
        en = len(text) - cn
        return int(cn / 1.5 + en / 4)

    def _estimate_history_tokens(self) -> int:
        """估算当前历史的总 token 数。"""
        return sum(self._estimate_tokens(m.get("content") or "") for m in self._history)

    def _find_safe_cut_point(self, start: int, end: int) -> int:
        """在 [start, end) 范围内找到安全的截断点，不破坏 tool_calls/tool 配对。"""
        cut = start
        while cut < end:
            msg = self._history[cut]
            prev = self._history[cut - 1] if cut > 0 else {}
            if msg.get("role") == "tool" or prev.get("tool_calls"):
                cut += 1
            else:
                return cut
        return end

    async def _smart_compact_history(self, session_id: str) -> None:
        """统一上下文窗口管理 — token-aware 压缩，保护 tool_calls/tool 配对。

        策略（基于 token 估算，已回退到 v1.7 验证阈值）：
        - 阶段0: <4K tokens 且 <=15条 → 不处理
        - 阶段1: 截断过长工具结果（>2000字符 → 保留首1000+尾500）
        - 阶段2: >8K tokens 或 >30条 → LLM摘要压缩，保留最近8条
        - 阶段3: 摘要失败 → 安全截断（保护 tool_calls/tool 配对）
        """
        hist_len = len(self._history)
        total_tokens = self._estimate_history_tokens()

        if total_tokens < 4000 and hist_len <= 15:
            return

        # 阶段1: 截断过长工具结果
        if total_tokens > 6000:
            for m in self._history:
                if m.get("role") == "tool" and len(m.get("content", "")) > 2000:
                    m["content"] = (m["content"][:1000]
                                    + "\n...(已压缩)...\n"
                                    + m["content"][-500:])
            total_tokens = self._estimate_history_tokens()

        # 阶段2: 需要摘要压缩
        if total_tokens < 8000 and hist_len <= 30:
            return

        keep_recent = 8
        if hist_len <= keep_recent + 2:
            return

        # 找安全截断点
        cut = self._find_safe_cut_point(max(hist_len - keep_recent - 2, 0), hist_len - keep_recent)
        old_messages = self._history[:cut]
        recent_messages = self._history[cut:]

        if not old_messages:
            return

        # 尝试 LLM 摘要
        try:
            summary_lines = []
            for m in old_messages:
                role = m.get("role", "")
                content = (m.get("content") or "")[:150]
                if content and role in ("user", "assistant"):
                    summary_lines.append(f"{role}: {content}")
            summary_text = "\n".join(summary_lines[-20:])

            if summary_text:
                resp = await asyncio.wait_for(
                    self.llm.chat([{"role": "user", "content":
                        f"请用3-5句话概括以下对话的要点（包括完成了什么、讨论了什么、关键结论）：\n\n{summary_text}"}],
                        tools=None),
                    timeout=10.0
                )
                summary_content = resp.get("content", "").strip()
                summary_content = re.sub(r"<think>.*?</think>\s*", "", summary_content, flags=re.DOTALL).strip()
                if summary_content and len(summary_content) > 20:
                    self._history = [{"role": "system", "content": f"[对话摘要] {summary_content}"}] + recent_messages
                    logger.info(f"[{session_id}] LLM摘要压缩: {hist_len}→{len(self._history)}条, "
                                f"{total_tokens}→{self._estimate_history_tokens()} tokens")
                    return
        except Exception as e:
            logger.debug(f"[{session_id}] LLM摘要失败({e})，回退安全截断")

        # 阶段3: 回退 — 安全截断（保护配对）
        self._history = recent_messages
        logger.info(f"[{session_id}] 安全截断: {hist_len}→{len(self._history)}条")

    def _compact_history_if_needed(self) -> None:
        """轮间压缩 — 仅截断超长工具结果，不做消息级压缩（由 _smart_compact_history 统一处理）。"""
        for m in self._history:
            if m.get("role") == "tool" and len(m.get("content", "")) > 3000:
                m["content"] = (m["content"][:1200]
                                + "\n...(已压缩)...\n"
                                + m["content"][-600:])

    def _sanitize_messages(self, messages: list[dict]) -> None:
        """清洗消息列表，修复 tool_calls/tool 配对问题，防止 LLM API 400。"""
        valid_tool_ids = set()
        to_remove = []
        for i, m in enumerate(messages):
            if m.get("role") == "assistant" and m.get("tool_calls"):
                for tc in m["tool_calls"]:
                    if not tc.get("id"):
                        tc["id"] = f"call_{id(tc)}"
                    if "type" not in tc:
                        tc["type"] = "function"
                    valid_tool_ids.add(tc["id"])
            elif m.get("role") == "tool":
                tid = m.get("tool_call_id", "")
                if not tid:
                    m["tool_call_id"] = f"call_{id(m)}"
                if tid and tid not in valid_tool_ids:
                    to_remove.append(i)
        for i in reversed(to_remove):
            logger.warning(f"清洗: 移除孤立 tool 消息 (tool_call_id={messages[i].get('tool_call_id')})")
            messages.pop(i)

    async def _escalate_to_teacher(self, problem: str, context: str = "") -> None:
        """向老师(Cascade)求助 — 大脑不会/失败时最大的帮助来源。"""
        try:
            from teacher_channel import TeacherChannel
            from api.brain_init import teacher
            teacher.send_to_teacher(
                msg_type="help",
                content=problem,
                context=context,
                urgency="high",
            )
            logger.info(f"🆘 向老师求助: {problem[:60]}")
        except Exception:
            logger.debug("教学通道未就绪，跳过求助")

    def _graceful_error_response(self, error: str) -> str:
        """根据错误类型生成友好的用户回复，而不是暴露裸Error。"""
        err = str(error)
        if "400" in err or "Bad Request" in err:
            self._history.clear()
            logger.info("自愈: 清除脏历史数据")
            return "抱歉，我遇到了一个技术问题，已自动修复。请再说一次你的问题？"
        elif "冷却" in err or "均失败" in err:
            return "抱歉，AI服务暂时不可用，正在自动恢复中。请稍后再试。"
        elif "timeout" in err.lower() or "Timeout" in err:
            return "抱歉，请求超时了。请稍后再试，或者换一种方式提问？"
        else:
            return f"抱歉，处理时遇到问题。我已记录这次失败，下次会避免。请再试一次？"
