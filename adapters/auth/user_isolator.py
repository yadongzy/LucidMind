"""S40+S45: 多用户隔离 + JWT 认证。

通过 user_id 前缀隔离 session_id，实现逻辑上的多用户。
S45: JWT 令牌认证，支持过期、密码哈希。

不修改 brain.py（规则 06）。
"""
import hashlib
import os
import time
from typing import Any

import jwt

from logs import get_logger

logger = get_logger("auth")


class UserIsolator:
    """用户隔离器 — 为每个用户生成隔离的 session namespace。"""

    def __init__(self):
        self._users: dict[str, dict] = {}  # user_id → user_info
        self._secret = os.getenv("JWT_SECRET", "")
        if not self._secret:
            self._secret = "lucidmind_default_secret_change_me"
            logger.warning("JWT_SECRET 未设置，使用不安全的默认值 — 请在 .env 中设置 JWT_SECRET")
        self._passwords: dict[str, str] = {}  # user_id → "salt_hex$pbkdf2_hex"
        self._pbkdf2_iterations = 100_000

    def register_or_get(self, user_id: str = "default") -> dict:
        """注册或获取用户信息。"""
        if user_id not in self._users:
            self._users[user_id] = {
                "user_id": user_id,
                "created_at": time.time(),
                "session_prefix": f"u_{hashlib.md5(user_id.encode()).hexdigest()[:6]}_",
                "active_sessions": [],
            }
            logger.info(f"新用户注册: {user_id}")
        return self._users[user_id]

    def get_isolated_session_id(self, user_id: str, session_id: str = "default") -> str:
        """生成隔离的 session_id — 加用户前缀。"""
        user = self.register_or_get(user_id)
        prefix = user["session_prefix"]
        if session_id.startswith(prefix):
            return session_id  # 已隔离
        isolated = f"{prefix}{session_id}"
        if isolated not in user["active_sessions"]:
            user["active_sessions"].append(isolated)
        return isolated

    def get_user_sessions(self, user_id: str) -> list[str]:
        """获取用户的所有会话。"""
        user = self._users.get(user_id)
        if not user:
            return []
        return user.get("active_sessions", [])

    def generate_token(self, user_id: str, expires_hours: int = 24) -> str:
        """S45: 生成 JWT 令牌。"""
        payload = {
            "sub": user_id,
            "iat": time.time(),
            "exp": time.time() + expires_hours * 3600,
        }
        token = jwt.encode(payload, self._secret, algorithm="HS256")
        return token

    def validate_token(self, token: str) -> str | None:
        """S45: 验证 JWT 令牌，返回 user_id 或 None。"""
        try:
            payload = jwt.decode(token, self._secret, algorithms=["HS256"])
            return payload.get("sub")
        except jwt.ExpiredSignatureError:
            logger.warning("JWT 已过期")
            return None
        except jwt.InvalidTokenError:
            logger.warning("JWT 无效")
            return None

    def has_password_users(self) -> bool:
        """是否存在密码注册的用户（bootstrap 模式判定：无用户时 HTTP API 放行）。"""
        return bool(self._passwords)

    def _hash_password(self, password: str, salt: bytes) -> str:
        """PBKDF2-SHA256 加盐哈希。"""
        return hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt, self._pbkdf2_iterations
        ).hex()

    def register_with_password(self, user_id: str, password: str) -> dict:
        """S45: 带密码注册。已存在的用户会被拒绝（防止账号接管）。"""
        if user_id in self._passwords:
            raise ValueError(f"用户 {user_id} 已存在，请直接登录")
        user = self.register_or_get(user_id)
        salt = os.urandom(16)
        self._passwords[user_id] = f"{salt.hex()}${self._hash_password(password, salt)}"
        logger.info(f"用户注册(密码): {user_id}")
        return user

    def login(self, user_id: str, password: str) -> str | None:
        """S45: 密码登录，返回 JWT 或 None。"""
        stored = self._passwords.get(user_id)
        if not stored:
            return None
        try:
            salt_hex, digest = stored.split("$", 1)
            candidate = self._hash_password(password, bytes.fromhex(salt_hex))
        except ValueError:
            return None
        if candidate != digest:
            logger.warning(f"登录失败: {user_id}")
            return None
        logger.info(f"登录成功: {user_id}")
        return self.generate_token(user_id)

    def get_stats(self) -> dict[str, Any]:
        """获取用户统计。"""
        return {
            "total_users": len(self._users),
            "users": [
                {"user_id": u["user_id"], "sessions": len(u["active_sessions"])}
                for u in self._users.values()
            ],
        }


# 全局单例
_isolator: UserIsolator | None = None

def get_isolator() -> UserIsolator:
    global _isolator
    if _isolator is None:
        _isolator = UserIsolator()
    return _isolator
