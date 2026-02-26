"""LucidMind API — FastAPI 入口。≤ 200 行。"""

import asyncio
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
from adapters.tools.composite import CompositeToolAdapter
from adapters.tools.sub_agent import SubAgentAdapter
from adapters.tools.introspect import IntrospectAdapter
from adapters.tools.hw_scanner import get_optimal_model_name
from adapters.tools.discover import discover_tool_adapters
from adapters.memory.json_memory import JSONMemoryAdapter
from adapters.learning.json_lessons import JSONLessonsAdapter
from adapters.learning.memory_store_adapter import MemoryStoreLearningAdapter
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
from api.personas import router as personas_router
from api.diagnostics import router as diagnostics_router
from api.memory import router as memory_router
from logs import get_logger

logger = get_logger("api")

app = FastAPI(title="LucidMind", version="0.1.0")
for _r in [upload_router, tasks_router, cron_router, sessions_router, auth_router, data_views.router, brain_init.router, http_chat.router, teacher.router, cascade_inject.router, plugins_router, mcp_router, channels_router, security_router, personas_router, diagnostics_router, memory_router]:
    app.include_router(_r)
# 前端静态文件 — frontend-v2构建产物(frontend/dist)为主页面
frontend_dist_dir = os.path.join(ROOT_DIR, "frontend", "dist")
# 启动时自动构建前端（如果 frontend-v2 源码比 dist 更新）
_fv2_dir = os.path.join(ROOT_DIR, "frontend-v2")
def _auto_build_frontend():
    """检测 frontend-v2/src 是否比 frontend/dist 更新，自动执行 vite build。"""
    try:
        dist_index = os.path.join(frontend_dist_dir, "index.html")
        src_dir = os.path.join(_fv2_dir, "src")
        if not os.path.exists(src_dir):
            return
        # 获取 dist/index.html 的修改时间（不存在则视为 0）
        dist_mtime = os.path.getmtime(dist_index) if os.path.exists(dist_index) else 0
        # 获取 src/ 下最新文件的修改时间
        src_mtime = 0
        for root, _, files in os.walk(src_dir):
            for f in files:
                t = os.path.getmtime(os.path.join(root, f))
                if t > src_mtime:
                    src_mtime = t
        if src_mtime > dist_mtime:
            logger.info("前端源码有更新，自动构建 frontend-v2...")
            import subprocess
            result = subprocess.run(
                ["npx", "vite", "build"],
                cwd=_fv2_dir, capture_output=True, text=True, timeout=60,
            )
            if result.returncode == 0:
                logger.info("前端自动构建成功 ✅")
            else:
                logger.warning(f"前端自动构建失败: {result.stderr[:200]}")
        else:
            logger.info("前端构建产物已是最新，跳过构建")
    except Exception as e:
        logger.warning(f"前端自动构建跳过: {e}")

_auto_build_frontend()
os.makedirs(os.path.join(frontend_dist_dir, "assets"), exist_ok=True)
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
    api_key=os.getenv("MINIMAX_API_KEY", ""),
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

# 活跃 provider 持久化（刷新页面后恢复用户选择的模型）
_ACTIVE_PROVIDER_PATH = os.path.join(ROOT_DIR, "data", "active_provider.json")
_provider_adapter_map = {"deepseek": _deepseek, "minimax": _minimax, "local": _local}

def _save_active_provider(provider: str):
    """保存用户选择的活跃 provider。"""
    try:
        os.makedirs(os.path.dirname(_ACTIVE_PROVIDER_PATH), exist_ok=True)
        with open(_ACTIVE_PROVIDER_PATH, "w") as f:
            json.dump({"provider": provider}, f)
    except Exception:
        pass

def _restore_active_provider():
    """启动时恢复用户上次选择的 provider。"""
    try:
        if os.path.exists(_ACTIVE_PROVIDER_PATH):
            with open(_ACTIVE_PROVIDER_PATH) as f:
                data = json.load(f)
            provider = data.get("provider", "")
            target = _provider_adapter_map.get(provider)
            if target:
                llm_adapter.set_primary(target)
                llm_adapter.provider_name = provider
                logger.info(f"恢复活跃 provider: {provider}")
    except Exception:
        pass

