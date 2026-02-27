"""Telegram Channel Adapter — 通过 Telegram Bot API 接入 Brain。

配置：
  TELEGRAM_BOT_TOKEN=你的Bot Token（从 @BotFather 获取）
  TELEGRAM_ALLOWED_USERS=逗号分隔的用户ID（可选，留空则不限制）

依赖：pip install python-telegram-bot
"""

import asyncio
import os
from typing import Callable, Awaitable

from ports.channel_port import ChannelPort
from logs import get_logger

logger = get_logger("channel.telegram")


class TelegramChannelAdapter(ChannelPort):
    """Telegram Bot 通道 — 将 Telegram 消息路由到 Brain。"""

    def __init__(self):
        self._on_message: Callable | None = None
        self._app = None
        self._task: asyncio.Task | None = None
        self._token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        self._allowed_users: set[int] = set()
        raw = os.getenv("TELEGRAM_ALLOWED_USERS", "")
        if raw:
            self._allowed_users = {int(x.strip()) for x in raw.split(",") if x.strip()}
        self._brain = None

    async def start(self, on_message: Callable[[str, str], Awaitable[None]]) -> None:
        self._on_message = on_message
        if not self._token:
            logger.info("Telegram: 未配置 TELEGRAM_BOT_TOKEN，跳过")
            return
        try:
            from telegram import Update
            from telegram.ext import Application, MessageHandler, CommandHandler, filters
        except ImportError:
            logger.warning("Telegram: 缺少 python-telegram-bot 库，pip install python-telegram-bot")
            return

        self._app = Application.builder().token(self._token).build()

        async def _handle_start(update: Update, context):
            user = update.effective_user
            await update.message.reply_text(
                f"🧠 LucidMind 已连接！\n"
                f"你好 {user.first_name}，直接发消息给我即可对话。"
            )

        async def _handle_message(update: Update, context):
            if not update.message or not update.message.text:
                return
            user_id = update.effective_user.id
            if self._allowed_users and user_id not in self._allowed_users:
                await update.message.reply_text("⛔ 你不在允许列表中。")
                return
            text = update.message.text.strip()
            if not text:
                return
            session_id = f"tg_{user_id}"
            logger.info(f"Telegram: 收到消息 from={user_id} len={len(text)}")

            # 调用 Brain 处理
            try:
                if self._brain:
                    # 收集 Brain 输出
                    response = await self._collect_response(session_id, text)
                    if response:
                        # Telegram 消息长度限制 4096
                        for chunk in self._split_message(response, 4000):
                            await update.message.reply_text(chunk)
                elif self._on_message:
                    await self._on_message(session_id, text)
            except Exception as e:
                logger.error(f"Telegram: 处理消息失败: {e}")
                await update.message.reply_text(f"❌ 处理出错: {e}")

        self._app.add_handler(CommandHandler("start", _handle_start))
        self._app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, _handle_message))

        # 后台启动 polling
        self._task = asyncio.create_task(self._run_polling())
        logger.info(f"Telegram: Bot 已启动 (允许用户: {self._allowed_users or '所有'})")

    async def _run_polling(self):
        """后台运行 Telegram polling。"""
        try:
            await self._app.initialize()
            await self._app.start()
            await self._app.updater.start_polling(drop_pending_updates=True)
            # 保持运行
            while True:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Telegram: polling 异常: {e}")
        finally:
            try:
                if self._app.updater.running:
                    await self._app.updater.stop()
                if self._app.running:
                    await self._app.stop()
                await self._app.shutdown()
            except Exception:
                pass

    async def _collect_response(self, session_id: str, user_input: str) -> str:
        """调用 Brain 并收集完整响应文本。"""
        from adapters.stream.collector_stream import CollectorStreamAdapter
        collector = CollectorStreamAdapter()
        await self._brain.process(session_id, user_input, stream=collector)
        return collector.get_text()

    @staticmethod
    def _split_message(text: str, max_len: int = 4000) -> list[str]:
        """按长度拆分消息。"""
        if len(text) <= max_len:
            return [text]
        chunks = []
        while text:
            if len(text) <= max_len:
                chunks.append(text)
                break
            # 尝试在换行处断开
            idx = text.rfind("\n", 0, max_len)
            if idx < max_len // 2:
                idx = max_len
            chunks.append(text[:idx])
            text = text[idx:].lstrip("\n")
        return chunks

    def set_brain(self, brain):
        """注入 Brain 引用。"""
        self._brain = brain

    async def send_message(self, text: str, chat_id: int | str | None = None):
        """主动推送消息到 Telegram（用于 Cron 结果推送）。"""
        if not self._token or not self._app:
            return
        try:
            from telegram import Bot
            bot = Bot(token=self._token)
            # 如果没有指定 chat_id，发送给所有允许的用户
            targets = [chat_id] if chat_id else list(self._allowed_users)
            if not targets:
                logger.debug("Telegram: 无推送目标")
                return
            for tid in targets:
                if not tid:
                    continue
                for chunk in self._split_message(text, 4000):
                    await bot.send_message(chat_id=int(tid), text=chunk)
            logger.info(f"Telegram: 已推送消息到 {len(targets)} 个用户")
        except Exception as e:
            logger.error(f"Telegram: 推送消息失败: {e}")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
        logger.info("Telegram: Channel 已停止")
