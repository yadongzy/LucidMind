"""微信个人号 Channel Adapter — 通过 GeweChat (iPad 协议) 接入 Brain。

方案对比（2025-2026）：
  ❌ WeChatFerry — 已停止维护（Hook 方式，仅 Windows）
  ❌ wxauto — 2025-10-28 停止维护（UIAutomation 方式，仅 Windows）
  ❌ itchat/wxpy — Web 协议已被封禁，高封号率
  ✅ GeweChat — 活跃维护，iPad 协议，Docker 部署，跨平台，相对稳定

GeweChat 部署：
  docker pull registry.cn-hangzhou.aliyuncs.com/gewe/gewe:latest
  docker tag registry.cn-hangzhou.aliyuncs.com/gewe/gewe gewe
  docker run -itd -v gewechat/data:/root/temp -p 2531:2531 -p 2532:2532 --privileged=true --name=gewe gewe /usr/sbin/init

配置：
  GEWECHAT_BASE_URL=http://localhost:2531  （GeweChat 服务地址）
  GEWECHAT_CALLBACK_URL=http://你的IP:8765/api/channel/wechat/webhook  （接收消息回调）
  GEWECHAT_TOKEN=你的appId（登录后获取）
  WECHAT_ALLOWED_WXIDS=逗号分隔的wxid（可选，留空则不限制）

API 文档：https://apifox.com/apidoc/shared-69ba62ca-cb7d-437e-85e4-6f3d3df271b1

限制：
  - GeweChat 服务必须与登录微信的手机在同省
  - 仅用于个人娱乐/研究，请勿用于商业
"""

import asyncio
import json
import os
import time
from typing import Callable, Awaitable

from ports.channel_port import ChannelPort
from logs import get_logger

logger = get_logger("channel.wechat")