_restore_active_provider()
# 聚合工具适配器（自动发现 + 手动补充特殊工具）
_sub_agent = SubAgentAdapter()
_builtin_tools = discover_tool_adapters()  # 自动扫描 adapters/tools/ 下所有 ToolPort 子类
_builtin_tools.append(_sub_agent)  # SubAgentAdapter 需要注入 llm，单独处理
# 自动发现 skills/ 目录下的插件
from skills import discover_skills
_skill_tools = discover_skills()
# MCP 客户端（连接外部 MCP 服务器）
from adapters.tools.mcp_client import MCPClientAdapter
_mcp_client = MCPClientAdapter()
_builtin_tools.append(_mcp_client)
tool_adapter = CompositeToolAdapter(_builtin_tools)  # 只传内建工具，_builtin_tools 正确记录
# 添加 skill 工具（不进入 _builtin_tools，hot_reload 时会替换）
for _sa in _skill_tools:
    tool_adapter._adapters.append(_sa)
tool_adapter._refresh()
# 注入 tool_adapter 引用到 skills 模块，支持热加载
from skills import set_tool_adapter_ref
set_tool_adapter_ref(tool_adapter)
_sub_agent.set_llm(llm_adapter)
memory_adapter, learning_adapter, reflection_adapter = JSONMemoryAdapter(), MemoryStoreLearningAdapter(), JSONReflectionAdapter()
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

class SwitchProviderRequest(BaseModel):
    provider: str

@app.post("/api/switch-provider")
async def switch_provider(req: SwitchProviderRequest):
    """切换活跃模型（不验证连接，用于顶部下拉框快速切换）。"""
    target = _provider_adapter_map.get(req.provider)
    if not target:
        raise HTTPException(status_code=400, detail=f"Unknown provider: {req.provider}")
    llm_adapter.set_primary(target)
    llm_adapter.provider_name = req.provider
    _save_active_provider(req.provider)
    model_name = getattr(target, "model", "?")
    logger.info(f"模型已切换: {req.provider} ({model_name})")
    return {"status": "ok", "provider": req.provider, "model": model_name}

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
    # 更新对应适配器的配置
    _target_map = {"deepseek": _deepseek, "minimax": _minimax, "local": _local, "openai": _deepseek}
    target = _target_map.get(req.provider, _deepseek)
    target.api_key = req.api_key
    target.base_url = base_url.rstrip("/")
    target.model = model
    target.provider_name = req.provider
    # 清除可用性缓存，让新 key 立即生效
    target._avail_ts = 0
    # 切换 FallbackLLMAdapter 主模型
    llm_adapter.set_primary(target)
    llm_adapter.provider_name = req.provider
    # 持久化活跃 provider 选择（刷新页面后恢复）
    _save_active_provider(req.provider)
    logger.info(f"配置已更新: Provider={req.provider}, Model={model}")
    return {"status": "ok", "message": "Connection verified and applied"}

def _get_brain(stream=None):
    global _brain_singleton
    if _brain_singleton is None:
        _brain_singleton = Brain(llm=llm_adapter, stream=stream, tools=tool_adapter, memory=memory_adapter, learning=learning_adapter, reflection=reflection_adapter)
        # P2a: 注入人格管理器
        from identity.personas import get_persona_manager
        _brain_singleton._persona_manager = get_persona_manager()
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

    _cron_lock = asyncio.Lock()

    async def _cron_execute(command: str, sid: str, job_id: str = ""):
        """Cron 触发回调：Brain 处理命令并广播结果。"""
        async with _cron_lock:
            logger.info(f"🔔 Cron 触发执行: sid={sid}, job={job_id}, command={command[:60]}")
            # 保存当前 stream，避免干扰用户对话
            prev_stream = b.stream
            stream = BroadcastStreamAdapter(_ws_channel, job_name=command[:30], job_id=job_id, telegram=_telegram_channel)
            b.set_stream(stream)
            # 注入系统提示：要求使用工具获取实时信息
            enhanced_cmd = (
                f"[定时任务自动执行] 用户要求: {command}\n"
                f"重要：这是定时任务，请务必使用 web_search 工具搜索最新实时信息来完成任务。"
                f"不要依赖训练数据，必须联网搜索获取当天最新内容。"
                f"搜索完成后，整理成简洁有条理的中文摘要回复。"
            )
            try:
                await b.process(sid, enhanced_cmd)
            except Exception as e:
                logger.error(f"🔔 Cron 执行失败: {e}")
                await stream.emit("error", str(e))
            finally:
                # 恢复之前的 stream
                b.set_stream(prev_stream)

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
tool_adapter.set_safety_guard(_safety_guard)  # Safety by Default: 审批链闭环
security_api.init(_safety_guard)
data_views.init(memory_adapter, learning_adapter, brain=None)  # brain注入在_get_brain中延迟设置
http_chat.init(lambda s: _get_brain(s))
