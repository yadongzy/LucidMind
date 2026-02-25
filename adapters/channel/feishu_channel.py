"""飞书 Channel Adapter — 通过飞书机器人 API 接入 Brain。

配置：
  FEISHU_APP_ID=飞书应用 App ID
  FEISHU_APP_SECRET=飞书应用 App Secret
  FEISHU_VERIFICATION_TOKEN=事件订阅验证 Token（可选）
  FEISHU_ENCRYPT_KEY=事件加密 Key（可选）

飞书开放平台：https://open.feishu.cn
需要在飞书开放平台创建企业自建应用，开启机器人能力，订阅消息事件。

回调地址设置为：http(s)://你的域名/api/channel/feishu/webhook
"""

import asyncio
import hashlib
import json
import os
import time
from typing import Callable, Awaitable, Any

from ports.channel_port import ChannelPort
from logs import get_logger

logger = get_logger("channel.feishu")


class FeishuChannelAdapter(ChannelPort):
    """飞书通道适配器 — 接收飞书 Webhook 事件，调用 Brain 处理并回复。"""

    def __init__(self):
        self._on_message: Callable | None = None
        self._brain = None
        self._app_id = os.getenv("FEISHU_APP_ID", "")
        self._app_secret = os.getenv("FEISHU_APP_SECRET", "")
        self._verification_token = os.getenv("FEISHU_VERIFICATION_TOKEN", "")
        self._encrypt_key = os.getenv("FEISHU_ENCRYPT_KEY", "")
        self._tenant_access_token = ""
        self._token_expires = 0
        self._processed_msg_ids: set[str] = set()  # 去重

    async def start(self, on_message: Callable[[str, str], Awaitable[None]]) -> None:
        self._on_message = on_message
        if not self._app_id or not self._app_secret:
            logger.info("飞书: 未配置 FEISHU_APP_ID/FEISHU_APP_SECRET，跳过")
            return
        logger.info("飞书: Channel 已就绪，等待 Webhook 事件")

    async def stop(self) -> None:
        logger.info("飞书: Channel 已停止")

    def set_brain(self, brain):
        self._brain = brain

    async def _get_tenant_token(self) -> str:
        """获取 tenant_access_token（2小时有效）。"""
        if self._tenant_access_token and time.time() < self._token_expires:
            return self._tenant_access_token
        try:
            import httpx
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
                    json={"app_id": self._app_id, "app_secret": self._app_secret},
                )
                data = resp.json()
                self._tenant_access_token = data.get("tenant_access_token", "")
                self._token_expires = time.time() + data.get("expire", 7200) - 300
                return self._tenant_access_token
        except Exception as e:
            logger.error(f"飞书: 获取 token 失败: {e}")
            return ""

    async def _reply_message(self, message_id: str, text: str):
        """回复飞书消息。"""
        token = await self._get_tenant_token()
        if not token:
            return
        try:
            import httpx
            async with httpx.AsyncClient(timeout=30) as client:
                await client.post(
                    f"https://open.feishu.cn/open-apis/im/v1/messages/{message_id}/reply",
                    headers={"Authorization": f"Bearer {token}"},
                    json={
                        "content": json.dumps({"text": text}),
                        "msg_type": "text",
                    },
                )
        except Exception as e:
            logger.error(f"飞书: 回复消息失败: {e}")

    async def _send_message(self, chat_id: str, text: str):
        """主动发送消息到会话。"""
        token = await self._get_tenant_token()
        if not token:
            return
        try:
            import httpx
            async with httpx.AsyncClient(timeout=30) as client:
                await client.post(
                    "https://open.feishu.cn/open-apis/im/v1/messages",
                    headers={"Authorization": f"Bearer {token}"},
                    params={"receive_id_type": "chat_id"},
                    json={
                        "receive_id": chat_id,
                        "content": json.dumps({"text": text}),
                        "msg_type": "text",
                    },
                )
        except Exception as e:
            logger.error(f"飞书: 发送消息失败: {e}")

    async def handle_webhook(self, body: dict) -> dict:
        """处理飞书 Webhook 请求（由 FastAPI 路由调用）。

        返回值直接作为 HTTP 响应体。
        """
        # URL 验证（飞书首次配置时发送）
        if "challenge" in body:
            return {"challenge": body["challenge"]}

        # 事件回调
        header = body.get("header", {})
        event = body.get("event", {})

        # 验证 token
        if self._verification_token:
            if header.get("token") != self._verification_token:
                logger.warning("飞书: 验证 token 不匹配")
                return {"code": 403, "msg": "invalid token"}

        event_type = header.get("event_type", "")
        if event_type != "im.message.receive_v1":
            return {"code": 0}

        message = event.get("message", {})
        msg_id = message.get("message_id", "")
        msg_type = message.get("message_type", "")
        chat_type = message.get("chat_type", "")

        # 去重
        if msg_id in self._processed_msg_ids:
            return {"code": 0}
        self._processed_msg_ids.add(msg_id)
        # 限制集合大小
        if len(self._processed_msg_ids) > 1000:
            self._processed_msg_ids = set(list(self._processed_msg_ids)[-500:])

        # 只处理文本消息
        if msg_type != "text":
            return {"code": 0}

        content = json.loads(message.get("content", "{}"))
        text = content.get("text", "").strip()
        if not text:
            return {"code": 0}

        sender = event.get("sender", {}).get("sender_id", {})
        user_id = sender.get("open_id", "unknown")
        session_id = f"feishu_{user_id}"

        logger.info(f"飞书: 收到消息 from={user_id} chat_type={chat_type} len={len(text)}")

        # 异步处理，立即返回
        asyncio.create_task(self._process_and_reply(session_id, text, msg_id))
        return {"code": 0}

    async def _process_and_reply(self, session_id: str, text: str, message_id: str):
        """调用 Brain 处理并回复。"""
        try:
            if self._brain:
                from adapters.stream.collector_stream import CollectorStreamAdapter
                collector = CollectorStreamAdapter()
                original_stream = self._brain._stream
                self._brain.set_stream(collector)
                try:
                    await self._brain.process(session_id, text)
                finally:
                    self._brain.set_stream(original_stream)
                response = collector.get_text()
                if response:
                    await self._reply_message(message_id, response)
            elif self._on_message:
                await self._on_message(session_id, text)
        except Exception as e:
            logger.error(f"飞书: 处理消息失败: {e}")
            await self._reply_message(message_id, f"❌ 处理出错: {e}")