class WeChatChannelAdapter(ChannelPort):
    """微信个人号通道 — 通过 GeweChat iPad 协议接入 Brain。"""

    def __init__(self):
        self._on_message: Callable | None = None
        self._brain = None
        self._base_url = os.getenv("GEWECHAT_BASE_URL", "http://localhost:2531")
        self._callback_url = os.getenv("GEWECHAT_CALLBACK_URL", "")
        self._app_id = os.getenv("GEWECHAT_TOKEN", "")
        self._allowed_wxids: set[str] = set()
        raw = os.getenv("WECHAT_ALLOWED_WXIDS", "")
        if raw:
            self._allowed_wxids = {x.strip() for x in raw.split(",") if x.strip()}
        self._processed_msg_ids: set[str] = set()

    async def start(self, on_message: Callable[[str, str], Awaitable[None]]) -> None:
        self._on_message = on_message
        if not self._app_id:
            logger.info("微信: 未配置 GEWECHAT_TOKEN (appId)，跳过")
            logger.info("微信: 请先部署 GeweChat Docker 服务，登录获取 appId")
            return
        # 设置回调地址
        if self._callback_url:
            await self._set_callback()
        logger.info(f"微信: Channel 已就绪 (GeweChat iPad 协议)")

    async def stop(self) -> None:
        logger.info("微信: Channel 已停止")

    def set_brain(self, brain):
        self._brain = brain

    async def _api(self, path: str, data: dict | None = None) -> dict:
        """调用 GeweChat API。"""
        try:
            import httpx
            url = f"{self._base_url}{path}"
            async with httpx.AsyncClient(timeout=30) as client:
                if data is not None:
                    resp = await client.post(url, json=data)
                else:
                    resp = await client.get(url)
                return resp.json()
        except Exception as e:
            logger.error(f"微信: API 调用失败 {path}: {e}")
            return {"ret": -1, "msg": str(e)}

    async def _set_callback(self):
        """设置消息回调地址。"""
        result = await self._api("/v2/api/tools/setCallback", {
            "token": self._app_id,
            "callbackUrl": self._callback_url,
        })
        if result.get("ret") == 200:
            logger.info(f"微信: 回调地址已设置: {self._callback_url}")
        else:
            logger.warning(f"微信: 设置回调失败: {result}")

    async def _send_text(self, to_wxid: str, text: str):
        """发送文本消息。"""
        # 微信单条消息长度不宜超过 2000
        chunks = self._split_message(text, 1800)
        for chunk in chunks:
            result = await self._api("/v2/api/message/postText", {
                "appId": self._app_id,
                "toWxid": to_wxid,
                "content": chunk,
            })
            if result.get("ret") != 200:
                logger.warning(f"微信: 发送失败: {result}")

    async def handle_webhook(self, body: dict) -> dict:
        """处理 GeweChat 回调消息。

        GeweChat 推送格式：
        {
            "TypeName": "AddMsg",
            "Appid": "...",
            "Data": {
                "MsgId": 123,
                "FromUserName": {"string": "wxid_xxx"},
                "ToUserName": {"string": "wxid_yyy"},
                "MsgType": 1,
                "Content": {"string": "消息内容"},
                ...
            }
        }
        """
        type_name = body.get("TypeName", "")
        if type_name != "AddMsg":
            return {"ret": 200}

        data = body.get("Data", {})
        msg_id = str(data.get("MsgId", ""))
        msg_type = data.get("MsgType", 0)

        # 去重
        if msg_id and msg_id in self._processed_msg_ids:
            return {"ret": 200}
        if msg_id:
            self._processed_msg_ids.add(msg_id)
        if len(self._processed_msg_ids) > 1000:
            self._processed_msg_ids = set(list(self._processed_msg_ids)[-500:])

        # 只处理文本消息 (MsgType=1)
        if msg_type != 1:
            return {"ret": 200}

        from_wxid = data.get("FromUserName", {}).get("string", "")
        to_wxid = data.get("ToUserName", {}).get("string", "")
        content = data.get("Content", {}).get("string", "").strip()

        if not content or not from_wxid:
            return {"ret": 200}

        # 忽略自己发的消息
        if from_wxid == to_wxid:
            return {"ret": 200}

        # 权限检查
        if self._allowed_wxids and from_wxid not in self._allowed_wxids:
            return {"ret": 200}

        # 群消息处理：提取真实发送者和内容
        is_group = from_wxid.endswith("@chatroom")
        actual_sender = from_wxid
        if is_group:
            # 群消息格式: "wxid_xxx:\n实际内容"
            if ":\n" in content:
                actual_sender, content = content.split(":\n", 1)
            elif ":" in content:
                actual_sender, content = content.split(":", 1)
            content = content.strip()
            # 群消息需要 @机器人才回复（可选策略）
            # 这里简单处理：群消息全部回复

        session_id = f"wx_{actual_sender}"
        reply_to = from_wxid  # 回复到原会话（私聊回个人，群聊回群）

        logger.info(f"微信: 收到消息 from={actual_sender} group={is_group} len={len(content)}")

        asyncio.create_task(self._process_and_reply(session_id, content, reply_to))
        return {"ret": 200}

    async def _process_and_reply(self, session_id: str, text: str, reply_to: str):
        """调用 Brain 处理并回复。"""
        try:
            if self._brain:
                from adapters.stream.collector_stream import CollectorStreamAdapter
                collector = CollectorStreamAdapter()
                original_stream = self._brain.stream
                self._brain.set_stream(collector)
                try:
                    await self._brain.process(session_id, text)
                finally:
                    self._brain.set_stream(original_stream)
                response = collector.get_text()
                if response:
                    await self._send_text(reply_to, response)
            elif self._on_message:
                await self._on_message(session_id, text)
        except Exception as e:
            logger.error(f"微信: 处理消息失败: {e}")
            await self._send_text(reply_to, f"❌ 处理出错: {e}")

    @staticmethod
    def _split_message(text: str, max_len: int = 1800) -> list[str]:
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

    async def get_login_qrcode(self) -> dict:
        """获取微信登录二维码（首次登录时使用）。"""
        result = await self._api("/v2/api/login/getLoginQrCode", {
            "appId": self._app_id,
        })
        return result

    async def check_login_status(self) -> dict:
        """检查登录状态。"""
        result = await self._api("/v2/api/login/checkLogin", {
            "appId": self._app_id,
        })
        return result
