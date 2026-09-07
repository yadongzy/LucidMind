"""S40+S45: 用户隔离 + JWT 认证 API。"""
from fastapi import APIRouter, Query, Request, HTTPException
from pydantic import BaseModel
from adapters.auth.user_isolator import get_isolator

router = APIRouter(prefix="/api/auth", tags=["auth"])


class AuthRequest(BaseModel):
    user_id: str
    password: str


async def require_auth(request: Request) -> None:
    """HTTP API 统一鉴权依赖（bootstrap 模式）。

    - 从未有用户用密码注册 → 本地单机模式，放行（保持现有前端/CLI 兼容）
    - 一旦有密码用户存在 → 除 /api/auth 外的所有 HTTP 接口要求
      `Authorization: Bearer <JWT>` 或 `?token=<JWT>`
    """
    iso = get_isolator()
    if not iso.has_password_users():
        return
    token = None
    auth_header = request.headers.get("authorization", "")
    if auth_header.lower().startswith("bearer "):
        token = auth_header[7:].strip()
    if not token:
        token = request.query_params.get("token")
    if not token or not iso.validate_token(token):
        raise HTTPException(status_code=401, detail="未认证或令牌无效")


@router.post("/register")
async def register(req: AuthRequest):
    """S45: 带密码注册，返回 JWT。已存在的用户返回 409。"""
    iso = get_isolator()
    try:
        iso.register_with_password(req.user_id, req.password)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    token = iso.generate_token(req.user_id)
    return {"user_id": req.user_id, "token": token}


@router.post("/login")
async def login(req: AuthRequest):
    """S45: 密码登录，返回 JWT。"""
    iso = get_isolator()
    token = iso.login(req.user_id, req.password)
    if not token:
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    return {"user_id": req.user_id, "token": token}


@router.get("/session")
async def get_session(token: str = Query(...), session_id: str = "default"):
    """S45: 用 JWT 获取隔离的 session_id。"""
    iso = get_isolator()
    user_id = iso.validate_token(token)
    if not user_id:
        raise HTTPException(status_code=401, detail="令牌无效或已过期")
    isolated = iso.get_isolated_session_id(user_id, session_id)
    return {"user_id": user_id, "isolated_session_id": isolated}


@router.get("/validate")
async def validate(token: str = Query(...)):
    """S45: 验证 JWT。"""
    iso = get_isolator()
    user_id = iso.validate_token(token)
    if not user_id:
        return {"valid": False}
    return {"valid": True, "user_id": user_id}


@router.get("/stats")
async def stats():
    """用户统计。"""
    return get_isolator().get_stats()
