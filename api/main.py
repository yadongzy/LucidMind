"""LucidMind API — FastAPI 入口。≤ 200 行。"""

import asyncio
import json
import os

from fastapi import FastAPI, WebSocket
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from api.startup import (
    ROOT_DIR, frontend_dist_dir,
    llm_adapter, tool_adapter, memory_adapter, learning_adapter, reflection_adapter,
    mcp_client, ws_channel,
    telegram_channel, feishu_channel, wecom_channel, wechat_channel,
)
from api.config import router as config_router
from api.upload import router as upload_router
from api.tasks import router as tasks_router
from api.cron import router as cron_router
from api.sessions import router as sessions_router
from api.auth import router as auth_router
from api import data_views, http_chat, brain_init, teacher, cascade_inject
from api.plugins import router as plugins_router
from api.mcp import router as mcp_router
from api import mcp as mcp_api
from api.channels import router as channels_router
from api import channels as channels_api
from api.security import router as security_router
from api import security as security_api
from api.personas import router as personas_router
from api.diagnostics import router as diagnostics_router
from api.memory import router as memory_router
from brain import Brain
from logs import get_logger

logger = get_logger("api")

app = FastAPI(title="LucidMind", version="0.1.0")
for _r in [config_router, upload_router, tasks_router, cron_router, sessions_router, auth_router,
           data_views.router, brain_init.router, http_chat.router, teacher.router, cascade_inject.router,
           plugins_router, mcp_router, channels_router, security_router, personas_router,
           diagnostics_router, memory_router]:
    app.include_router(_r)

app.mount("/static/output", StaticFiles(directory=os.path.join(ROOT_DIR, "data", "output")), name="output")
app.mount("/assets", StaticFiles(directory=os.path.join(frontend_dist_dir, "assets")), name="assets")

brain_init.set_ws_channel(ws_channel)
try:
    from api.cron import set_ws_channel as _set_cron_ws
    _set_cron_ws(ws_channel)
except ImportError: pass

# --- Brain 单例 ---
_brain_singleton = None

def _get_brain(stream=None):
    global _brain_singleton
    if _brain_singleton is None:
        _brain_singleton = Brain(llm=llm_adapter, stream=stream, tools=tool_adapter,
                                  memory=memory_adapter, learning=learning_adapter, reflection=reflection_adapter)
        from identity.personas import get_persona_manager
        _brain_singleton._persona_manager = get_persona_manager()
        brain_init.set_brain(_brain_singleton)
        data_views._brain_ref = _brain_singleton
        logger.info("🧠 Brain 单例已创建")
    elif stream:
        _brain_singleton.set_stream(stream)
    return _brain_singleton

# --- Routes ---
@app.get("/")
async def index():
    return FileResponse(os.path.join(frontend_dist_dir, "index.html"))

@app.get("/api/health")
async def health():
    available = await llm_adapter.is_available()
    return {"status": "ok", "version": "0.1.0", "llm_available": available}

@app.get("/api/status")
async def status():
    llm_ok = await llm_adapter.is_available()
    tools = tool_adapter.list_tools()
    return {
        "version": "0.1.0", "stage": "S10",
        "llm": {"provider": getattr(llm_adapter, "provider_name", "Unknown"),
                "model": llm_adapter.model, "available": llm_ok},
        "tools": [t["function"]["name"] for t in tools],
        "ports": {"llm": True, "stream": True, "tools": True, "memory": True, "learning": True, "channel": True},
    }

# --- Task notify hook ---
def _task_notify_hook(event: str, task: dict):
    try:
        msg = json.dumps({"type": "task_updated", "event": event, "task": {
            "id": task.get("id"), "status": task.get("status"),
            "content": (task.get("content") or "")[:80],
            "priority": task.get("priority"), "source": task.get("source")}})
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.create_task(ws_channel.broadcast(msg))
    except Exception: pass

import task_dispatcher as _td
_td.register_notify_hook(_task_notify_hook)

# --- Lifecycle ---
@app.on_event("startup")
async def _startup():
    mcp_count = await mcp_client.discover()
    if mcp_count > 0:
        tool_adapter._rebuild_map()
        logger.info(f"MCP: {mcp_count} 个外部工具已注入 Brain")
    b = _get_brain()
    from api.cron import set_cron_callback
    from adapters.stream.broadcast_stream import BroadcastStreamAdapter
    _cron_lock = asyncio.Lock()

    async def _cron_execute(command: str, sid: str, job_id: str = ""):
        async with _cron_lock:
            logger.info(f"🔔 Cron 触发: sid={sid}, job={job_id}, cmd={command[:60]}")
            prev_stream = b.stream
            stream = BroadcastStreamAdapter(ws_channel, job_name=command[:30], job_id=job_id, telegram=telegram_channel)
            b.set_stream(stream)
            enhanced_cmd = (f"[定时任务自动执行] 用户要求: {command}\n"
                f"重要：请务必使用 web_search 工具搜索最新实时信息。不要依赖训练数据。")
            try:
                await b.process(sid, enhanced_cmd)
            except Exception as e:
                logger.error(f"🔔 Cron 执行失败: {e}")
                await stream.emit("error", str(e))
            finally:
                b.set_stream(prev_stream)

    set_cron_callback(_cron_execute)
    for ch in [telegram_channel, feishu_channel, wecom_channel, wechat_channel]:
        ch.set_brain(b)
        await ch.start(None)
    await brain_init.awaken(b)

@app.on_event("shutdown")
async def _shutdown():
    await mcp_client.shutdown()
    for ch in [telegram_channel, feishu_channel, wecom_channel, wechat_channel]:
        await ch.stop()

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    token = websocket.query_params.get("token", "")
    brain = _get_brain()
    await ws_channel.handle_connection(websocket, brain, token=token)

# --- Module init ---
teacher.init(ws_channel, brain_init.teacher)
mcp_api.init(mcp_client, tool_adapter)
channels_api.init(telegram_channel, feishu_channel, wecom_channel, wechat_channel)
from adapters.tools.tool_safety import get_safety_guard
_safety_guard = get_safety_guard()
_safety_guard.set_ws_channel(ws_channel)
tool_adapter.set_safety_guard(_safety_guard)
security_api.init(_safety_guard)
data_views.init(memory_adapter, learning_adapter, brain=None)
http_chat.init(lambda s: _get_brain(s))
