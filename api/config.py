"""LucidMind API — 模型配置与切换路由。"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from adapters.llm.deepseek import DeepSeekAdapter
from adapters.llm.anthropic_adapter import AnthropicAdapter
import api.startup as startup
from logs import get_logger

logger = get_logger("api.config")
router = APIRouter()

_PROVIDERS = {
    "deepseek": ("https://api.deepseek.com/v1", "deepseek-chat", "openai"),
    "minimax": ("https://api.minimax.io/anthropic", "MiniMax-M2.5", "anthropic"),
    "openai": ("https://api.openai.com/v1", "gpt-4o", "openai"),
    "local": ("http://localhost:11434/v1", "qwen3:8b", "openai"),
    "anthropic": ("https://api.anthropic.com", "claude-sonnet-4-5", "anthropic"),
    "google": ("https://generativelanguage.googleapis.com/v1beta/openai", "gemini-2.0-flash", "openai"),
    "groq": ("https://api.groq.com/openai/v1", "llama-3.3-70b-versatile", "openai"),
    "moonshot": ("https://api.moonshot.cn/v1", "moonshot-v1-128k", "openai"),
    "zhipu": ("https://open.bigmodel.cn/api/paas/v4", "glm-4-plus", "openai"),
    "xai": ("https://api.x.ai/v1", "grok-2", "openai"),
    "mistral": ("https://api.mistral.ai/v1", "mistral-large-latest", "openai"),
    "volcengine": ("https://ark.cn-beijing.volces.com/api/v3", "doubao-seed-1-8-251228", "openai"),
    "antigravity": ("http://127.0.0.1:8045/v1", "gemini-3-flash", "openai"),
}


class ConfigRequest(BaseModel):
    provider: str; api_key: str; model: str | None = None


class SwitchProviderRequest(BaseModel):
    provider: str


@router.post("/api/switch-provider")
async def switch_provider(req: SwitchProviderRequest):
    """切换活跃模型（不验证连接，用于顶部下拉框快速切换）。"""
    target = startup.provider_adapter_map.get(req.provider)
    if not target:
        raise HTTPException(status_code=400, detail=f"Unknown provider: {req.provider}")
    startup.llm_adapter.set_primary(target)
    startup.llm_adapter.provider_name = req.provider
    startup.save_active_provider(req.provider)
    model_name = getattr(target, "model", "?")
    logger.info(f"模型已切换: {req.provider} ({model_name})")
    return {"status": "ok", "provider": req.provider, "model": model_name}


@router.post("/api/verify")
async def verify_config(req: ConfigRequest):
    """验证并应用配置。"""
    entry = _PROVIDERS.get(req.provider)
    if not entry:
        raise HTTPException(status_code=400, detail="Unknown provider")
    base_url, default_model, api_type = entry
    model = req.model or default_model
    if api_type == "anthropic":
        test = AnthropicAdapter(api_key=req.api_key, base_url=base_url, model=model)
    else:
        test = DeepSeekAdapter(api_key=req.api_key, base_url=base_url, model=model)
    if not await test.is_available():
        return {"status": "error", "message": "Connection failed"}
    _target_map = startup.provider_adapter_map
    target = _target_map.get(req.provider) or list(_target_map.values())[0]
    target.api_key = req.api_key
    target.base_url = base_url.rstrip("/")
    target.model = model
    target.provider_name = req.provider
    target._avail_ts = 0
    startup.llm_adapter.set_primary(target)
    startup.llm_adapter.provider_name = req.provider
    startup.save_active_provider(req.provider)
    logger.info(f"配置已更新: Provider={req.provider}, Model={model}")
    return {"status": "ok", "message": "Connection verified and applied"}
