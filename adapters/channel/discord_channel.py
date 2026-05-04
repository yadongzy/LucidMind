"""Discord Channel Adapter — 通过 Discord Bot 接入 Brain。

配置：
  DISCORD_BOT_TOKEN=你的 Bot Token（从 Discord Developer Portal 获取）
  DISCORD_ALLOWED_CHANNELS=逗号分隔的频道 ID（可选，留空则不限制）

依赖：pip install discord.py
"""

import asyncio
import os
from typing import Callable, Awaitable

from ports.channel_port import ChannelPort
from logs import get_logger

logger = get_logger("channel.discord")


class DiscordChannelAdapter(ChannelPort):
    """Discord Bot 通道 — 将 Discord 消息路由到 Brain，支持线程绑定。"""

    def __init__(self):
        self._on_message: Callable | None = None
        self._client = None
        self._task: asyncio.Task | None = None
        self._token = os.getenv("DISCORD_BOT_TOKEN", "")
        self._allowed_channels: set[int] = set()
        raw = os.getenv("DISCORD_ALLOWED_CHANNELS", "")
        if raw:
            self._allowed_channels = {int(x.strip()) for x in raw.split(",") if x.strip()}
        self._brain = None

    async def start(self, on_message: Callable[[str, str], Awaitable[None]]) -> None:
        self._on_message = on_message
        if not self._token:
            logger.info("Discord: 未配置 DISCORD_BOT_TOKEN，跳过")
            return
        try:
            import discord
        except ImportError:
            logger.warning("Discord: 缺少 discord.py 库，pip install discord.py")
            return

        intents = discord.Intents.default()
        intents.message_content = True
        self._client = discord.Client(intents=intents)

        @self._client.event
        async def on_ready():
            logger.info(f"Discord: Bot 已登录: {self._client.user}")

        @self._client.event
        async def on_message(message):
            if message.author == self._client.user:
                return
            if message.author.bot:
                return
            if self._allowed_channels and message.channel.id not in self._allowed_channels:
                return

            # 线程绑定：使用 thread_id 或 channel_id 作为会话隔离
            thread_id = getattr(message.channel, "id", message.channel.id)
            session_id = f"discord_{message.author.id}_{thread_id}"
            text = message.content.strip()
            if not text:
                return

            logger.info(f"Discord: 收到消息 from={message.author} channel={message.channel} len={len(text)}")

            try:
                if self._brain:
                    from adapters.stream.collector_stream import CollectorStreamAdapter
                    collector = CollectorStreamAdapter()
                    await self._brain.process(session_id, text, stream=collector)
                    response = collector.get_text()
                    if response:
                        for chunk in self._split_message(response, 1900):
                            await message.reply(chunk)
                elif self._on_message:
                    await self._on_message(session_id, text)
            except Exception as e:
                logger.error(f"Discord: 处理消息失败: {e}")
                await message.reply(f"❌ Error: {e}")

        self._task = asyncio.create_task(self._run_bot())
        logger.info(f"Discord: Bot 启动中 (允许频道: {self._allowed_channels or '所有'})")

    async def _run_bot(self):
        try:
            await self._client.start(self._token)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Discord: Bot 异常: {e}")

    @staticmethod
    def _split_message(text: str, max_len: int = 1900) -> list[str]:
        if len(text) <= max_len:
            return [text]
        chunks = []
        while text:
            if len(text) <= max_len:
                chunks.append(text)
                break
            idx = text.rfind("\n", 0, max_len)
            if idx < max_len // 2:
                idx = max_len
            chunks.append(text[:idx])
            text = text[idx:].lstrip("\n")
        return chunks

    def set_brain(self, brain):
        self._brain = brain

    async def send_message(self, text: str, channel_id: int | str | None = None):
        """主动推送消息到 Discord 频道。"""
        if not self._client or not channel_id:
            return
        try:
            channel = self._client.get_channel(int(channel_id))
            if channel:
                for chunk in self._split_message(text, 1900):
                    await channel.send(chunk)
                logger.info(f"Discord: 已推送消息到频道 {channel_id}")
        except Exception as e:
            logger.error(f"Discord: 推送消息失败: {e}")

    async def stop(self) -> None:
        if self._client:
            await self._client.close()
        if self._task:
            self._task.cancel()
        logger.info("Discord: Channel 已停止")
