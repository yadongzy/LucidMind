"""企业微信 Channel Adapter — 通过企业微信应用消息 API 接入 Brain。

配置：
  WECOM_CORP_ID=企业ID
  WECOM_AGENT_ID=应用AgentId
  WECOM_SECRET=应用Secret
  WECOM_TOKEN=回调Token（用于验证消息来源）
  WECOM_ENCODING_AES_KEY=回调EncodingAESKey（消息加解密）

企业微信管理后台：https://work.weixin.qq.com
需要创建自建应用，设置回调地址为：http(s)://你的域名/api/channel/wecom/webhook
"""

import asyncio
import hashlib
import json
import os
import time
import xml.etree.ElementTree as ET
from typing import Callable, Awaitable

from ports.channel_port import ChannelPort
from logs import get_logger

logger = get_logger("channel.wecom")


class WeComChannelAdapter(ChannelPort):
    """企业微信通道适配器 — 接收企业微信回调事件，调用 Brain 处理并回复。"""

    def __init__(self):
        self._on_message: Callable | None = None
        self._brain = None
        self._corp_id = os.getenv("WECOM_CORP_ID", "")
        self._agent_id = os.getenv("WECOM_AGENT_ID", "")
        self._secret = os.getenv("WECOM_SECRET", "")
        self._callback_token = os.getenv("WECOM_TOKEN", "")
        self._encoding_aes_key = os.getenv("WECOM_ENCODING_AES_KEY", "")
        self._access_token = ""
        self._token_expires = 0
        self._processed_msg_ids: set[str] = set()

    async def start(self, on_message: Callable[[str, str], Awaitable[None]]) -> None:
        self._on_message = on_message
        if not self._corp_id or not self._secret:
            logger.info("企业微信: 未配置 WECOM_CORP_ID/WECOM_SECRET，跳过")
            return
        logger.info("企业微信: Channel 已就绪，等待回调事件")

    async def stop(self) -> None:
        logger.info("企业微信: Channel 已停止")

    def set_brain(self, brain):
        self._brain = brain

    async def _get_access_token(self) -> str:
        """获取 access_token（2小时有效）。"""
        if self._access_token and time.time() < self._token_expires:
            return self._access_token
        try:
            import httpx
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    "https://qyapi.weixin.qq.com/cgi-bin/gettoken",
                    params={"corpid": self._corp_id, "corpsecret": self._secret},
                )
                data = resp.json()
                if data.get("errcode", 0) != 0:
                    logger.error(f"企业微信: 获取 token 失败: {data}")
                    return ""
                self._access_token = data.get("access_token", "")
                self._token_expires = time.time() + data.get("expires_in", 7200) - 300
                return self._access_token
        except Exception as e:
            logger.error(f"企业微信: 获取 token 异常: {e}")
            return ""

    async def _send_text(self, user_id: str, text: str):
        """发送文本消息给用户。"""
        token = await self._get_access_token()
        if not token:
            return
        try:
            import httpx
            # 企业微信消息长度限制 2048
            chunks = self._split_message(text, 2000)
            async with httpx.AsyncClient(timeout=30) as client:
                for chunk in chunks:
                    await client.post(
                        f"https://qyapi.weixin.qq.com/cgi-bin/message/send?access_token={token}",
                        json={
                            "touser": user_id,
                            "msgtype": "text",
                            "agentid": int(self._agent_id) if self._agent_id else 0,
                            "text": {"content": chunk},
                        },
                    )
        except Exception as e:
            logger.error(f"企业微信: 发送消息失败: {e}")

    def verify_url(self, msg_signature: str, timestamp: str, nonce: str, echostr: str) -> str:
        """验证回调 URL（企业微信首次配置时调用）。

        简单模式：不加密，直接返回 echostr。
        加密模式需要 WXBizMsgCrypt，此处提供简化实现。
        """
        # 验证签名
        check_list = sorted([self._callback_token, timestamp, nonce, echostr])
        check_str = "".join(check_list)
        signature = hashlib.sha1(check_str.encode()).hexdigest()
        if signature != msg_signature:
            logger.warning("企业微信: URL 验证签名不匹配")
            return ""
        return echostr

    async def handle_webhook(self, body: str, msg_signature: str = "",
                             timestamp: str = "", nonce: str = "") -> str:
        """处理企业微信回调请求（XML 格式）。

        Args:
            body: 原始 XML 请求体
            msg_signature: 消息签名
            timestamp: 时间戳
            nonce: 随机数

        Returns:
            响应 XML 字符串
        """
        try:
            root = ET.fromstring(body)
        except ET.ParseError as e:
            logger.warning(f"企业微信: XML 解析失败: {e}")
            return "success"

        msg_type = root.findtext("MsgType", "")
        msg_id = root.findtext("MsgId", "")

        # 去重
        if msg_id and msg_id in self._processed_msg_ids:
            return "success"
        if msg_id:
            self._processed_msg_ids.add(msg_id)
        if len(self._processed_msg_ids) > 1000:
            self._processed_msg_ids = set(list(self._processed_msg_ids)[-500:])

        if msg_type != "text":
            return "success"

        content = root.findtext("Content", "").strip()
        from_user = root.findtext("FromUserName", "unknown")

        if not content:
            return "success"

        session_id = f"wecom_{from_user}"
        logger.info(f"企业微信: 收到消息 from={from_user} len={len(content)}")

        # 异步处理
        asyncio.create_task(self._process_and_reply(session_id, content, from_user))
        return "success"

    async def _process_and_reply(self, session_id: str, text: str, user_id: str):
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
                    await self._send_text(user_id, response)
            elif self._on_message:
                await self._on_message(session_id, text)
        except Exception as e:
            logger.error(f"企业微信: 处理消息失败: {e}")
            await self._send_text(user_id, f"❌ 处理出错: {e}")

    @staticmethod
    def _split_message(text: str, max_len: int = 2000) -> list[str]:
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
