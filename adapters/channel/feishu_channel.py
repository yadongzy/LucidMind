"""飞书 Channel Adapter — 通过飞书官方 SDK 长连接模式接入 Brain。

使用 lark-oapi SDK 的 WebSocket 长连接模式：
  - 无需公网域名或 IP
  - 无需 ngrok 内网穿透
  - 无需配置加密/验签
  - 只需 App ID + App Secret 即可一键连接

配置：
  FEISHU_APP_ID=飞书应用 App ID
  FEISHU_APP_SECRET=飞书应用 App Secret

飞书开放平台：https://open.feishu.cn
1. 创建企业自建应用 → 开启机器人能力
2. 事件订阅方式选择「使用长连接接收事件」
3. 添加事件：im.message.receive_v1
"""

import asyncio
import json
import os
import threading
import time
from typing import Callable, Awaitable

from ports.channel_port import ChannelPort
from logs import get_logger

logger = get_logger("channel.feishu")


class FeishuChannelAdapter(ChannelPort):
    """飞书通道适配器 — 通过 SDK 长连接接收消息，调用 Brain 处理并回复。"""

    def __init__(self):
        self._on_message: Callable | None = None
        self._brain = None
        self._app_id = os.getenv("FEISHU_APP_ID", "")
        self._app_secret = os.getenv("FEISHU_APP_SECRET", "")
        self._ws_client = None
        self._ws_thread: threading.Thread | None = None
        self._running = False
        self._tenant_access_token = ""
        self._token_expires = 0
        self._processed_msg_ids: set[str] = set()  # 去重
        self._loop = None  # 主 asyncio 事件循环

    async def start(self, on_message: Callable[[str, str], Awaitable[None]]) -> None:
        self._on_message = on_message
        self._loop = asyncio.get_event_loop()
        if not self._app_id or not self._app_secret:
            logger.info("飞书: 未配置 FEISHU_APP_ID/FEISHU_APP_SECRET，跳过")
            return
        self._start_ws_client()

    def _start_ws_client(self):
        """启动 SDK 长连接客户端（在独立线程中运行）。"""
        if self._running:
            return
        try:
            import lark_oapi as lark

            # 注册消息事件处理器
            event_handler = lark.EventDispatcherHandler.builder("", "") \
                .register_p2_im_message_receive_v1(self._on_receive_message) \
                .build()

            self._ws_client = lark.ws.Client(
                self._app_id,
                self._app_secret,
                event_handler=event_handler,
                log_level=lark.LogLevel.INFO,
            )

            self._running = True
            self._ws_thread = threading.Thread(
                target=self._ws_client.start,
                daemon=True,
                name="feishu-ws",
            )
            self._ws_thread.start()
            logger.info("飞书: 长连接客户端已启动 (WebSocket 模式，无需公网域名)")
        except ImportError:
            logger.error("飞书: lark-oapi 未安装，请运行 pip install lark-oapi")
        except Exception as e:
            logger.error(f"飞书: 启动长连接失败: {e}")
            self._running = False

    def _on_receive_message(self, data) -> None:
        """SDK 事件回调 — 收到飞书消息（在 ws 线程中调用）。"""
        try:
            event = data.event
            message = event.message
            msg_id = message.message_id
            msg_type = message.message_type
            chat_type = message.chat_type

            # 去重
            if msg_id in self._processed_msg_ids:
                return
            self._processed_msg_ids.add(msg_id)
            if len(self._processed_msg_ids) > 1000:
                self._processed_msg_ids = set(list(self._processed_msg_ids)[-500:])

            # 只处理文本消息
            if msg_type != "text":
                return

            content = json.loads(message.content or "{}")
            text = content.get("text", "").strip()
            if not text:
                return

            sender = event.sender
            user_id = sender.sender_id.open_id if sender and sender.sender_id else "unknown"
            session_id = f"feishu_{user_id}"

            logger.info(f"飞书: 收到消息 from={user_id} chat_type={chat_type} len={len(text)}")

            # 调度到主事件循环执行异步处理
            if self._loop and self._loop.is_running():
                asyncio.run_coroutine_threadsafe(
                    self._process_and_reply(session_id, text, msg_id),
                    self._loop,
                )
        except Exception as e:
            logger.error(f"飞书: 解析消息事件失败: {e}")

    async def stop(self) -> None:
        self._running = False
        # lark ws.Client 没有 stop 方法，daemon 线程会随主进程退出
        self._ws_client = None
        self._ws_thread = None
        logger.info("飞书: Channel 已停止")

    def set_brain(self, brain):
        self._brain = brain

    async def _get_tenant_token(self) -> str:
        """获取 tenant_access_token（2小时有效，用于主动发送消息）。"""
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
        """兼容旧 Webhook 模式（保留以免路由报错）。"""
        # URL 验证
        if "challenge" in body:
            return {"challenge": body["challenge"]}
        return {"code": 0, "msg": "请使用长连接模式，无需配置 Webhook"}

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
