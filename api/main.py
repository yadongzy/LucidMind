"""LucidMind API — FastAPI 入口。≤ 200 行。"""

import json
import os
import sys

from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

# 项目根目录加入 sys.path
ROOT_DIR = os.path.dirname(os.path.dirname(__file__))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

load_dotenv(os.path.join(ROOT_DIR, ".env"))

from brain import Brain
from adapters.llm.deepseek import DeepSeekAdapter
from adapters.llm.fallback_llm import FallbackLLMAdapter
from adapters.channel.websocket_channel import WebSocketChannelAdapter
from adapters.tools.shell import ShellAdapter; from adapters.tools.file import FileAdapter
from adapters.tools.web_search import WebSearchAdapter; from adapters.tools.composite import CompositeToolAdapter
from adapters.tools.search_files import SearchFilesAdapter; from adapters.tools.document import DocumentAdapter
from adapters.tools.browser_tool import BrowserToolAdapter; from adapters.tools.image_tool import ImageToolAdapter
from adapters.tools.file_analyze import FileAnalyzeAdapter; from adapters.tools.sub_agent import SubAgentAdapter
from adapters.tools.introspect import IntrospectAdapter; from adapters.tools.teaching import TeachingAdapter
from adapters.tools.weather import WeatherAdapter; from adapters.tools.system_monitor import SystemMonitorAdapter
from adapters.tools.scheduler import SchedulerAdapter; from adapters.tools.hw_scanner import HWScannerAdapter, get_optimal_model_name
from adapters.tools.deep_research import DeepResearchAdapter
from adapters.memory.json_memory import JSONMemoryAdapter
from adapters.learning.json_lessons import JSONLessonsAdapter
from adapters.reflection.json_reflection import JSONReflectionAdapter
from adapters.learning.special_kb import SpecialKB

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
from logs import get_logger

logger = get_logger("api")

app = FastAPI(title="LucidMind", version="0.1.0")
for _r in [upload_router, tasks_router, cron_router, sessions_router, auth_router, data_views.router, brain_init.router, http_chat.router, teacher.router, cascade_inject.router, plugins_router, mcp_router, channels_router, security_router]:
    app.include_router(_r)
# 前端静态文件 — frontend-v2构建产物(frontend/dist)为主页面
frontend_dist_dir = os.path.join(ROOT_DIR, "frontend", "dist")
app.mount("/static/output", StaticFiles(directory=os.path.join(ROOT_DIR, "data", "output")), name="output")
app.mount("/assets", StaticFiles(directory=os.path.join(frontend_dist_dir, "assets")), name="assets")

# 全局复用的 adapters — DeepSeek 主模型 + 本地 qwen3:8b 保底
_deepseek = DeepSeekAdapter(
    api_key=os.getenv("DEEPSEEK_API_KEY", ""),
    base_url="https://api.deepseek.com/v1",
    model="deepseek-chat",
)
_deepseek.provider_name = "deepseek"
_minimax = DeepSeekAdapter(
    api_key=os.getenv("MINIMAX_API_KEY", "sk-cp-LbE4ilWhHLWMvYDEnqCST8j564oVcZ29AYpxRlITfOuRlHJhvW0KDNKWhvbECRCYbxrW3NPaOCsFB2E-QN4mHuofvI8HnslSC-covqXrphIK7eBWtKThi5o"),
    base_url="https://api.minimax.chat/v1", model="MiniMax-M1",
)
_minimax.provider_name = "minimax"
# 自动扫描硬件，选择最优本地模型
_optimal_local_model = get_optimal_model_name()
logger.info(f"硬件扫描: 最优本地模型={_optimal_local_model}")
_local = DeepSeekAdapter(
    api_key="ollama",
    base_url="http://localhost:11434/v1",
    model=_optimal_local_model,
)
_local.provider_name = "local"
_special_kb = SpecialKB()
llm_adapter = FallbackLLMAdapter(primary=_deepseek, fallbacks=[_minimax, _local], special_kb=_special_kb)
llm_adapter.provider_name = "deepseek+minimax+local"
# 聚合工具适配器（内置 + 插件）
_sub_agent = SubAgentAdapter()
_builtin_tools = [ShellAdapter(), FileAdapter(), WebSearchAdapter(), SearchFilesAdapter(),
    DocumentAdapter(), BrowserToolAdapter(), ImageToolAdapter(), FileAnalyzeAdapter(), _sub_agent,
    IntrospectAdapter(), TeachingAdapter(),
    WeatherAdapter(), SystemMonitorAdapter(), SchedulerAdapter(), HWScannerAdapter(), DeepResearchAdapter()]
