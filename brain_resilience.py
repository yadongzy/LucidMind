"""Brain Resilience Mixin — 自愈/重试/自检/压缩/消息清洗方法。

从 brain.py 拆分，保持 Brain 核心精简。
包含: LLM重试(Ralph)、工具重试、参数自适应、自检、历史压缩、消息清洗。

核心理念（第零条）：想尽一切办法完成任务 + 想尽一切办法保护自己。
"""

import asyncio
import os
import platform

from logs import get_logger

logger = get_logger("brain")


class BrainResilienceMixin:
    """韧性能力混入 — 让大脑能自愈、重试、自检。"""

    async def _llm_call_with_retry(self, session_id: str, messages: list, tools) -> dict:
        """S7 Ralph: LLM 调用失败时自动重试，每次重试透明告知用户。"""
        last_error = None
        for attempt in range(self.ralph_max_retries + 1):
            try:
                return await self.llm.chat(messages, tools=tools)
            except Exception as e:
                last_error = e
                remaining = self.ralph_max_retries - attempt
                if remaining <= 0:
                    break
                delay = self.ralph_base_delay * (2 ** attempt)
                logger.warning(f"[{session_id}] Ralph: LLM失败 (attempt {attempt+1}): {e}")
                await self.stream.emit("info",
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
        """PluginHub 无结果时，自动创建一个 stub skill。"""
        try:
            from skills.skill_creator import create_skill
            # 从 tool_name 推断 skill 名和描述
            parts = tool_name.split("_")
            # 用第一个词或前两个词作为 skill 名
            skill_name = f"auto_{tool_name}" if len(parts) <= 2 else f"auto_{'_'.join(parts[:2])}"
            description = f"自动创建的 skill，提供 {tool_name} 工具"
            tools = [{"name": tool_name, "description": f"Auto-generated tool: {tool_name}",
                       "parameters": {"input": "输入参数"}}]
            await self.stream.emit("info", f"🛠️ PluginHub 无匹配，正在自动创建 skill: {skill_name}...")
            result = create_skill(skill_name, description, tools)
            if result.get("success"):
                await self.stream.emit("info", f"✅ Skill {skill_name} 已自动创建并热加载")
                logger.info(f"[{session_id}] 自动创建 skill 成功: {skill_name}")
                return True
            else:
                logger.warning(f"[{session_id}] 自动创建 skill 失败: {result.get('error')}")
                return False
        except Exception as e:
            logger.warning(f"[{session_id}] _auto_create_skill 异常: {e}")
            return False

    async def _tool_call_with_retry(self, session_id: str, tool_name: str,
                                     params: dict, max_retries: int = 2) -> dict:
        """S11: 工具层 Ralph — 失败→分析错误→换方法→再试→学习。"""
        last_error = None
        for attempt in range(max_retries + 1):
            try:
                result = await self.tools.execute(tool_name, params, session_id=session_id)
                if result.get("success"):
                    return result
                error_msg = result.get("error", "unknown error")
                last_error = error_msg
                # 工具未注册 → 尝试自动搜索安装
                if "未知工具" in error_msg or "未注册" in error_msg:
                    installed = await self._on_tool_not_found(session_id, tool_name)
                    if installed:
                        # 安装成功，立即重试（不计入重试次数）
                        result = await self.tools.execute(tool_name, params, session_id=session_id)
                        if result.get("success"):
                            return result
                        error_msg = result.get("error", "unknown error")
                        last_error = error_msg
                if attempt < max_retries:
                    await self.stream.emit("info",
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
                    await self.stream.emit("info", f"⚡ 工具 {tool_name} 异常，换方法重试...")
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
            elif platform.system() != "Windows":
                if not p["command"].startswith("sudo "):
                    p["command"] = f"sudo {p['command']}"
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

    def _compact_history_if_needed(self) -> None:
        """S18-2: 智能历史压缩 — 工具截断 + 旧消息摘要（保护 tool_calls/tool 配对）。"""
        total = sum(len(m.get("content") or "") for m in self._history)
        # 阶段1: 截断过长工具结果
        if total > 30000:
            for m in self._history:
                if m.get("role") == "tool" and len(m.get("content", "")) > 2000:
                    m["content"] = (m["content"][:1000]
                                    + "\n...(已压缩)...\n"
                                    + m["content"][-500:])
        # 阶段2: 消息数>40 → 摘要压缩旧消息（保护 tool_calls/tool 配对）
        if len(self._history) > 40:
            cut = 20
            while cut < len(self._history) - 10:
                msg = self._history[cut]
                prev = self._history[cut - 1] if cut > 0 else {}
                if msg.get("role") == "tool" or prev.get("tool_calls"):
                    cut += 1
                else:
                    break
            old = self._history[:cut]
            summary_parts = []
            for m in old:
                r, c = m.get("role", ""), (m.get("content") or "")[:100]
                if c:
                    summary_parts.append(f"{r}: {c}")
            summary = f"对话摘要(前{cut}条):\n" + "\n".join(summary_parts[:10])
            self._history = [{"role": "system", "content": summary}] + self._history[cut:]
            logger.info(f"智能压缩: {len(old)}条旧消息→摘要, 剩余{len(self._history)}条")

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
