"""S34: WebSocket Channel Adapter — 实现 ChannelPort 接口。

让 WebSocket 通道经过标准 Port 接口，实现真正的可插拔。
新 Adapter，不修改 brain.py（规则 06）。
"""
import asyncio
import json
import time
from typing import Callable, Awaitable, Any

from fastapi import WebSocket, WebSocketDisconnect
from ports.channel_port import ChannelPort
from adapters.stream.websocket_stream import WebSocketStreamAdapter
from command_queue import get_command_queue, CommandLane
from logs import get_logger

logger = get_logger("channel.ws")

_SERVER_PING_INTERVAL = 30  # 服务端主动 ping 间隔（秒）
_SERVER_PONG_TIMEOUT = 180  # 服务端无 pong 判死时间（秒）— 需要足够长以覆盖 fallback 模型处理


class WebSocketChannelAdapter(ChannelPort):
    """WebSocket 通道适配器 — 将 WebSocket 消息路由到 Brain。"""

    def __init__(self):
        self._on_message: Callable | None = None
        self._connections: dict[str, WebSocket] = {}
        self._last_pong: dict[str, float] = {}  # conn_id -> last pong timestamp
        self._server_hb_task: asyncio.Task | None = None

    async def start(self, on_message: Callable[[str, str], Awaitable[None]]) -> None:
        self._on_message = on_message
        if not self._server_hb_task or self._server_hb_task.done():
            self._server_hb_task = asyncio.create_task(self._server_heartbeat_loop())
        logger.info("WebSocket Channel 已就绪 (服务端心跳已启动)")

    async def stop(self) -> None:
        if self._server_hb_task:
            self._server_hb_task.cancel()
            try:
                await self._server_hb_task
            except (asyncio.CancelledError, Exception):
                pass
        for cid in list(self._connections):
            try:
                await self._connections[cid].close()
            except Exception:
                pass
        self._connections.clear()
        self._last_pong.clear()
        logger.info("WebSocket Channel 已停止")

    def _resolve_user(self, token: str) -> str:
        if not token:
            return "anonymous"
        try:
            from adapters.auth.user_isolator import get_isolator
            uid = get_isolator().validate_token(token)
            return uid or "anonymous"
        except Exception:
            return "anonymous"

    def _isolate_sid(self, user_id: str, session_id: str) -> str:
        if user_id == "anonymous":
            return session_id
        try:
            from adapters.auth.user_isolator import get_isolator
            return get_isolator().get_isolated_session_id(user_id, session_id)
        except Exception:
            return session_id

    async def handle_connection(self, websocket: WebSocket, brain,
                                token: str = "") -> None:
        """处理一个 WebSocket 连接的完整生命周期。"""
        await websocket.accept()
        conn_id = str(id(websocket))
        self._connections[conn_id] = websocket
        self._last_pong[conn_id] = time.time()
        user_id = self._resolve_user(token)
        # S59: ws_holder — stream 始终指向当前用户最新活跃连接
        if not hasattr(brain, '_ws_holders'):
            brain._ws_holders = {}
        holder = brain._ws_holders.setdefault(user_id, {"ws": websocket})
        holder["ws"] = websocket
        stream = WebSocketStreamAdapter(websocket, ws_holder=holder)
        brain.set_stream(stream)
        # 对话输入排队机制：用户连续发消息时入队顺序处理，不丢失
        chat_queue: asyncio.Queue = asyncio.Queue()
        consumer_task: asyncio.Task | None = None
        current_task: asyncio.Task | None = None
        logger.info(f"WebSocket 连接已建立 (conn={conn_id}, user={user_id})")

        async def _queue_consumer():
            """顺序消费聊天队列，保证消息按发送顺序处理。"""
            nonlocal current_task
            while True:
                item = await chat_queue.get()
                if item is None:  # 毒丸，退出
                    break
                sid, user_input = item
                pending = chat_queue.qsize()
                if pending > 0:
                    try:
                        await stream.emit("info", f"📨 排队中: 还有 {pending} 条消息待处理")
                    except Exception:
                        pass
                current_task = asyncio.create_task(self._safe_process(
                    brain, stream, sid, user_input, self._on_message))
                await current_task
                current_task = None
                chat_queue.task_done()

        consumer_task = asyncio.create_task(_queue_consumer())

        try:
            while True:
                raw = await websocket.receive_text()
                data = json.loads(raw)
                msg_type = data.get("type")

                if msg_type == "server_pong":
                    self._last_pong[conn_id] = time.time()
                elif msg_type == "ping":
                    self._last_pong[conn_id] = time.time()
                    await websocket.send_json({"type": "pong",
                        "ts": time.time(),
                        "client_ts": data.get("client_ts"),
                        "brain": brain._awake if hasattr(brain, '_awake') else True,
                        "queue": chat_queue.qsize()})
                elif msg_type == "switch_session":
                    iso_sid = self._isolate_sid(user_id, data.get("session_id", "default"))
                    await brain.switch_session(iso_sid)
                elif msg_type == "abort":
                    # 清空排队 + 取消当前任务
                    while not chat_queue.empty():
                        try:
                            chat_queue.get_nowait()
                            chat_queue.task_done()
                        except asyncio.QueueEmpty:
                            break
                    if current_task and not current_task.done():
                        current_task.cancel()
                        logger.info(f"用户中止了当前任务 (conn={conn_id})")
                        try:
                            await current_task
                        except (asyncio.CancelledError, Exception):
                            pass
                    try:
                        await stream.emit("info", "⏹ 已停止")
                        await stream.emit("complete", None)
                    except Exception:
                        pass
                elif msg_type == "tool_approval_response":
                    from adapters.tools.tool_safety import get_safety_guard
                    guard = get_safety_guard()
                    guard.handle_approval_response(
                        data.get("request_id", ""),
                        data.get("approved", False),
                        data.get("reason", ""),
                    )
                elif msg_type == "chat":
                    user_input = data.get("message", "").strip()
                    if user_input:
                        raw_sid = data.get("session_id", "default")
                        sid = self._isolate_sid(user_id, raw_sid)
                        await chat_queue.put((sid, user_input))
                        qsize = chat_queue.qsize()
                        if qsize > 1:
                            logger.info(f"📨 消息入队: queue={qsize} (conn={conn_id})")
        except WebSocketDisconnect:
            logger.info(f"WebSocket 连接已断开 (conn={conn_id})")
        except Exception as e:
            logger.error(f"WebSocket 错误 (conn={conn_id}): {e}")
        finally:
            # 停止消费者（毒丸让 consumer 退出循环，但不取消正在执行的 process 任务）
            await chat_queue.put(None)
            if consumer_task and not consumer_task.done():
                # 等待当前 process 完成（最多 120s），ws_holder 会路由到新连接
                try:
                    await asyncio.wait_for(consumer_task, timeout=120)
                except (asyncio.TimeoutError, asyncio.CancelledError, Exception):
                    consumer_task.cancel()
                    try:
                        await consumer_task
                    except (asyncio.CancelledError, Exception):
                        pass
            self._connections.pop(conn_id, None)
            self._last_pong.pop(conn_id, None)

    async def broadcast(self, message: str):
        """向所有活跃连接广播消息。"""
        dead = []
        for cid, ws in list(self._connections.items()):
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(cid)
        for cid in dead:
            self._connections.pop(cid, None)
            self._last_pong.pop(cid, None)

    async def _server_heartbeat_loop(self):
        """服务端主动心跳：定期检测僵尸连接并清理。"""
        while True:
            try:
                await asyncio.sleep(_SERVER_PING_INTERVAL)
                now = time.time()
                dead = []
                for cid, ws in list(self._connections.items()):
                    last = self._last_pong.get(cid, 0)
                    if now - last > _SERVER_PONG_TIMEOUT:
                        dead.append(cid)
                        continue
                    try:
                        await ws.send_json({"type": "server_ping", "ts": now})
                    except Exception:
                        dead.append(cid)
                for cid in dead:
                    ws = self._connections.pop(cid, None)
                    self._last_pong.pop(cid, None)
                    if ws:
                        try:
                            await ws.close()
                        except Exception:
                            pass
                    logger.info(f"♻ 清理僵尸连接: {cid}")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"服务端心跳异常: {e}")

    # 承诺性结尾模式：回复以这些短语结尾表示任务未完成
    _PROMISE_TAIL_PATTERNS = [
        "让我", "我来", "正在", "接下来", "下面我", "现在我",
        "让我用", "让我试", "我来试", "我来帮",
        "稍等", "请稍等", "马上",
        "正在尝试", "正在执行", "正在处理", "正在搜索", "正在查找",
        "I'll", "Let me", "I'm going to", "I will now",
    ]

    # 追踪每个会话的活跃任务（一个目标一个任务，跨消息追踪）
    _session_tasks: dict[str, str] = {}   # session_id → task_id

    @staticmethod
    def _detect_reply_question(reply: str) -> bool:
        """检测回复是否以提问结尾（等待用户响应 → 任务仍在进行中）。"""
        if not reply:
            return False
        tail = reply.strip()[-100:]
        return any(q in tail for q in ["?", "？", "需要我帮", "需要我", "要我帮"])

    @staticmethod
    def _clean_reply_for_check(reply: str) -> str:
        """剥离 DSML/XML 伪工具调用标签，返回纯文本用于质量检查。"""
        import re
        _dsml_re = re.compile(
            r'<\s*\|?\s*(?:DSML\s*\|?\s*)?(?:function_calls|invoke|parameter|/invoke|/function_calls|/parameter)\b[^>]*>',
            re.IGNORECASE,
        )
        return _dsml_re.sub("", reply.strip()).strip()

    @staticmethod
    async def _safe_process(brain, stream, sid, user_input, on_message):
        """后台安全执行 brain.process，通过 command_queue CHAT lane 统一入队。
        工具调用/复杂操作自动入队 task_dispatcher，实现对话→任务看板联动。

        设计: 一个对话目标 = 一个任务。同一会话内多条消息复用同一任务，
        以总目标为完成标准，而非每条消息独立判断。
        """
        async def _do_process():
            if on_message:
                await on_message(sid, user_input)
            else:
                import task_dispatcher as td

                # === 任务查找/创建: 复用同会话的活跃任务 ===
                task_id = WebSocketChannelAdapter._session_tasks.get(sid)
                is_new_task = False

                # 验证已有任务是否仍然活跃
                if task_id:
                    store = td.load_store()
                    task_alive = any(
                        t["id"] == task_id and t["status"] in ("ready", "running")
                        for t in store.get("tasks", [])
                    )
                    if not task_alive:
                        task_id = None
                        WebSocketChannelAdapter._session_tasks.pop(sid, None)

                if task_id:
                    # 复用现有任务，更新进度
                    td.update_task_progress(task_id, f"步骤: {user_input[:60]}")
                    logger.info(f"[{sid}] 复用会话任务: {task_id}, 步骤: {user_input[:40]}")
                else:
                    # 首条消息 → 创建新任务（总目标）
                    is_new_task = True
                    try:
                        task = td.enqueue(
                            user_input[:500],
                            task_type="task",
                            priority="P2",
                            source="chat",
                            timeout_s=300,
                        )
                        task_id = task["id"]
                        WebSocketChannelAdapter._session_tasks[sid] = task_id
                        td.update_task_progress(task_id, "执行中")
                        logger.info(f"[{sid}] 新建会话任务: {task_id}")
                    except Exception as e:
                        logger.debug(f"对话任务创建失败: {e}")

                result = await brain.process(sid, user_input, stream=stream)

                # === 结果质量检查 + 目标完成判断 ===
                if task_id and isinstance(result, dict):
                    tool_happened = result.get("tool_calls_happened", False)
                    empty_promise = result.get("empty_promise_detected", False)
                    reply = result.get("reply", "")

                    clean_reply = WebSocketChannelAdapter._clean_reply_for_check(reply)
                    tail = clean_reply[-200:] if len(clean_reply) > 200 else clean_reply

                    is_empty_fallback = reply and "没有生成有效的回复" in reply
                    is_promise_ending = any(
                        p in tail for p in WebSocketChannelAdapter._PROMISE_TAIL_PATTERNS
                    ) if tail else False
                    is_question = WebSocketChannelAdapter._detect_reply_question(clean_reply)

                    if is_empty_fallback or is_promise_ending or (empty_promise and not tool_happened):
                        # 软失败: 承诺未兑现 / 空回复 → fail + 唤醒Daemon
                        error_reason = (
                            "空回复" if is_empty_fallback
                            else "承诺未兑现" if is_promise_ending
                            else "空承诺:工具未执行"
                        )
                        td.fail_task(task_id, error_reason)
                        WebSocketChannelAdapter._session_tasks.pop(sid, None)
                        logger.warning(f"[{sid}] 对话任务失败({error_reason}): {task_id}")
                        _wake_daemon()
                    elif is_question:
                        # 回复以提问结尾 → 任务仍在进行中（等待用户下一步输入）
                        td.update_task_progress(task_id, "等待用户响应")
                        logger.info(f"[{sid}] 任务等待用户响应: {task_id}")
                    elif tool_happened and not is_new_task:
                        # 多步任务中工具已执行 → 步骤完成，任务继续
                        td.update_task_progress(task_id, f"步骤完成: {user_input[:40]}")
                        logger.info(f"[{sid}] 任务步骤完成(继续): {task_id}")
                    else:
                        # 无提问+无承诺 → 目标完成
                        td.complete_task(task_id)
                        WebSocketChannelAdapter._session_tasks.pop(sid, None)
                        logger.info(f"[{sid}] 对话任务目标完成: {task_id}")
                elif task_id:
                    td.complete_task(task_id)
                    WebSocketChannelAdapter._session_tasks.pop(sid, None)

        try:
            cq = get_command_queue()
            await cq.enqueue(
                lane=CommandLane.CHAT,
                task=_do_process,
                task_id=f"chat_{sid}",
            )
        except asyncio.CancelledError:
            logger.info(f"Brain 处理已被用户中止 (sid={sid})")
        except Exception as e:
            logger.error(f"Brain 处理异常 (sid={sid}): {e}")
            try:
                await stream.emit("error", f"处理出错: {e}")
                await stream.emit("complete", None)
            except Exception:
                pass


def _wake_daemon():
    """尝试唤醒 Daemon（塥罗式，不依赖全局变量）。"""
    try:
        from api.brain_init import daemon
        if daemon:
            daemon.wake()
    except Exception:
        pass