# 自动发现 skills/ 目录下的插件
from skills import discover_skills
_skill_tools = discover_skills()
# MCP 客户端（连接外部 MCP 服务器）
from adapters.tools.mcp_client import MCPClientAdapter
_mcp_client = MCPClientAdapter()
_builtin_tools.append(_mcp_client)
tool_adapter = CompositeToolAdapter(_builtin_tools + _skill_tools)
# 注入 tool_adapter 引用到 skills 模块，支持热加载
from skills import set_tool_adapter_ref
set_tool_adapter_ref(tool_adapter)
_sub_agent.set_llm(llm_adapter)
memory_adapter, learning_adapter, reflection_adapter = JSONMemoryAdapter(), JSONLessonsAdapter(), JSONReflectionAdapter()
IntrospectAdapter._learning_adapter = learning_adapter
# 多通道适配器
from adapters.channel.telegram_channel import TelegramChannelAdapter
from adapters.channel.feishu_channel import FeishuChannelAdapter
from adapters.channel.wecom_channel import WeComChannelAdapter
from adapters.channel.wechat_channel import WeChatChannelAdapter
_telegram_channel = TelegramChannelAdapter()
_feishu_channel = FeishuChannelAdapter()
_wecom_channel = WeComChannelAdapter()
_wechat_channel = WeChatChannelAdapter()
# S30+S34: Brain 单例 + Channel Port 闭环
_brain_singleton = None
_ws_channel = WebSocketChannelAdapter()
brain_init.set_ws_channel(_ws_channel)  # 让 Daemon 能监控连接状态
# 注入 WebSocket 到 cron 调度器（统一管理定时任务和提醒）
try:
    from api.cron import set_ws_channel as _set_cron_ws
    _set_cron_ws(_ws_channel)
except ImportError:
    pass

class ConfigRequest(BaseModel):
    provider: str; api_key: str; model: str | None = None


@app.get("/")
async def index():
    """主页 — 返回新前端(frontend-v2构建产物)。"""
    return FileResponse(os.path.join(frontend_dist_dir, "index.html"))


@app.get("/api/health")
async def health():
    """健康检查。"""
    available = await llm_adapter.is_available()
    return {"status": "ok", "version": "0.1.0", "llm_available": available}


@app.get("/api/status")
async def status():
    """开发者状态面板数据。"""
    llm_ok = await llm_adapter.is_available()
    tools = tool_adapter.list_tools()
    return {
        "version": "0.1.0",
        "stage": "S10",
        "llm": {
            "provider": getattr(llm_adapter, "provider_name", "Unknown"), # Need to add this field or infer
            "model": llm_adapter.model,
            "available": llm_ok,
        },
        "tools": [t["function"]["name"] for t in tools],
        "ports": {
            "llm": True,
            "stream": True,
            "tools": True,
            "memory": True,
            "learning": True,
            "channel": True,  # CLI adapter available
        },
    }


_PROVIDERS = {
    "deepseek": ("https://api.deepseek.com/v1", "deepseek-chat"),
    "minimax": ("https://api.minimax.chat/v1", "MiniMax-M1"),
    "openai": ("https://api.openai.com/v1", "gpt-4-turbo"),
    "local": ("http://localhost:11434/v1", "qwen3:8b"),
}

@app.post("/api/verify")
async def verify_config(req: ConfigRequest):
    """验证并应用配置。"""
    entry = _PROVIDERS.get(req.provider)
    if not entry:
        raise HTTPException(status_code=400, detail="Unknown provider")
    base_url, default_model = entry
    model = req.model or default_model
    test = DeepSeekAdapter(api_key=req.api_key, base_url=base_url, model=model)
    if not await test.is_available():
        return {"status": "error", "message": "Connection failed"}
    # 更新主模型配置（deepseek/minimax/openai 共用主槽位）
    target = _local if req.provider == "local" else _deepseek
    target.api_key = req.api_key
    target.base_url = base_url.rstrip("/")
    target.model = model
    target.provider_name = req.provider
    llm_adapter.provider_name = req.provider
    logger.info(f"配置已更新: Provider={req.provider}, Model={model}")
    return {"status": "ok", "message": "Connection verified and applied"}

