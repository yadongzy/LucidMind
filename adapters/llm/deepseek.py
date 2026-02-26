"""DeepSeek LLM Adapter — 通过 OpenAI 兼容 API 调用 DeepSeek。"""

import os
import json
import time
from typing import Any, AsyncIterator

import httpx

from ports.llm_port import LLMPort
from logs import get_logger

logger = get_logger("llm")


class DeepSeekAdapter(LLMPort):
    """DeepSeek API 适配器。使用 OpenAI 兼容格式。"""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = "https://api.deepseek.com/v1",
        model: str = "deepseek-chat",
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ):
        self.api_key = api_key or os.getenv("DEEPSEEK_API_KEY", "")
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self._is_local = "localhost" in base_url or "127.0.0.1" in base_url
        self._timeout = 180 if self._is_local else 60

        if not self.api_key:
            logger.warning("初始化: DEEPSEEK_API_KEY 未设置，LLM 调用将失败")
        else:
            logger.info(f"初始化: 模型={self.model}, 基址={self.base_url}")

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        stream: bool = False,
        **kwargs,
    ) -> dict[str, Any] | AsyncIterator[str]:
        """调用 DeepSeek API。"""

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

        body: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "stream": stream,
        }

        if tools:
            body["tools"] = tools
            body["tool_choice"] = kwargs.get("tool_choice", "auto") or "auto"

        if stream:
            return self._stream_chat(headers, body)

        return await self._non_stream_chat(headers, body)

    async def _non_stream_chat(
        self, headers: dict, body: dict
    ) -> dict[str, Any]:
        """非流式调用。"""
        t0 = time.time()
        msg_count = len(body.get("messages", []))
        last_msg = body["messages"][-1]["content"][:80] if body.get("messages") else ""
        logger.info(f"调用开始: 模型={body['model']}, 消息数={msg_count}, 最后一条={last_msg}")

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(
                    f"{self.base_url}/chat/completions",
                    json=body,
                    headers=headers,
                )
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPStatusError as e:
            elapsed = time.time() - t0
            logger.error(f"调用失败: HTTP {e.response.status_code}, 耗时={elapsed:.1f}s, 响应={e.response.text[:200]}")
            raise
        except Exception as e:
            elapsed = time.time() - t0
            logger.error(f"调用失败: {type(e).__name__}: {e}, 耗时={elapsed:.1f}s")
            raise

        elapsed = time.time() - t0
        choice = data["choices"][0]
        message = choice["message"]

        result: dict[str, Any] = {"content": message.get("content", "")}

        # 捕获 LLM 原生推理内容（DeepSeek-R1 的 reasoning_content）
        # 这是模型真正的思考过程，不是我们编的
        reasoning = message.get("reasoning_content")
        if reasoning:
            result["reasoning_content"] = reasoning
            logger.info(f"模型返回了推理内容: {len(reasoning)} 字")

        if message.get("tool_calls"):
            result["tool_calls"] = [
                {
                    "id": tc["id"],
                    "function": {
                        "name": tc["function"]["name"],
                        "arguments": tc["function"]["arguments"],
                    },
                }
                for tc in message["tool_calls"]
            ]
            logger.info(f"调用完成: 耗时={elapsed:.1f}s, 工具调用={len(result['tool_calls'])}个")

        usage = data.get("usage", {})
        if usage:
            result["usage"] = usage
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
        self, headers: dict, body: dict
    ) -> AsyncIterator[str]:
        """流式调用，逐 token 返回。"""
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/chat/completions",
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
                        chunk = json.loads(payload)
                        delta = chunk["choices"][0].get("delta", {})
                        content = delta.get("content", "")
                        if content:
                            yield content
                    except (json.JSONDecodeError, KeyError, IndexError):
                        continue

    async def is_available(self) -> bool:
        """检查 API 是否可用（缓存60s）。先试 /models，失败则用轻量 chat 探测。"""
        import time as _t
        now = _t.time()
        if now - getattr(self, '_avail_ts', 0) < 60:
            return getattr(self, '_avail_cache', False)
        if not self.api_key:
            return False
        try:
            headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
            async with httpx.AsyncClient(timeout=10) as client:
                # 先试 /models（DeepSeek/OpenAI 支持）
                resp = await client.get(f"{self.base_url}/models", headers=headers)
                if resp.status_code == 200:
                    self._avail_cache, self._avail_ts = True, now
                    return True
                # /models 不可用（如 MiniMax），用轻量 chat 探测
                probe = {"model": self.model, "messages": [{"role": "user", "content": "hi"}], "max_tokens": 1}
                resp2 = await client.post(f"{self.base_url}/chat/completions", json=probe, headers=headers)
                ok = resp2.status_code == 200
                self._avail_cache, self._avail_ts = ok, now
                return ok
        except Exception:
            self._avail_cache, self._avail_ts = False, now
            return False
