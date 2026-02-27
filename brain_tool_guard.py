"""Brain 工具守卫 Mixin — 空承诺检测 + 三层防护 + 防伪造。

从 brain.py 拆出以遵守规则03行数限制。
三层防护:
  Layer 1: 从文本提取工具意图并直接执行
  Layer 2: tool_choice="required" 强制工具调用
  Layer 3: 切换到更强FC模型重试（通过 llm_override，不修改 self.llm）
"""

import json
import re
import time

from logs import get_logger
from brain_perf import compress_tool_result

logger = get_logger("brain")


class BrainToolGuardMixin:
    """空承诺检测与三层防护。混入 Brain 类。"""

    # === 空承诺检测 ===
    _PROMISE_PATTERNS = [
        "正在尝试", "我来试试", "我去试", "让我试", "我试试",
        "正在利用工具", "正在使用工具", "我来用工具", "让我用",
        "正在执行", "正在处理", "马上", "立刻", "我来帮你",
        "好的，让我", "好的，我来", "好的老大", "好的，老大",
        "正在调用", "正在搜索", "正在查找", "正在查询",
        "请稍等", "稍等", "正在努力", "我正在",
        "I'll try", "Let me try", "I'm working on", "I'm searching",
    ]

    def _detect_empty_promise(self, reply_text: str) -> bool:
        """检测 LLM 回复是否包含行动承诺但实际未调用任何工具。"""
        text = reply_text.strip()
        if not text or len(text) > 500:
            return False
        return any(p in text for p in self._PROMISE_PATTERNS)

    # === 强FC模型查找 ===
    def _get_stronger_fc_model(self):
        """获取 function calling 能力更强的备用模型。
        当前模型如果已经是强FC模型则返回 None。"""
        current = getattr(self.llm, "model", "")
        if any(s in current.lower() for s in ("deepseek", "gpt-4")):
            return None
        fallback_llm = self.llm
        if hasattr(fallback_llm, "_all"):
            for adapter in fallback_llm._all:
                model_name = getattr(adapter, "model", "")
                if any(s in model_name.lower() for s in ("deepseek", "gpt-4")):
                    h = fallback_llm._health.get(model_name, {})
                    if h.get("failures", 0) < 3:
                        return adapter
        elif hasattr(fallback_llm, "_primary"):
            primary = fallback_llm._primary
            model_name = getattr(primary, "model", "")
            if any(s in model_name.lower() for s in ("deepseek", "gpt-4")):
                return primary
        return None

    # === 文本意图提取 ===
    def _extract_tool_intent_from_text(self, reply_text: str) -> dict | None:
        """从 LLM 文本回复中提取工具调用意图。
        返回 {"name": str, "arguments": dict} 或 None。"""
        text = reply_text.strip()
        # 模式: "正在调用 web_search 搜索关于 'xxx' 的信息"
        m = re.search(
            r'(?:正在调用|调用|使用)\s*(\w+)\s*(?:搜索|查询|查找|获取).*?[\'""「]([^\'""」]+)[\'""」]',
            text,
        )
        if m:
            tool_name = m.group(1)
            query = m.group(2)
            if tool_name in ("web_search", "search"):
                return {"name": "web_search", "arguments": {"query": query}}
        # 模式: "搜索 'xxx'"
        m = re.search(r'(?:搜索|查询|查找)\s*[\'""「]([^\'""」]+)[\'""」]', text)
        if m and "web_search" in text:
            return {"name": "web_search", "arguments": {"query": m.group(1)}}
        # 模式: "执行命令 'xxx'" 或 "运行 'xxx'"
        m = re.search(r'(?:执行命令|运行命令|执行|运行)\s*[\'""「`]([^\'""」`]+)[\'""」`]', text)
        if m:
            return {"name": "run_command", "arguments": {"command": m.group(1)}}
        return None

    # === 三层防护主方法 ===
    async def _guard_empty_promise(
        self, session_id: str, user_input: str, response: dict,
        messages: list, tools: list | None, _s=None,
    ) -> tuple[dict, bool]:
        """空承诺三层防护。返回 (可能更新的response, tool_calls_happened)。

        Layer 1: 从文本提取工具意图并直接执行
        Layer 2: tool_choice="required" 强制LLM产生工具调用
        Layer 3: 切换到更强FC模型重试（通过 llm_override）
        """
        _s = _s or self.stream
        content_text = response.get("content", "") or ""
        if not self._detect_empty_promise(content_text):
            return response, False

        logger.warning(f"[{session_id}] 空承诺检测: '{content_text[:60]}...'")
        await _s.emit("info", "🔄 检测到承诺未兑现，正在重试...")

        # Layer 1: 文本意图提取
        intent = self._extract_tool_intent_from_text(content_text)
        if intent and self.tools:
            t_name = intent["name"]
            t_params = intent["arguments"]
            logger.info(f"[{session_id}] Layer1: 从文本提取 {t_name}({t_params})")
            try:
                result = await self._tool_call_with_retry(session_id, t_name, t_params, _s=_s)
                r_text = str(result.get("result") or result.get("error") or "")
                if not r_text.strip():
                    r_text = "(Command executed with no output)"
                r_text = compress_tool_result(r_text)
                tc_id = f"extracted_{t_name}"
                formatted_tc = {"id": tc_id, "type": "function",
                    "function": {"name": t_name, "arguments": json.dumps(t_params, ensure_ascii=False)}}
                self._history.append({"role": "assistant", "content": None, "tool_calls": [formatted_tc]})
                self._history.append({"role": "tool", "tool_call_id": tc_id, "content": r_text})
                await _s.emit("tool_call", f"{t_name}({json.dumps(t_params, ensure_ascii=False)[:100]})")
                await _s.emit("tool_result", r_text[:200])
                self._compact_history_if_needed()
                messages = await self._build_messages()
                response = await self._llm_call_with_retry(session_id, messages, tools=None, _s=_s)
                return response, True
            except Exception:
                pass

        # Layer 2: tool_choice="required"
        logger.info(f"[{session_id}] Layer2: 使用 tool_choice=required 重试")
        try:
            response2 = await self._llm_call_with_retry(
                session_id, messages, tools, tool_choice="required", _s=_s,
            )
            if response2.get("tool_calls"):
                return response2, False  # caller will handle tool_calls
        except Exception:
            pass

        # Layer 3: 更强FC模型
        stronger = self._get_stronger_fc_model()
        if stronger:
            logger.info(f"[{session_id}] Layer3: 切换到 {getattr(stronger, 'model', '?')}")
            try:
                response3 = await self._llm_call_with_retry(
                    session_id, messages, tools,
                    tool_choice="required", llm_override=stronger, _s=_s,
                )
                if response3.get("tool_calls"):
                    return response3, False
            except Exception:
                pass

        logger.warning(f"[{session_id}] 三层防护均未成功")
        return response, False

    # === 防伪造守卫：检测并强制调用工具（后备方案） ===
    _FAKE_PATTERNS = [
        {
            "user_re": r"(\d+)\s*秒后[提醒叫]",
            "reply_re": r"已设置提醒|已设定提醒|提醒已设置",
            "tool": "set_reminder",
            "extract": lambda m, _: {"message": "提醒", "seconds": int(m.group(1))},
        },
        {
            "user_re": r"(\d+)\s*分钟?后[提醒叫]",
            "reply_re": r"已设置提醒|已设定提醒|提醒已设置",
            "tool": "set_reminder",
            "extract": lambda m, _: {"message": "提醒", "minutes": int(m.group(1))},
        },
        {
            "user_re": r"删除(.+?)(?:文件|的文件)",
            "reply_re": r"已删除|已确认.*删除|删除.*完成|文件.*已.*删除",
            "tool": "delete_file",
            "extract": lambda m, _: {"path": m.group(1).strip()},
        },
        {
            "user_re": r"(?:删掉|移除|去掉)(.+?)(?:文件)?$",
            "reply_re": r"已删除|已移除|已去掉|已清除|删除.*完成",
            "tool": "delete_file",
            "extract": lambda m, _: {"path": m.group(1).strip()},
        },
    ]

    # 通用伪造动作检测：用户要求执行操作 + LLM 声称完成但未调任何工具
    _ACTION_CLAIM_PATTERNS = re.compile(
        r"已(?:删除|移除|清除|完成|执行|创建|写入|保存|修改|更新|发送|设置|安装|卸载|停止|启动|重启)"
        r"|(?:删除|移除|执行|创建|写入|发送|设置|安装).*(?:完成|成功)"
        r"|(?:文件|目录|数据|配置|服务).*已.*(?:删除|创建|修改|更新)",
        re.IGNORECASE,
    )
    _ACTION_REQUEST_PATTERNS = re.compile(
        r"删除|移除|清除|创建|写入|修改|更新|发送|设置|安装|卸载|停止|启动|重启|运行|执行",
        re.IGNORECASE,
    )

    async def _force_tool_if_faked(self, session_id: str, user_input: str, reply_text: str, _s=None) -> bool:
        """检测 LLM 伪造工具结果并强制执行真实工具调用。返回 True 表示已强制执行。"""
        _s = _s or self.stream

        # Phase 1: 精确模式匹配（已知的伪造模式）
        for pat in self._FAKE_PATTERNS:
            user_match = re.search(pat["user_re"], user_input)
            if not user_match:
                continue
            if not re.search(pat["reply_re"], reply_text):
                continue
            tool_name = pat["tool"]
            msg_match = re.search(r"(?:提醒|叫)我?(.+?)$", user_input)
            params = pat["extract"](user_match, user_input)
            if msg_match:
                extracted = msg_match.group(1).strip()
                extracted = re.sub(r"^你", "", extracted).strip()
                if extracted:
                    params["message"] = extracted
            logger.warning(f"[{session_id}] 防伪造守卫: LLM 假装已调用 {tool_name}，强制执行")
            await _s.emit("info", "🛡️ 检测到未执行的操作，正在补救...")
            try:
                result = await self._tool_call_with_retry(session_id, tool_name, params, _s=_s)
                result_text = str(result.get("result") or result.get("error") or "")
                await _s.emit("tool_call", f"{tool_name}({json.dumps(params, ensure_ascii=False)})")
                await _s.emit("tool_result", result_text[:200])
                logger.info(f"[{session_id}] 防伪造守卫: {tool_name} 执行成功: {result_text[:80]}")
                self._history.append({"role": "assistant", "content": None, "tool_calls": [{
                    "id": f"forced_{tool_name}", "type": "function",
                    "function": {"name": tool_name, "arguments": json.dumps(params, ensure_ascii=False)},
                }]})
                self._history.append({"role": "tool", "tool_call_id": f"forced_{tool_name}", "content": result_text})
                return True
            except Exception as e:
                logger.error(f"[{session_id}] 防伪造守卫: {tool_name} 执行失败: {e}")
                return False

        # Phase 2: 通用伪造检测 — 用户要求操作 + LLM 声称完成但无工具调用
        if (self._ACTION_REQUEST_PATTERNS.search(user_input)
                and self._ACTION_CLAIM_PATTERNS.search(reply_text)):
            logger.warning(f"[{session_id}] 通用防伪造: 用户要求操作且 LLM 声称完成但未调用工具")
            await _s.emit("info", "🛡️ 检测到声称完成但未使用工具，正在强制重试...")
            # 注入纠正提示，让 LLM 用真实工具重做
            self._history.append({
                "role": "user",
                "content": (
                    "[系统] 你刚才声称已完成操作，但实际上没有调用任何工具。"
                    "你必须使用真实的工具来执行操作，不能假装已完成。"
                    "请使用可用的工具来执行用户的请求。如果没有合适的工具，请如实告知。"
                ),
            })
            return True  # 触发 caller 重新进入工具循环

        return False
