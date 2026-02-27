"""Fallback LLM Adapter — 多模型自动切换 + SpecialKB 智能路由。

对标 OpenClaw model-fallback.ts (469行)。
超越维度: 透明告知切换 + SpecialKB 缓存省 token + 简洁。

智能路由逻辑：
1. 用户提问 → 查 SpecialKB → 有缓存 → 本地模型+参考答案（省 token）
2. 外部模型回答后 → 记录到 SpecialKB
3. 重复问题不再消耗外部 token
"""

import asyncio
import time
from typing import Any, AsyncIterator

from ports.llm_port import LLMPort
from logs import get_logger

logger = get_logger("llm")

_TRANSIENT_KEYWORDS = ["timeout", "rate_limit", "429", "503", "502", "connection", "reset", "refused"]


class FallbackLLMAdapter(LLMPort):
    """多模型 fallback + SpecialKB 智能路由。"""

    def __init__(self, primary: LLMPort, fallbacks: list[LLMPort] | None = None,
                 special_kb=None):
        self._primary = primary
        self._fallbacks = fallbacks or []
        self._all = [primary] + self._fallbacks
        self._kb = special_kb  # SpecialKB 实例
        self._health: dict[str, dict] = {}  # provider健康状态
        for a in self._all:
            name = getattr(a, "model", "?")
            self._health[name] = {"failures": 0, "last_fail": 0, "cooldown": 0}
        names = list(self._health.keys())
        logger.info(f"初始化: 主模型={names[0]}, 备用={names[1:]}, KB={'ON' if self._kb else 'OFF'}")

    @property
    def model(self) -> str:
        return getattr(self._primary, "model", "unknown")

    def set_primary(self, adapter: LLMPort) -> None:
        """切换主模型：将指定 adapter 设为 primary，其余为 fallback。"""
        if adapter not in self._all:
            self._all.append(adapter)
        self._primary = adapter
        self._fallbacks = [a for a in self._all if a is not adapter]
        self._all = [adapter] + self._fallbacks
        logger.info(f"主模型已切换: {getattr(adapter, 'model', '?')}")

    def _extract_user_question(self, messages: list[dict]) -> str:
        """提取最后一条用户消息。"""
        for m in reversed(messages):
            if m.get("role") == "user" and m.get("content"):
                return m["content"]
        return ""

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        stream: bool = False,
        **kwargs,
    ) -> dict[str, Any] | AsyncIterator[str]:
        question = self._extract_user_question(messages)

        # S16: SpecialKB 智能路由 — 缓存命中时用本地模型+参考答案
        if self._kb and question and not tools and self._fallbacks:
            cached = self._kb.lookup(question)
            if cached and cached.get("quality", 0) >= 0.7:
                logger.info(f"SpecialKB 命中: '{question[:40]}...' (quality={cached['quality']}, asks={cached['ask_count']})")
                # 注入参考答案到 system prompt，让本地模型参考
                kb_hint = f"\n\n## 参考答案（来自之前的优质回答，请参考但可以改进）\n{cached['answer'][:2000]}"
                enhanced = list(messages)
                if enhanced and enhanced[0].get("role") == "system":
                    enhanced[0] = {**enhanced[0], "content": enhanced[0]["content"] + kb_hint}
                else:
                    enhanced.insert(0, {"role": "system", "content": kb_hint})
                # 用本地模型回答
                local = self._fallbacks[0]
                local_name = getattr(local, "model", "local")
                try:
                    result = await local.chat(enhanced, tools=tools, stream=stream, **kwargs)
                    logger.info(f"SpecialKB 路由成功: 本地模型 {local_name} 使用缓存回答 (省外部token)")
                    self._kb.boost_quality(question)
                    return result
                except Exception as e:
                    logger.warning(f"SpecialKB 本地回答失败: {e}, 回退到外部模型")

        # S26: 增强 fallback — 健康检查 + 瞬态重试 + 错误分类
        # 自我保护：如果所有模型都在冷却，等待冷却结束而不是直接报错死掉
        all_cooling = all(
            self._health.get(getattr(a, "model", f"a-{i}"), {}).get("failures", 0) >= 3
            and time.time() - self._health.get(getattr(a, "model", f"a-{i}"), {}).get("last_fail", 0) < 60
            for i, a in enumerate(self._all)
        )
        if all_cooling:
            oldest_fail = min(
                self._health.get(getattr(a, "model", f"a-{i}"), {}).get("last_fail", 0)
                for i, a in enumerate(self._all)
            )
            wait_secs = max(1, 60 - (time.time() - oldest_fail))
            logger.warning(f"所有模型冷却中，等待 {wait_secs:.0f}s 后自动恢复（自我保护）")
            await asyncio.sleep(wait_secs + 2)
            for h in self._health.values():
                h["failures"] = 0

        errors = []
        for i, adapter in enumerate(self._all):
            model_name = getattr(adapter, "model", f"adapter-{i}")
            h = self._health.get(model_name, {"failures": 0, "last_fail": 0, "cooldown": 0})
            # 冷却期内跳过（连续失败3次后冷却60秒，冷却结束后重置计数器重新尝试）
            if h["failures"] >= 3:
                if time.time() - h["last_fail"] < 60:
                    logger.info(f"跳过 {model_name}: 冷却中 ({h['failures']}次失败)")
                    errors.append(f"{model_name}: 冷却中")
                    continue
                else:
                    h["failures"] = 0  # 冷却结束，重置计数器，给模型重新尝试的机会
            # 本地模型：精简工具数量+描述（省token给回复）
            call_tools = tools
            is_local = getattr(adapter, "_is_local", False)
            if is_local and tools:
                core = ["run_command","read_file","write_file","list_directory","web_search","grep",
                         "introspect","teaching","cascade_communicate","doubao_communicate",
                         "weather","system_monitor","clipboard","notify","scheduler"]
                filtered = [t for t in tools if t.get("function",{}).get("name","") in core]
                call_tools = [self._slim_tool(t) for t in (filtered if len(tools) > 15 else tools)]
                logger.info(f"本地模型工具精简: {len(tools)}→{len(call_tools)}")
            # 尝试调用（瞬态错误重试1次）
            for attempt in range(2):
                try:
                    result = await adapter.chat(messages, tools=call_tools, stream=stream, **kwargs)
                    if i > 0: logger.info(f"Fallback 成功: 使用备用模型 {model_name}")
                    h["failures"] = 0  # 成功则重置
                    if i == 0 and not stream:
                        answer = result.get("content", "")
                        if self._kb and question and answer and len(answer) > 20:
                            self._kb.record(question, answer, model_name)
                        # 微调数据收集：外部大模型成功回复时记录
                        if answer and not is_local:
                            try:
                                from finetune_collector import collect
                                collect(messages, result, model_name)
                            except Exception:
                                pass
                    return result
                except Exception as e:
                    err_str = str(e).lower()
                    # 模型不支持 tools → 去掉 tools 参数重试（不算失败）
                    tools_unsupported = (
                        "does not support tools" in err_str
                        or (is_local and "400" in err_str and call_tools)
                    )
                    if tools_unsupported and call_tools and attempt == 0:
                        logger.info(f"{model_name} 不支持 tools (或400错误), 去掉工具参数重试")
                        call_tools = None
                        continue
                    is_transient = any(k in err_str for k in _TRANSIENT_KEYWORDS)
                    if is_transient and attempt == 0:
                        logger.info(f"{model_name} 瞬态错误, 1秒后重试: {e}")
                        await asyncio.sleep(1)
                        continue
                    h["failures"] += 1
                    h["last_fail"] = time.time()
                    errors.append(f"{model_name}: {e}")
                    logger.warning(f"模型 {model_name} 失败(#{h['failures']}): {e}")
                    break
            if i < len(self._all) - 1:
                next_name = getattr(self._all[i + 1], "model", "?")
                logger.info(f"切换到备用模型: {next_name}")

        raise RuntimeError(f"所有模型均失败: " + " | ".join(errors))

    @staticmethod
    def _slim_tool(tool: dict) -> dict:
        """精简工具定义：截断描述，移除optional参数，省token。"""
        import copy
        t = copy.deepcopy(tool)
        func = t.get("function", {})
        if func.get("description"):
            func["description"] = func["description"][:60]
        params = func.get("parameters", {})
        props = params.get("properties", {})
        required = set(params.get("required", []))
        # 移除 optional 参数，只保留 required
        if required and len(props) > len(required):
            func["parameters"]["properties"] = {k: v for k, v in props.items() if k in required}
        # 截断参数描述
        for v in func.get("parameters", {}).get("properties", {}).values():
            if v.get("description"):
                v["description"] = v["description"][:30]
        return t

    def get_health(self) -> dict:
        """返回所有模型的健康状态，供 API 暴露。"""
        models = []
        for adapter in self._all:
            name = getattr(adapter, "model", "?")
            is_local = getattr(adapter, "_is_local", False)
            h = self._health.get(name, {"failures": 0, "last_fail": 0})
            cooling = h["failures"] >= 3 and (time.time() - h.get("last_fail", 0)) < 60
            models.append({
                "model": name, "local": is_local,
                "failures": h["failures"], "cooling": cooling,
            })
        return {
            "local_only": self.is_local_only(),
            "models": models,
        }

    def is_local_only(self) -> bool:
        """检测是否只有本地模型可用（外部API全部冷却或失败）。"""
        for adapter in self._all:
            if not getattr(adapter, "_is_local", False):
                h = self._health.get(getattr(adapter, "model", "?"), {})
                if h.get("failures", 0) < 3:
                    return False
        return True

    async def is_available(self) -> bool:
        for adapter in self._all:
            if await adapter.is_available():
                return True
        return False
