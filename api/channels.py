"""多通道管理 API — Telegram / 飞书 / 企业微信 / 微信 Webhook 端点 + ngrok 内网穿透。"""

import asyncio
import os
import shutil
import subprocess
from pathlib import Path
from fastapi import APIRouter, Request, Query
from fastapi.responses import PlainTextResponse
from logs import get_logger

logger = get_logger("api.channels")
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


# ── 各通道环境变量映射 ──
_CHANNEL_ENV_KEYS = {
    "telegram": ["TELEGRAM_BOT_TOKEN", "TELEGRAM_ALLOWED_USERS"],
    "feishu": ["FEISHU_APP_ID", "FEISHU_APP_SECRET"],
    "wecom": ["WECOM_CORP_ID", "WECOM_AGENT_ID", "WECOM_SECRET", "WECOM_TOKEN"],
    "wechat": ["GEWECHAT_BASE_URL", "GEWECHAT_TOKEN", "GEWECHAT_CALLBACK_URL", "WECHAT_ALLOWED_WXIDS"],
}


def _update_env_file(updates: dict[str, str]):
    """更新 .env 文件中的键值对，不存在则追加。"""
    env_path = Path(os.getcwd()) / ".env"
    lines = []
    if env_path.exists():
        lines = env_path.read_text(encoding="utf-8").splitlines()

    for key, value in updates.items():
        found = False
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if "=" in stripped and stripped.split("=", 1)[0].strip() == key:
                lines[i] = f"{key}={value}"
                found = True
                break
        if not found:
            lines.append(f"{key}={value}")
        # 同步到当前进程环境变量
        os.environ[key] = value

    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


@router.post("/{name}/config")
async def save_channel_config(name: str, request: Request):
    """保存通道配置到 .env 并重新初始化通道适配器。"""
    allowed_keys = _CHANNEL_ENV_KEYS.get(name)
    if not allowed_keys:
        return {"status": "error", "message": f"未知通道: {name}"}

    body = await request.json()
    updates = {}
    for key in allowed_keys:
        val = body.get(key, "").strip()
        if val:
            updates[key] = val

    if not updates:
        return {"status": "error", "message": "请至少填写一个配置项"}

    # 写入 .env
    try:
        _update_env_file(updates)
        logger.info(f"通道配置已保存: {name} — {list(updates.keys())}")
    except Exception as e:
        return {"status": "error", "message": f"保存 .env 失败: {e}"}

    # 重新初始化通道适配器
    ch_map = {"telegram": _telegram, "feishu": _feishu, "wecom": _wecom, "wechat": _wechat}
    ch = ch_map.get(name)
    if ch:
        try:
            await ch.stop()
        except Exception:
            pass
        # 更新适配器内部配置
        if name == "telegram":
            ch._token = updates.get("TELEGRAM_BOT_TOKEN", ch._token)
            raw = updates.get("TELEGRAM_ALLOWED_USERS", "")
            if raw:
                ch._allowed_users = {int(x.strip()) for x in raw.split(",") if x.strip()}
        elif name == "feishu":
            ch._app_id = updates.get("FEISHU_APP_ID", ch._app_id)
            ch._app_secret = updates.get("FEISHU_APP_SECRET", ch._app_secret)
        elif name == "wecom":
            ch._corp_id = updates.get("WECOM_CORP_ID", getattr(ch, '_corp_id', ''))
            ch._agent_id = updates.get("WECOM_AGENT_ID", getattr(ch, '_agent_id', ''))
            ch._secret = updates.get("WECOM_SECRET", getattr(ch, '_secret', ''))
            ch._token_str = updates.get("WECOM_TOKEN", getattr(ch, '_token_str', ''))
        elif name == "wechat":
            ch._base_url = updates.get("GEWECHAT_BASE_URL", getattr(ch, '_base_url', ''))
            ch._app_id = updates.get("GEWECHAT_TOKEN", getattr(ch, '_app_id', ''))
            ch._callback_url = updates.get("GEWECHAT_CALLBACK_URL", getattr(ch, '_callback_url', ''))
        # 重启
        try:
            await ch.start(ch._on_message)
            return {"status": "ok", "message": f"{name} 配置已保存并重启成功"}
        except Exception as e:
            return {"status": "ok", "message": f"配置已保存，但启动失败: {e}"}

    return {"status": "ok", "message": f"{name} 配置已保存（重启服务后生效）"}


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


# ── ngrok 内网穿透管理 ──

_ngrok_process: subprocess.Popen | None = None
_ngrok_url: str = ""