def _get_brain(stream=None):
    global _brain_singleton
    if _brain_singleton is None:
        _brain_singleton = Brain(llm=llm_adapter, stream=stream, tools=tool_adapter, memory=memory_adapter, learning=learning_adapter, reflection=reflection_adapter)
        brain_init.set_brain(_brain_singleton)
        data_views._brain_ref = _brain_singleton
        logger.info("🧠 Brain 单例已创建")
    elif stream: _brain_singleton.set_stream(stream)
    return _brain_singleton

def _task_notify_hook(event: str, task: dict):
    """任务变更时通过 WebSocket 推送到前端。"""
    import asyncio
    try:
        msg = json.dumps({"type": "task_updated", "event": event, "task": {
            "id": task.get("id"), "status": task.get("status"),
            "content": (task.get("content") or "")[:80],
            "priority": task.get("priority"), "source": task.get("source"),
        }})
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.create_task(_ws_channel.broadcast(msg))
    except Exception:
        pass

import task_dispatcher as _td
_td.register_notify_hook(_task_notify_hook)

@app.on_event("startup")
async def _startup():
    # MCP: 发现外部 MCP Server 工具
    mcp_count = await _mcp_client.discover()
    if mcp_count > 0:
        tool_adapter._rebuild_map()
        logger.info(f"MCP: {mcp_count} 个外部工具已注入 Brain")
    b = _get_brain()
    # 注册 Cron 回调：任务触发时让 Brain 自主执行
    from api.cron import set_cron_callback
    from adapters.stream.broadcast_stream import BroadcastStreamAdapter

    async def _cron_execute(command: str, sid: str):
        """Cron 触发回调：Brain 处理命令并广播结果。"""
        logger.info(f"🔔 Cron 触发执行: sid={sid}, command={command[:60]}")
        stream = BroadcastStreamAdapter(_ws_channel, job_name=command[:30])
        b.set_stream(stream)
        try:
            await b.process(sid, command)
        except Exception as e:
            logger.error(f"🔔 Cron 执行失败: {e}")
            await stream.emit("error", str(e))
        finally:
            # 恢复 stream 到最近的 WebSocket 连接
            if hasattr(b, '_ws_holders') and b._ws_holders:
                for uid, holder in b._ws_holders.items():
                    ws = holder.get("ws")
                    if ws:
                        from adapters.stream.websocket_stream import WebSocketStreamAdapter
                        b.set_stream(WebSocketStreamAdapter(ws, ws_holder=holder))
                        break

    set_cron_callback(_cron_execute)
    logger.info("🔔 Cron 回调已注册: Brain 将自主执行定时任务")
    # 启动多通道
    _telegram_channel.set_brain(b)
    _feishu_channel.set_brain(b)
    _wecom_channel.set_brain(b)
    _wechat_channel.set_brain(b)
    await _telegram_channel.start(None)
    await _feishu_channel.start(None)
    await _wecom_channel.start(None)
    await _wechat_channel.start(None)
    await brain_init.awaken(b)

@app.on_event("shutdown")
async def _shutdown():
    await _mcp_client.shutdown()
    await _telegram_channel.stop()
    await _feishu_channel.stop()
    await _wecom_channel.stop()
    await _wechat_channel.stop()

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """S34+S49: WebSocket 通过 ChannelPort 接入 Brain，支持 JWT 认证。"""
    token = websocket.query_params.get("token", "")
    brain = _get_brain()
    await _ws_channel.handle_connection(websocket, brain, token=token)


teacher.init(_ws_channel, brain_init.teacher)
mcp_api.init(_mcp_client, tool_adapter)
channels_api.init(_telegram_channel, _feishu_channel, _wecom_channel, _wechat_channel)
from adapters.tools.tool_safety import get_safety_guard
_safety_guard = get_safety_guard()
_safety_guard.set_ws_channel(_ws_channel)
security_api.init(_safety_guard)
data_views.init(memory_adapter, learning_adapter, brain=None)  # brain注入在_get_brain中延迟设置
http_chat.init(lambda s: _get_brain(s))
