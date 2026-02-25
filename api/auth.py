"""S40+S45: 用户隔离 + JWT 认证 API。"""
from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel
from adapters.auth.user_isolator import get_isolator

router = APIRouter(prefix="/api/auth", tags=["auth"])


class AuthRequest(BaseModel):
    user_id: str
    password: str


@router.post("/register")
async def register(req: AuthRequest):
    """S45: 带密码注册，返回 JWT。"""
    iso = get_isolator()
    iso.register_with_password(req.user_id, req.password)
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
