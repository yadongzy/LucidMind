"""Anthropic LLM Adapter — 通过 Anthropic Messages API 调用 MiniMax Coding Plan (M2.5)。

Coding Plan 的 sk-cp- Key 专用于 Anthropic 兼容端点:
  base_url = https://api.minimax.io/anthropic
  
本 adapter 将 LucidMind 内部的 OpenAI 风格消息/工具格式
转换为 Anthropic Messages API 格式，返回时再转回 OpenAI 风格。

格式转换:
  OpenAI tools → Anthropic tools (function.parameters → input_schema)
  Anthropic tool_use blocks → OpenAI tool_calls [{id, function:{name, arguments}}]
"""

import json
import time
from typing import Any, AsyncIterator

import httpx

from ports.llm_port import LLMPort
from logs import get_logger

logger = get_logger("llm.anthropic")

_ANTHROPIC_VERSION = "2023-06-01"


class AnthropicAdapter(LLMPort):
    """Anthropic Messages API 适配器。用于 MiniMax Coding Plan (sk-cp- Key)。"""

    def __init__(
        self,
        api_key: str = "",
        base_url: str = "https://api.minimax.io/anthropic",
        model: str = "MiniMax-M2.5",
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self._is_local = False
        self._timeout = 120
        self._actual_model: str | None = None

        if not self.api_key:
            logger.warning("初始化: MINIMAX_API_KEY 未设置 (Anthropic adapter)")
        else:
            logger.info(f"初始化: Anthropic adapter, 模型={self.model}, 基址={self.base_url}")

    # ── 格式转换: OpenAI → Anthropic ──

    @staticmethod
    def _convert_tools_to_anthropic(tools: list[dict]) -> list[dict]:
        """OpenAI function-calling tools → Anthropic tools 格式。
        
        OpenAI:  {"type":"function","function":{"name":"x","description":"y","parameters":{...}}}
        Anthropic: {"name":"x","description":"y","input_schema":{...}}
        """
        result = []
        for t in tools:
            func = t.get("function", t)  # 兼容直接传 function dict
            entry = {
                "name": func.get("name", ""),
                "description": func.get("description", "")[:1024],
                "input_schema": func.get("parameters", {"type": "object", "properties": {}}),
            }
            result.append(entry)
        return result

    @staticmethod
    def _convert_messages_to_anthropic(messages: list[dict]) -> tuple[str, list[dict]]:
        """OpenAI messages → Anthropic (system, messages) 格式。
        
        - system 消息提取为顶层 system 参数
        - tool 结果消息转为 Anthropic 的 tool_result content block
        - assistant 带 tool_calls 的消息转为 tool_use content blocks
        """
        system_parts = []
        anthropic_msgs = []

        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "") or ""

            if role == "system":
                system_parts.append(content)
                continue

            if role == "user":
                anthropic_msgs.append({"role": "user", "content": content})
                continue

            if role == "assistant":
                # 检查是否有 tool_calls（需要转为 tool_use blocks）
                tool_calls = msg.get("tool_calls")
                if tool_calls:
                    blocks = []
                    if content:
                        blocks.append({"type": "text", "text": content})
                    for tc in tool_calls:
                        func = tc.get("function", {})
                        args = func.get("arguments", "{}")
                        if isinstance(args, str):
                            try:
                                args = json.loads(args)
                            except json.JSONDecodeError:
                                args = {"raw": args}
                        blocks.append({
                            "type": "tool_use",
                            "id": tc.get("id", ""),
                            "name": func.get("name", ""),
                            "input": args,
                        })
                    anthropic_msgs.append({"role": "assistant", "content": blocks})
                else:
                    anthropic_msgs.append({"role": "assistant", "content": content})
                continue

            if role == "tool":
                # OpenAI tool result → Anthropic tool_result content block
                tool_call_id = msg.get("tool_call_id", "")
                anthropic_msgs.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": tool_call_id,
                        "content": content,
                    }],
                })
                continue

            # 未知 role，作为 user 处理
            if content:
                anthropic_msgs.append({"role": "user", "content": content})

        # Anthropic 要求消息交替 user/assistant，合并连续同角色消息
        anthropic_msgs = AnthropicAdapter._merge_consecutive_roles(anthropic_msgs)

        return "\n\n".join(system_parts), anthropic_msgs

    @staticmethod
    def _merge_consecutive_roles(messages: list[dict]) -> list[dict]:
        """合并连续同角色消息（Anthropic 要求严格交替）。"""
        if not messages:
            return messages
        merged = [messages[0]]
        for msg in messages[1:]:
            if msg["role"] == merged[-1]["role"]:
                # 合并 content
                prev_content = merged[-1]["content"]
                curr_content = msg["content"]
                if isinstance(prev_content, str) and isinstance(curr_content, str):
                    merged[-1]["content"] = prev_content + "\n\n" + curr_content
                elif isinstance(prev_content, list) and isinstance(curr_content, list):
                    merged[-1]["content"] = prev_content + curr_content
                elif isinstance(prev_content, str) and isinstance(curr_content, list):
                    merged[-1]["content"] = [{"type": "text", "text": prev_content}] + curr_content
                elif isinstance(prev_content, list) and isinstance(curr_content, str):
                    merged[-1]["content"] = prev_content + [{"type": "text", "text": curr_content}]
            else:
                merged.append(msg)
        return merged

    # ── 格式转换: Anthropic → OpenAI ──

    @staticmethod
    def _convert_response_to_openai(data: dict) -> dict[str, Any]:
        """Anthropic Messages response → OpenAI 风格 result dict。
        
        Anthropic content blocks:
          - {"type":"text","text":"..."} → content
          - {"type":"thinking","thinking":"..."} → reasoning_content
          - {"type":"tool_use","id":"...","name":"...","input":{...}} → tool_calls
        """
        content_parts = []
        tool_calls = []
        reasoning = []

        for block in data.get("content", []):
            btype = block.get("type", "")
            if btype == "text":
                content_parts.append(block.get("text", ""))
            elif btype == "thinking":
                reasoning.append(block.get("thinking", ""))
            elif btype == "tool_use":
                tool_calls.append({
                    "id": block.get("id", ""),
                    "function": {
                        "name": block.get("name", ""),
                        "arguments": json.dumps(block.get("input", {}), ensure_ascii=False),
                    },
                })

        result: dict[str, Any] = {
            "content": "\n".join(content_parts),
            "model": data.get("model", ""),
        }

        if tool_calls:
            result["tool_calls"] = tool_calls

        if reasoning:
            result["reasoning_content"] = "\n".join(reasoning)

        usage = data.get("usage", {})
        if usage:
            u = {
                "prompt_tokens": usage.get("input_tokens", 0),
                "completion_tokens": usage.get("output_tokens", 0),
                "total_tokens": usage.get("input_tokens", 0) + usage.get("output_tokens", 0),
            }
            result["usage"] = u
            try:
                from token_tracker import get_tracker
                get_tracker().record(
                    model=self.model, provider=getattr(self, "provider_name", "minimax"),
                    prompt_tokens=u["prompt_tokens"],
                    completion_tokens=u["completion_tokens"],
                    total_tokens=u["total_tokens"],
                )
            except Exception:
                pass

        return result

    # ── 主调用方法 ──

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        stream: bool = False,
        **kwargs,
    ) -> dict[str, Any] | AsyncIterator[str]:
        """调用 Anthropic Messages API。"""

        if stream:
            return self._stream_chat(messages, tools, **kwargs)

        return await self._non_stream_chat(messages, tools, **kwargs)

    async def _non_stream_chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        **kwargs,
    ) -> dict[str, Any]:
        """非流式调用 Anthropic Messages API。"""
        t0 = time.time()

        system_prompt, anthropic_messages = self._convert_messages_to_anthropic(messages)

        headers = {
            "Content-Type": "application/json",
            "x-api-key": self.api_key,
            "anthropic-version": _ANTHROPIC_VERSION,
        }

        body: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": anthropic_messages,
        }

        if system_prompt:
            body["system"] = system_prompt

        if tools:
            body["tools"] = self._convert_tools_to_anthropic(tools)
            tool_choice = kwargs.get("tool_choice")
            if tool_choice == "required":
                body["tool_choice"] = {"type": "any"}
            elif tool_choice == "none":
                body["tool_choice"] = {"type": "none"}
            # "auto" 是默认值，不需要设置

        msg_count = len(anthropic_messages)
        last_msg = ""
        if anthropic_messages:
            lm = anthropic_messages[-1].get("content", "")
            if isinstance(lm, str):
                last_msg = lm[:80]
            elif isinstance(lm, list) and lm:
                last_msg = str(lm[0])[:80]
        logger.info(f"调用开始: 模型={self.model}, 消息数={msg_count}, 最后一条={last_msg}")

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(
                    f"{self.base_url}/v1/messages",
                    json=body,
                    headers=headers,
                )
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPStatusError as e:
            elapsed = time.time() - t0
            logger.error(f"调用失败: HTTP {e.response.status_code}, 耗时={elapsed:.1f}s, 响应={e.response.text[:300]}")
            raise
        except Exception as e:
            elapsed = time.time() - t0
            logger.error(f"调用失败: {type(e).__name__}: {e}, 耗时={elapsed:.1f}s")
            raise

        elapsed = time.time() - t0

        # 记录真实模型名
        actual_model = data.get("model", self.model)
        if actual_model != self.model:
            logger.info(f"实际模型: 请求={self.model}, 返回={actual_model}")
        self._actual_model = actual_model

        # 转换为 OpenAI 风格结果
        result = self._convert_response_to_openai(data)
        result["model"] = actual_model

        # 日志
        tc_count = len(result.get("tool_calls", []))
        usage = result.get("usage", {})
        if tc_count:
            logger.info(f"调用完成: 耗时={elapsed:.1f}s, 工具调用={tc_count}个")
        if usage:
            logger.info(
                f"调用完成: 耗时={elapsed:.1f}s, "
                f"tokens(prompt={usage.get('prompt_tokens',0)}, "
                f"completion={usage.get('completion_tokens',0)}, "
                f"total={usage.get('total_tokens',0)}), "
                f"回复摘要={result['content'][:80]}"
            )
        else:
            logger.info(f"调用完成: 耗时={elapsed:.1f}s, 回复摘要={result['content'][:80]}")

        return result

    async def _stream_chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        **kwargs,
    ) -> AsyncIterator[str]:
        """流式调用 Anthropic Messages API (SSE)。"""
        system_prompt, anthropic_messages = self._convert_messages_to_anthropic(messages)

        headers = {
            "Content-Type": "application/json",
            "x-api-key": self.api_key,
            "anthropic-version": _ANTHROPIC_VERSION,
        }

        body: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": anthropic_messages,
            "stream": True,
        }

        if system_prompt:
            body["system"] = system_prompt

        if tools:
            body["tools"] = self._convert_tools_to_anthropic(tools)

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/v1/messages",
                json=body,
                headers=headers,
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    payload = line[6:]
                    if payload.strip() == "[DONE]":
                        break
                    try:
                        event = json.loads(payload)
                        etype = event.get("type", "")
                        if etype == "content_block_delta":
                            delta = event.get("delta", {})
                            if delta.get("type") == "text_delta":
                                text = delta.get("text", "")
                                if text:
                                    yield text
                    except (json.JSONDecodeError, KeyError, IndexError):
                        continue

    async def is_available(self) -> bool:
        """检查 Anthropic API 是否可用（缓存60s）。"""
        now = time.time()
        if now - getattr(self, '_avail_ts', 0) < 60:
            return getattr(self, '_avail_cache', False)
        if not self.api_key:
            return False
        try:
            headers = {
                "x-api-key": self.api_key,
                "anthropic-version": _ANTHROPIC_VERSION,
                "Content-Type": "application/json",
            }
            body = {
                "model": self.model,
                "max_tokens": 1,
                "messages": [{"role": "user", "content": "hi"}],
            }
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    f"{self.base_url}/v1/messages",
                    json=body,
                    headers=headers,
                )
                ok = resp.status_code == 200
                self._avail_cache, self._avail_ts = ok, now
                return ok
        except Exception:
            self._avail_cache, self._avail_ts = False, now
            return False
