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
import tempfile
import threading
import time
from pathlib import Path
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

        # 清除代理环境变量，避免飞书 SDK 连接时 SSL 失败
        # 必须在 SDK 初始化前清除，否则 urllib3 会缓存代理设置
        _proxy_keys = ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy")
        _saved_proxies = {k: os.environ.pop(k) for k in _proxy_keys if k in os.environ}
        if _saved_proxies:
            logger.info(f"飞书: 已临时清除代理环境变量: {list(_saved_proxies.keys())}")

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

            def _run_ws():
                """在独立线程中创建新的事件循环运行 ws client。"""
                import asyncio as _aio
                import lark_oapi.ws.client as ws_mod
                # 彻底清除代理：从 os.environ 移除 + 禁用 urllib3 代理检测
                for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy",
                           "ALL_PROXY", "all_proxy", "NO_PROXY", "no_proxy"):
                    os.environ.pop(k, None)
                try:
                    import urllib3.util.connection
                    urllib3.util.connection.HAS_IPV6 = False  # 强制 IPv4
                except Exception:
                    pass
                # SDK 的 start() 使用模块级 loop 变量，必须替换为新的事件循环
                new_loop = _aio.new_event_loop()
                _aio.set_event_loop(new_loop)
                ws_mod.loop = new_loop
                # Lock 也需要绑定到新 loop
                self._ws_client._lock = _aio.Lock()
                try:
                    self._ws_client.start()
                except Exception as e:
                    logger.error(f"飞书: 长连接线程退出: {e}")
                finally:
                    self._running = False
                    logger.info("飞书: 长连接线程已结束")

            self._running = True
            self._ws_thread = threading.Thread(
                target=_run_ws,
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

            sender = event.sender
            user_id = sender.sender_id.open_id if sender and sender.sender_id else "unknown"
            session_id = f"feishu_{user_id}"
            content = json.loads(message.content or "{}")

            if msg_type == "text":
                text = content.get("text", "").strip()
                if not text:
                    return
                logger.info(f"飞书: 收到文本消息 from={user_id} chat_type={chat_type} len={len(text)}")
                if self._loop and self._loop.is_running():
                    asyncio.run_coroutine_threadsafe(
                        self._process_and_reply(session_id, text, msg_id),
                        self._loop,
                    )
            elif msg_type == "audio":
                file_key = content.get("file_key", "")
                if not file_key:
                    return
                logger.info(f"飞书: 收到语音消息 from={user_id} file_key={file_key}")
                if self._loop and self._loop.is_running():
                    asyncio.run_coroutine_threadsafe(
                        self._handle_audio_message(session_id, msg_id, file_key),
                        self._loop,
                    )
            else:
                logger.debug(f"飞书: 忽略消息类型 {msg_type} from={user_id}")
                return
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
            logger.error("飞书: 无法获取 tenant_access_token，回复取消")
            return
        try:
            import httpx
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    f"https://open.feishu.cn/open-apis/im/v1/messages/{message_id}/reply",
                    headers={"Authorization": f"Bearer {token}"},
                    json={
                        "content": json.dumps({"text": text}),
                        "msg_type": "text",
                    },
                )
                data = resp.json()
                if data.get("code") != 0:
                    logger.error(f"飞书: 回复消息失败: code={data.get('code')}, msg={data.get('msg')}")
                else:
                    logger.info(f"飞书: 回复消息成功 message_id={message_id}")
        except Exception as e:
            logger.error(f"飞书: 回复消息异常: {e}")

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

    async def _download_message_resource(self, message_id: str, file_key: str, ext: str = "opus") -> str | None:
        """下载飞书消息中的文件资源，返回本地临时文件路径。"""
        token = await self._get_tenant_token()
        if not token:
            return None
        try:
            import httpx
            url = f"https://open.feishu.cn/open-apis/im/v1/messages/{message_id}/resources/{file_key}"
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.get(
                    url,
                    headers={"Authorization": f"Bearer {token}"},
                    params={"type": "file"},
                )
                if resp.status_code != 200:
                    logger.error(f"飞书: 下载资源失败: status={resp.status_code}")
                    return None
                tmp_dir = Path(tempfile.gettempdir()) / "lucidmind_feishu"
                tmp_dir.mkdir(exist_ok=True)
                tmp_path = tmp_dir / f"{file_key}.{ext}"
                tmp_path.write_bytes(resp.content)
                logger.info(f"飞书: 语音文件已下载: {tmp_path} ({len(resp.content)} bytes)")
                return str(tmp_path)
        except Exception as e:
            logger.error(f"飞书: 下载资源异常: {e}")
            return None

    async def _handle_audio_message(self, session_id: str, message_id: str, file_key: str):
        """处理语音消息：下载音频 → STT 转文字 → 交给 Brain。"""
        try:
            # 1. 下载语音文件
            audio_path = await self._download_message_resource(message_id, file_key, "opus")
            if not audio_path:
                await self._reply_message(message_id, "❌ 无法下载语音文件，请检查应用权限 im:message:resource")
                return

            # 2. 语音转文字
            text = await self._speech_to_text(audio_path)
            if not text:
                await self._reply_message(message_id, "❌ 语音识别失败，请发送文本消息")
                return

            logger.info(f"飞书: 语音识别结果: {text[:80]}")

            # 3. 交给 Brain 处理
            await self._process_and_reply(session_id, text, message_id)

        except Exception as e:
            logger.error(f"飞书: 处理语音消息失败: {e}")
            await self._reply_message(message_id, f"❌ 语音处理出错: {e}")
        finally:
            # 清理临时文件
            try:
                if audio_path and Path(audio_path).exists():
                    Path(audio_path).unlink()
            except Exception:
                pass

    _whisper_model = None
    _whisper_checked = False

    async def _speech_to_text(self, audio_path: str) -> str:
        """语音转文字 — 优先用 openai-whisper，降级用飞书 API。"""
        if not FeishuChannelAdapter._whisper_checked:
            FeishuChannelAdapter._whisper_checked = True
            try:
                import whisper
                FeishuChannelAdapter._whisper_model = whisper.load_model("base")
                logger.info("飞书: Whisper 模型已加载 (base)")
            except ImportError:
                logger.info("飞书: whisper 未安装，将使用飞书语音识别 API")
            except Exception as e:
                logger.warning(f"飞书: Whisper 加载失败: {e}")

        if FeishuChannelAdapter._whisper_model:
            try:
                result = await asyncio.to_thread(
                    FeishuChannelAdapter._whisper_model.transcribe, audio_path, language="zh"
                )
                return result.get("text", "").strip()
            except Exception as e:
                logger.warning(f"飞书: whisper 识别失败: {e}，尝试飞书 API")

        # 降级: 飞书语音识别 API (需要 PCM 格式，仅支持 60 秒以内)
        try:
            token = await self._get_tenant_token()
            if not token:
                return ""
            # 用 ffmpeg 转换为 PCM
            import subprocess
            pcm_path = audio_path + ".pcm"
            proc = await asyncio.to_thread(
                subprocess.run,
                ["ffmpeg", "-y", "-i", audio_path, "-f", "s16le", "-ar", "16000", "-ac", "1", pcm_path],
                capture_output=True, timeout=30,
            )
            if proc.returncode != 0:
                logger.warning(f"飞书: ffmpeg 转换失败: {proc.stderr.decode()[:200]}")
                return ""
            pcm_data = Path(pcm_path).read_bytes()
            Path(pcm_path).unlink(missing_ok=True)

            import base64
            import httpx
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    "https://open.feishu.cn/open-apis/speech_to_text/v1/speech/file_recognize",
                    headers={"Authorization": f"Bearer {token}"},
                    json={
                        "speech": {"speech": base64.b64encode(pcm_data).decode()},
                        "config": {"engine_type": "16k_auto", "file_id": "feishu_audio", "format": "pcm"},
                    },
                )
                data = resp.json()
                if data.get("code") == 0:
                    return data.get("data", {}).get("recognition_text", "")
                else:
                    logger.error(f"飞书: 语音识别API失败: {data.get('msg')}")
                    return ""
        except Exception as e:
            logger.error(f"飞书: 语音识别降级失败: {e}")
            return ""

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
                await self._brain.process(session_id, text, stream=collector)
                response = collector.get_text()
                if response:
                    await self._reply_message(message_id, response)
            elif self._on_message:
                await self._on_message(session_id, text)
        except Exception as e:
            logger.error(f"飞书: 处理消息失败: {e}")
            await self._reply_message(message_id, f"❌ 处理出错: {e}")
