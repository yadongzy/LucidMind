"""Token Usage API — 实时 token 使用量查询 + 预算配置。"""

from fastapi import APIRouter
from pydantic import BaseModel
from token_tracker import get_tracker
from logs import get_logger

logger = get_logger("api.token")
router = APIRouter()


@router.get("/api/tokens")
async def get_token_stats():
    """获取 token 使用统计（看板数据源）。"""
    return get_tracker().get_stats()


class TokenConfigRequest(BaseModel):
    budget_enabled: bool | None = None
    max_tokens_per_day: int | None = None
    max_tokens_per_hour: int | None = None
    warn_threshold_pct: float | None = None
    auto_switch_threshold_pct: float | None = None
    auto_switch_target: str | None = None
    pause_at_limit: bool | None = None


@router.post("/api/tokens/config")
async def update_token_config(req: TokenConfigRequest):
    """更新 token 预算配置。"""
    config_dict = {k: v for k, v in req.model_dump().items() if v is not None}
    get_tracker().save_config(config_dict)
    logger.info(f"Token 配置已更新: {config_dict}")
    return {"status": "ok", "config": get_tracker()._config.__dict__}


@router.post("/api/tokens/reset")
async def reset_token_stats():
    """重置今日 token 统计。"""
    tracker = get_tracker()
    from datetime import datetime
    today = datetime.now().strftime("%Y-%m-%d")
    tracker._daily[today] = 0
    hour_key = datetime.now().strftime("%Y-%m-%d-%H")
    tracker._hourly[hour_key] = 0
    tracker.flush()
    logger.info("Token 统计已重置")
    return {"status": "ok"}
