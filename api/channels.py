"""多通道管理 API — Telegram / 飞书 / 企业微信 / 微信 Webhook 端点。"""

from fastapi import APIRouter, Request, Query
from fastapi.responses import PlainTextResponse

router = APIRouter(prefix="/api/channel", tags=["channels"])

_telegram = None
_feishu = None
_wecom = None
_wechat = None


def init(telegram=None, feishu=None, wecom=None, wechat=None):
    """由 main.py 调用，注入各通道适配器引用。"""
    global _telegram, _feishu, _wecom, _wechat
    _telegram = telegram
    _feishu = feishu
    _wecom = wecom
    _wechat = wechat


@router.get("/status")
async def channel_status():
    """返回所有通道的状态。"""
    channels = []
    if _telegram:
        channels.append({
            "name": "telegram", "label": "Telegram",
            "configured": bool(_telegram._token),
            "running": _telegram._task is not None and not _telegram._task.done() if _telegram._task else False,
        })
    if _feishu:
        channels.append({
            "name": "feishu", "label": "飞书",
            "configured": bool(_feishu._app_id and _feishu._app_secret),
            "running": bool(_feishu._app_id),
        })
    if _wecom:
        channels.append({
            "name": "wecom", "label": "企业微信",
            "configured": bool(_wecom._corp_id and _wecom._secret),
            "running": bool(_wecom._corp_id),
        })
    if _wechat:
        channels.append({
            "name": "wechat", "label": "微信 (GeweChat)",
            "configured": bool(_wechat._app_id),
            "running": bool(_wechat._app_id),
        })
    return {"channels": channels, "total": len(channels)}


@router.post("/{name}/test")
async def test_channel(name: str):
    """测试通道连接。"""
    ch_map = {"telegram": _telegram, "feishu": _feishu, "wecom": _wecom, "wechat": _wechat}
    ch = ch_map.get(name)
    if not ch:
        return {"status": "error", "message": f"未知通道: {name}"}
    try:
        if name == "telegram":
            if not ch._token:
                return {"status": "error", "message": "未配置 TELEGRAM_BOT_TOKEN"}
            return {"status": "ok", "message": f"Telegram 已配置, polling={'运行中' if (ch._task and not ch._task.done()) else '未启动'}"}
        elif name == "feishu":
            if not ch._app_id:
                return {"status": "error", "message": "未配置 FEISHU_APP_ID"}
            return {"status": "ok", "message": f"飞书已配置, app_id={ch._app_id[:8]}..."}
        elif name == "wecom":
            if not ch._corp_id:
                return {"status": "error", "message": "未配置 WECOM_CORP_ID"}
            return {"status": "ok", "message": f"企微已配置, corp={ch._corp_id[:8]}..."}
        elif name == "wechat":
            if not ch._app_id:
                return {"status": "error", "message": "未配置 GEWECHAT_TOKEN"}
            return {"status": "ok", "message": f"微信已配置, appId={ch._app_id[:8]}..."}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.post("/{name}/restart")
async def restart_channel(name: str):
    """重启通道。"""
    ch_map = {"telegram": _telegram, "feishu": _feishu, "wecom": _wecom, "wechat": _wechat}
    ch = ch_map.get(name)
    if not ch:
        return {"status": "error", "message": f"未知通道: {name}"}
    try:
        await ch.stop()
        await ch.start(None)
        return {"status": "ok", "message": f"{name} 已重启"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ── 飞书 Webhook ──

@router.post("/feishu/webhook")
async def feishu_webhook(request: Request):
    """飞书事件回调端点。"""
    if not _feishu:
        return {"code": -1, "msg": "飞书通道未初始化"}
    body = await request.json()
    result = await _feishu.handle_webhook(body)
    return result


# ── 企业微信 Webhook ──

@router.get("/wecom/webhook")
async def wecom_verify(
    msg_signature: str = Query(""),
    timestamp: str = Query(""),
    nonce: str = Query(""),
    echostr: str = Query(""),
):
    """企业微信 URL 验证（GET 请求）。"""
    if not _wecom:
        return PlainTextResponse("not configured")
    result = _wecom.verify_url(msg_signature, timestamp, nonce, echostr)
    return PlainTextResponse(result)


@router.post("/wecom/webhook")
async def wecom_webhook(
    request: Request,
    msg_signature: str = Query(""),
    timestamp: str = Query(""),
    nonce: str = Query(""),
):
    """企业微信消息回调端点。"""
    if not _wecom:
        return PlainTextResponse("not configured")
    body = await request.body()
    result = await _wecom.handle_webhook(
        body.decode("utf-8"), msg_signature, timestamp, nonce
    )
    return PlainTextResponse(result)


# ── 微信 (GeweChat) Webhook ──

@router.post("/wechat/webhook")
async def wechat_webhook(request: Request):
    """GeweChat 消息回调端点。"""
    if not _wechat:
        return {"ret": -1, "msg": "微信通道未初始化"}
    body = await request.json()
    result = await _wechat.handle_webhook(body)
    return result


@router.get("/wechat/qrcode")
async def wechat_qrcode():
    """获取微信登录二维码。"""
    if not _wechat:
        return {"error": "微信通道未初始化"}
    return await _wechat.get_login_qrcode()


@router.get("/wechat/login-status")
async def wechat_login_status():
    """检查微信登录状态。"""
    if not _wechat:
        return {"error": "微信通道未初始化"}
    return await _wechat.check_login_status()
