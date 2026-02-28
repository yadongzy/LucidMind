"""LucidMind API — 模型目录 + 本地扫描 + 硬件推荐。

对标 OpenClaw model-catalog.ts / model-scan.ts / model-selection.ts。
超越维度: 硬件自动扫描 + 智能推荐 + 云端/本地分离。
"""

import json
import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from adapters.llm.deepseek import DeepSeekAdapter
from adapters.llm.anthropic_adapter import AnthropicAdapter
import api.startup as startup
from logs import get_logger

logger = get_logger("api.models")
router = APIRouter()

_CATALOG_PATH = Path(__file__).parent.parent / "adapters" / "llm" / "model_catalog.json"
_CUSTOM_PROVIDERS_PATH = Path(__file__).parent.parent / "data" / "custom_providers.json"


def _load_catalog() -> dict:
    """加载模型目录。"""
    with open(_CATALOG_PATH, encoding="utf-8") as f:
        return json.load(f)


def _load_custom_providers() -> dict:
    """加载用户自定义 provider。"""
    if _CUSTOM_PROVIDERS_PATH.exists():
        try:
            with open(_CUSTOM_PROVIDERS_PATH, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save_custom_providers(data: dict):
    """保存用户自定义 provider。"""
    os.makedirs(_CUSTOM_PROVIDERS_PATH.parent, exist_ok=True)
    with open(_CUSTOM_PROVIDERS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _check_api_key(env_key: str) -> bool:
    """检查环境变量中是否有 API key。"""
    val = os.getenv(env_key, "")
    return bool(val and len(val) > 5)


@router.get("/api/models")
async def list_models():
    """列出所有可用模型（云端 + 本地），含状态信息。"""
    catalog = _load_catalog()
    custom = _load_custom_providers()

    # 云端 providers
    cloud = []
    for pid, pinfo in catalog.get("cloud_providers", {}).items():
        has_key = _check_api_key(pinfo.get("env_key", "")) or bool(pinfo.get("api_key")) or pid in startup.provider_adapter_map
        # 当前活跃状态
        is_active = False
        active_model = None
        adapter = startup.provider_adapter_map.get(pid)
        if adapter:
            is_active = startup.llm_adapter and (
                startup.llm_adapter._primary is adapter
            )
            active_model = getattr(adapter, "model", None)

        cloud.append({
            "id": pid,
            "name": pinfo["name"],
            "api_type": pinfo.get("api_type", "openai"),
            "configured": has_key,
            "active": is_active,
            "active_model": active_model,
            "models": pinfo.get("models", []),
        })

    # 自定义 providers（跳过已在 catalog 中的）
    catalog_ids = set(catalog.get("cloud_providers", {}).keys())
    for pid, pinfo in custom.items():
        if pid in catalog_ids:
            continue
        has_key = _check_api_key(pinfo.get("env_key", "")) if pinfo.get("env_key") else bool(pinfo.get("api_key"))
        cloud.append({
            "id": pid,
            "name": pinfo.get("name", pid),
            "api_type": pinfo.get("api_type", "openai"),
            "configured": has_key,
            "active": False,
            "active_model": None,
            "models": pinfo.get("models", []),
            "custom": True,
        })

    # 本地模型
    local_scan = _scan_local_models()

    return {
        "cloud_providers": cloud,
        "local": local_scan,
        "active_provider": getattr(startup.llm_adapter, "provider_name", "unknown") if startup.llm_adapter else None,
    }


@router.get("/api/models/scan")
async def scan_local():
    """扫描本地硬件 + Ollama 已安装模型 + 推荐。"""
    return _scan_local_models()


@router.get("/api/models/hardware")
async def get_hardware():
    """获取硬件信息。"""
    from adapters.tools.hw_scanner import scan_hardware
    return scan_hardware()


@router.get("/api/models/recommend")
async def recommend():
    """根据硬件推荐最佳本地模型。"""
    from adapters.tools.hw_scanner import recommend_model
    return recommend_model()


class SwitchModelRequest(BaseModel):
    provider: str
    model: str | None = None


@router.post("/api/models/switch")
async def switch_model(req: SwitchModelRequest):
    """切换到指定 provider 的指定模型。支持动态创建 adapter。"""
    catalog = _load_catalog()
    custom = _load_custom_providers()

    # 已注册的 provider 直接切换
    existing = startup.provider_adapter_map.get(req.provider)
    if existing:
        if req.model:
            existing.model = req.model
            if hasattr(existing, '_actual_model'):
                existing._actual_model = None
        startup.llm_adapter.set_primary(existing)
        startup.llm_adapter.provider_name = req.provider
        startup.save_active_provider(req.provider)
        model_name = getattr(existing, "model", "?")
        logger.info(f"模型切换: {req.provider}/{model_name}")
        return {"status": "ok", "provider": req.provider, "model": model_name}

    # 未注册的 provider — 查找目录并动态创建
    pinfo = catalog.get("cloud_providers", {}).get(req.provider) or custom.get(req.provider)
    if not pinfo:
        raise HTTPException(status_code=400, detail=f"Unknown provider: {req.provider}")

    api_key = os.getenv(pinfo.get("env_key", ""), "") or pinfo.get("api_key", "")
    if not api_key:
        raise HTTPException(status_code=400, detail=f"未配置 API Key ({pinfo.get('env_key', '?')})")

    base_url = pinfo["base_url"]
    model = req.model or (pinfo["models"][0]["id"] if pinfo.get("models") else "default")
    api_type = pinfo.get("api_type", "openai")

    if api_type == "anthropic":
        adapter = AnthropicAdapter(api_key=api_key, base_url=base_url, model=model)
    else:
        adapter = DeepSeekAdapter(api_key=api_key, base_url=base_url, model=model)
    adapter.provider_name = req.provider

    # 注册到 provider map
    startup.provider_adapter_map[req.provider] = adapter
    startup.llm_adapter._all.append(adapter)
    startup.llm_adapter._fallbacks.append(adapter)
    startup.llm_adapter._health[model] = {"failures": 0, "last_fail": 0, "cooldown": 0}

    # 设为主模型
    startup.llm_adapter.set_primary(adapter)
    startup.llm_adapter.provider_name = req.provider
    startup.save_active_provider(req.provider)

    logger.info(f"动态注册并切换: {req.provider}/{model}")
    return {"status": "ok", "provider": req.provider, "model": model, "dynamic": True}


class AddProviderRequest(BaseModel):
    id: str
    name: str
    base_url: str
    api_key: str | None = None
    env_key: str | None = None
    api_type: str = "openai"
    models: list[dict[str, Any]] = []


@router.post("/api/models/add-provider")
async def add_provider(req: AddProviderRequest):
    """添加自定义 provider（持久化到 data/custom_providers.json）。"""
    custom = _load_custom_providers()
    custom[req.id] = {
        "name": req.name,
        "base_url": req.base_url,
        "api_key": req.api_key or "",
        "env_key": req.env_key or "",
        "api_type": req.api_type,
        "models": req.models,
    }
    _save_custom_providers(custom)
    logger.info(f"自定义 provider 已添加: {req.id} ({req.name})")
    return {"status": "ok", "id": req.id}


@router.delete("/api/models/provider/{provider_id}")
async def remove_provider(provider_id: str):
    """删除自定义 provider。"""
    custom = _load_custom_providers()
    if provider_id not in custom:
        raise HTTPException(status_code=404, detail="Not a custom provider")
    del custom[provider_id]
    _save_custom_providers(custom)
    return {"status": "ok"}


class InstallModelRequest(BaseModel):
    model: str


@router.post("/api/models/install")
async def install_local_model(req: InstallModelRequest):
    """安装本地 Ollama 模型。"""
    from adapters.tools.hw_scanner import install_model
    result = install_model(req.model)
    return {"status": "ok", "result": result}


def _scan_local_models() -> dict:
    """扫描本地硬件 + Ollama 模型 + 推荐。"""
    from adapters.tools.hw_scanner import scan_hardware, scan_ollama_models, recommend_model

    hw = scan_hardware()
    ollama = scan_ollama_models()
    catalog = _load_catalog()

    # 已安装模型加上目录元数据
    installed = []
    local_recs = {m["name"]: m for m in catalog.get("local_model_recommendations", [])}
    for m in ollama.get("models", []):
        meta = local_recs.get(m["name"], {})
        installed.append({
            **m,
            "tool_support": meta.get("tool_support", False),
            "chinese": meta.get("chinese", 0.5),
            "desc": meta.get("desc", ""),
        })

    # 推荐
    try:
        rec = recommend_model()
    except Exception:
        rec = {"recommended_model": "qwen3:4b", "advice": []}

    # 当前活跃本地模型
    local_adapter = startup.provider_adapter_map.get("local")
    active_local = getattr(local_adapter, "model", None) if local_adapter else None

    return {
        "hardware": {
            "os": hw.get("os", "?"),
            "arch": hw.get("arch", "?"),
            "cpu": hw.get("cpu", "?"),
            "cpu_cores": hw.get("cpu_cores", 0),
            "ram_gb": hw.get("ram_gb", 0),
            "ram_free_gb": hw.get("ram_free_gb", 0),
            "gpu": hw.get("gpu", "None"),
            "gpu_vram_gb": hw.get("gpu_vram_gb", 0),
        },
        "ollama_running": ollama.get("ollama_running", False),
        "installed_models": installed,
        "recommended_model": rec.get("recommended_model", "qwen3:4b"),
        "recommended_desc": rec.get("recommended_desc", ""),
        "advice": rec.get("advice", []),
        "active_model": active_local,
        "catalog_recommendations": catalog.get("local_model_recommendations", []),
    }
