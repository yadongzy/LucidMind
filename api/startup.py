"""LucidMind API 启动初始化 — Adapter 创建、前端构建、工具聚合。"""

import json
import os
import sys

ROOT_DIR = os.path.dirname(os.path.dirname(__file__))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from dotenv import load_dotenv
load_dotenv(os.path.join(ROOT_DIR, ".env"))

from adapters.llm.deepseek import DeepSeekAdapter
from adapters.llm.anthropic_adapter import AnthropicAdapter
from adapters.llm.fallback_llm import FallbackLLMAdapter
from adapters.channel.websocket_channel import WebSocketChannelAdapter
from adapters.tools.composite import CompositeToolAdapter
from adapters.tools.sub_agent import SubAgentAdapter
from adapters.tools.introspect import IntrospectAdapter
from adapters.tools.hw_scanner import get_optimal_model_name
from adapters.tools.discover import discover_tool_adapters
from adapters.memory.json_memory import JSONMemoryAdapter
from adapters.learning.memory_store_adapter import MemoryStoreLearningAdapter
from adapters.tools.observed_tool import ObservedToolAdapter
from adapters.reflection.json_reflection import JSONReflectionAdapter
from adapters.learning.special_kb import SpecialKB
from adapters.tools.mcp_client import MCPClientAdapter
from adapters.channel.telegram_channel import TelegramChannelAdapter
from adapters.channel.feishu_channel import FeishuChannelAdapter
from adapters.channel.wecom_channel import WeComChannelAdapter
from adapters.channel.wechat_channel import WeChatChannelAdapter
from skills import discover_skills, set_tool_adapter_ref
from logs import get_logger

logger = get_logger("api.startup")

# --- 前端自动构建 ---
frontend_dist_dir = os.path.join(ROOT_DIR, "frontend", "dist")
_fv2_dir = os.path.join(ROOT_DIR, "frontend-v2")

def auto_build_frontend():
    """检测 frontend-v2/src 是否比 frontend/dist 更新，自动执行 vite build。"""
    try:
        dist_index = os.path.join(frontend_dist_dir, "index.html")
        src_dir = os.path.join(_fv2_dir, "src")
        if not os.path.exists(src_dir):
            return
        dist_mtime = os.path.getmtime(dist_index) if os.path.exists(dist_index) else 0
        src_mtime = 0
        for root, _, files in os.walk(src_dir):
            for f in files:
                t = os.path.getmtime(os.path.join(root, f))
                if t > src_mtime:
                    src_mtime = t
        if src_mtime > dist_mtime:
            logger.info("前端源码有更新，自动构建 frontend-v2...")
            import subprocess
            result = subprocess.run(["npx", "vite", "build"], cwd=_fv2_dir, capture_output=True, text=True, timeout=60)
            if result.returncode == 0:
                logger.info("前端自动构建成功 ✅")
            else:
                logger.warning(f"前端自动构建失败: {result.stderr[:200]}")
        else:
            logger.info("前端构建产物已是最新，跳过构建")
    except Exception as e:
        logger.warning(f"前端自动构建跳过: {e}")

# --- 延迟初始化容器（D3 修复：避免 import 时副作用） ---
llm_adapter = None
tool_adapter = None
memory_adapter = None
learning_adapter = None
reflection_adapter = None
mcp_client = None
telegram_channel = None
feishu_channel = None
wecom_channel = None
wechat_channel = None
ws_channel = None
provider_adapter_map = {}
_ACTIVE_PROVIDER_PATH = os.path.join(ROOT_DIR, "data", "active_provider.json")

def save_active_provider(provider: str):
    try:
        os.makedirs(os.path.dirname(_ACTIVE_PROVIDER_PATH), exist_ok=True)
        with open(_ACTIVE_PROVIDER_PATH, "w") as f:
            json.dump({"provider": provider}, f)
    except Exception: pass