@router.get("/ngrok/status")
async def ngrok_status():
    """检测 ngrok 安装状态和运行状态。"""
    installed = shutil.which("ngrok") is not None
    running = _ngrok_process is not None and _ngrok_process.poll() is None
    return {
        "installed": installed,
        "running": running,
        "url": _ngrok_url if running else "",
    }


@router.post("/ngrok/install")
async def ngrok_install():
    """通过 brew 安装 ngrok（仅 macOS）。"""
    if shutil.which("ngrok"):
        return {"status": "ok", "message": "ngrok 已安装"}
    try:
        proc = await asyncio.create_subprocess_exec(
            "brew", "install", "ngrok",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=120)
        output = stdout.decode("utf-8", errors="replace")[-500:]
        if proc.returncode == 0:
            logger.info("ngrok 安装成功")
            return {"status": "ok", "message": "ngrok 安装成功"}
        return {"status": "error", "message": f"安装失败 (exit {proc.returncode}): {output}"}
    except asyncio.TimeoutError:
        return {"status": "error", "message": "安装超时（120s），请手动运行 brew install ngrok"}
    except FileNotFoundError:
        return {"status": "error", "message": "未找到 brew，请先安装 Homebrew: https://brew.sh"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.post("/ngrok/authtoken")
async def ngrok_authtoken(request: Request):
    """配置 ngrok authtoken。"""
    body = await request.json()
    token = body.get("token", "").strip()
    if not token:
        return {"status": "error", "message": "请输入 authtoken"}
    if not shutil.which("ngrok"):
        return {"status": "error", "message": "ngrok 未安装"}
    # 确保 ngrok 配置目录存在
    ngrok_cfg_dir = Path.home() / "Library" / "Application Support" / "ngrok"
    if not ngrok_cfg_dir.exists():
        ngrok_cfg_dir.mkdir(parents=True, exist_ok=True)
    try:
        proc = await asyncio.create_subprocess_exec(
            "ngrok", "config", "add-authtoken", token,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
        output = stdout.decode("utf-8", errors="replace").strip()
        if proc.returncode == 0:
            logger.info(f"ngrok authtoken 已配置")
            return {"status": "ok", "message": "authtoken 配置成功"}
        return {"status": "error", "message": output or "配置失败"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.post("/ngrok/start")
async def ngrok_start():
    """启动 ngrok 隧道（端口 8765）。"""
    global _ngrok_process, _ngrok_url

    if not shutil.which("ngrok"):
        return {"status": "error", "message": "ngrok 未安装，请先安装"}

    # 已在运行
    if _ngrok_process and _ngrok_process.poll() is None and _ngrok_url:
        return {"status": "ok", "url": _ngrok_url, "message": "ngrok 已在运行"}

    # 启动 ngrok（清除代理环境变量，免费版不支持代理）
    try:
        clean_env = {k: v for k, v in os.environ.items()
                     if k.lower() not in ("http_proxy", "https_proxy", "all_proxy", "no_proxy")}
        _ngrok_process = subprocess.Popen(
            ["ngrok", "http", "8765", "--log=stdout"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=clean_env,
        )
        # 等待获取公网 URL（通过 ngrok API）
        _ngrok_url = ""
        import httpx
        for attempt in range(15):
            await asyncio.sleep(1)
            if _ngrok_process.poll() is not None:
                return {"status": "error", "message": "ngrok 启动后立即退出，请检查 ngrok 配置（可能需要 ngrok authtoken）"}
            try:
                async with httpx.AsyncClient(timeout=3) as client:
                    resp = await client.get("http://127.0.0.1:4040/api/tunnels")
                    if resp.status_code == 200:
                        tunnels = resp.json().get("tunnels", [])
                        for t in tunnels:
                            if t.get("proto") == "https":
                                _ngrok_url = t["public_url"]
                                break
                        if not _ngrok_url and tunnels:
                            _ngrok_url = tunnels[0].get("public_url", "")
                        if _ngrok_url:
                            logger.info(f"ngrok 隧道已建立: {_ngrok_url}")
                            return {"status": "ok", "url": _ngrok_url, "message": "ngrok 隧道已建立"}
            except Exception:
                continue

        return {"status": "error", "message": "ngrok 启动超时，无法获取公网地址。请检查 ngrok authtoken 是否已配置"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.post("/ngrok/stop")
async def ngrok_stop():
    """停止 ngrok 隧道。"""
    global _ngrok_process, _ngrok_url
    if _ngrok_process and _ngrok_process.poll() is None:
        _ngrok_process.terminate()
        try:
            _ngrok_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _ngrok_process.kill()
        logger.info("ngrok 隧道已停止")
    _ngrok_process = None
    _ngrok_url = ""
    return {"status": "ok", "message": "ngrok 已停止"}
