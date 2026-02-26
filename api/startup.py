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
from adapters.llm.fallback_llm import FallbackLLMAdapter
from adapters.channel.websocket_channel import WebSocketChannelAdapter
from adapters.tools.composite import CompositeToolAdapter
from adapters.tools.sub_agent import SubAgentAdapter
from adapters.tools.introspect import IntrospectAdapter
from adapters.tools.hw_scanner import get_optimal_model_name
from adapters.tools.discover import discover_tool_adapters
from adapters.memory.json_memory import JSONMemoryAdapter
from adapters.learning.memory_store_adapter import MemoryStoreLearningAdapter
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

auto_build_frontend()
os.makedirs(os.path.join(frontend_dist_dir, "assets"), exist_ok=True)

# --- LLM Adapters ---
_deepseek = DeepSeekAdapter(api_key=os.getenv("DEEPSEEK_API_KEY", ""), base_url="https://api.deepseek.com/v1", model="deepseek-chat")
_deepseek.provider_name = "deepseek"
_minimax = DeepSeekAdapter(api_key=os.getenv("MINIMAX_API_KEY", ""), base_url="https://api.minimax.chat/v1", model="MiniMax-M1")
_minimax.provider_name = "minimax"
_optimal_local_model = get_optimal_model_name()
logger.info(f"硬件扫描: 最优本地模型={_optimal_local_model}")
_local = DeepSeekAdapter(api_key="ollama", base_url="http://localhost:11434/v1", model=_optimal_local_model)
_local.provider_name = "local"
_special_kb = SpecialKB()
llm_adapter = FallbackLLMAdapter(primary=_deepseek, fallbacks=[_minimax, _local], special_kb=_special_kb)
llm_adapter.provider_name = "deepseek+minimax+local"

# --- Provider 持久化 ---
_ACTIVE_PROVIDER_PATH = os.path.join(ROOT_DIR, "data", "active_provider.json")
provider_adapter_map = {"deepseek": _deepseek, "minimax": _minimax, "local": _local}

def save_active_provider(provider: str):
    try:
        os.makedirs(os.path.dirname(_ACTIVE_PROVIDER_PATH), exist_ok=True)
        with open(_ACTIVE_PROVIDER_PATH, "w") as f:
            json.dump({"provider": provider}, f)
    except Exception: pass

def _restore_active_provider():
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

_restore_active_provider()

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

# --- Multi-channel ---
telegram_channel = TelegramChannelAdapter()
feishu_channel = FeishuChannelAdapter()
wecom_channel = WeComChannelAdapter()
wechat_channel = WeChatChannelAdapter()
ws_channel = WebSocketChannelAdapter()