def init():
    """D3 修复: 显式初始化所有 Adapter，由 main.py startup 事件调用，不在 import 时执行。"""
    global llm_adapter, tool_adapter, memory_adapter, learning_adapter, reflection_adapter
    global mcp_client, telegram_channel, feishu_channel, wecom_channel, wechat_channel, ws_channel
    global provider_adapter_map

    auto_build_frontend()
    os.makedirs(os.path.join(frontend_dist_dir, "assets"), exist_ok=True)

    # --- LLM Adapters ---
    _deepseek = DeepSeekAdapter(api_key=os.getenv("DEEPSEEK_API_KEY", ""), base_url="https://api.deepseek.com/v1", model="deepseek-chat")
    _deepseek.provider_name = "deepseek"
    _minimax = AnthropicAdapter(api_key=os.getenv("MINIMAX_API_KEY", ""), base_url="https://api.minimax.io/anthropic", model="MiniMax-M2.5")
    _minimax.provider_name = "minimax"
    _optimal_local_model = get_optimal_model_name()
    logger.info(f"硬件扫描: 最优本地模型={_optimal_local_model}")
    _local = DeepSeekAdapter(api_key="ollama", base_url="http://localhost:11434/v1", model=_optimal_local_model)
    _local.provider_name = "local"
    # --- Antigravity 本地代理 (OpenAI 兼容，含 100+ 模型) ---
    _antigravity = DeepSeekAdapter(
        api_key="sk-9455ba5346a04b5294bbaf2589cf2f2c",
        base_url="http://127.0.0.1:8045/v1",
        model="gemini-3-flash",
    )
    _antigravity.provider_name = "antigravity"
    _antigravity._is_local = False  # 云端代理，非本地模型，不要精简工具

    _special_kb = SpecialKB()
    llm_adapter = FallbackLLMAdapter(primary=_deepseek, fallbacks=[_minimax, _antigravity, _local], special_kb=_special_kb)
    llm_adapter.provider_name = "deepseek+minimax+antigravity+local"

    # --- Provider 持久化 ---
    provider_adapter_map.update({"deepseek": _deepseek, "minimax": _minimax, "antigravity": _antigravity, "local": _local})
    try:
        if os.path.exists(_ACTIVE_PROVIDER_PATH):
            with open(_ACTIVE_PROVIDER_PATH) as f:
                data = json.load(f)
            provider = data.get("provider", "")
            target = provider_adapter_map.get(provider)
            if target:
                llm_adapter.set_primary(target)
                llm_adapter.provider_name = provider
                logger.info(f"恢复活跃 provider: {provider}")
    except Exception: pass

    # --- Tool Adapters ---
    _sub_agent = SubAgentAdapter()
    _builtin_tools = discover_tool_adapters()
    _builtin_tools.append(_sub_agent)
    mcp_client = MCPClientAdapter()
    _builtin_tools.append(mcp_client)
    tool_adapter = CompositeToolAdapter(_builtin_tools)
    _skill_tools = discover_skills()
    for _sa in _skill_tools:
        tool_adapter._adapters.append(_sa)
    tool_adapter._refresh()
    set_tool_adapter_ref(tool_adapter)
    _sub_agent.set_llm(llm_adapter)

    # --- Memory / Learning / Reflection ---
    memory_adapter = JSONMemoryAdapter()
    learning_adapter = MemoryStoreLearningAdapter()
    reflection_adapter = JSONReflectionAdapter()
    IntrospectAdapter._learning_adapter = learning_adapter

    # --- P1#7: 工具观察装饰器 ---
    tool_adapter = ObservedToolAdapter(tool_adapter, observer=learning_adapter._tool_observer)

    # --- Multi-channel ---
    telegram_channel = TelegramChannelAdapter()
    feishu_channel = FeishuChannelAdapter()
    wecom_channel = WeComChannelAdapter()
    wechat_channel = WeChatChannelAdapter()
    ws_channel = WebSocketChannelAdapter()

    # --- Token Tracker 阈值回调 ---
    try:
        from token_tracker import get_tracker
        def _on_token_threshold(event, pct, used, budget):
            if event == "auto_switch":
                cfg = get_tracker()._config
                target = cfg.auto_switch_target or "local"
                if cfg.pause_at_limit:
                    logger.warning(f"🛑 Token 预算耗尽({pct:.1f}%)，暂停 LLM 调用")
                else:
                    t = provider_adapter_map.get(target)
                    if t:
                        llm_adapter.set_primary(t)
                        llm_adapter.provider_name = target
                        logger.warning(f"🔄 Token 预算超限({pct:.1f}%)，自动切换到 {target}")
        get_tracker().on_threshold(_on_token_threshold)
    except Exception as e:
        logger.warning(f"Token tracker 初始化失败: {e}")

    logger.info("✅ 所有 Adapter 初始化完成")
