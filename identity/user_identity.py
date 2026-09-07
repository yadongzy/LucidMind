"""多用户身份管理器 — 每个用户拥有独立的灵魂空间。

架构:
  identity/              ← 系统默认模板（出厂设置）
  ├── CORE.md            ← 不可变内核（所有用户共享，不复制）
  ├── SOUL.md            ← 默认灵魂模板
  ├── USER.md            ← 默认用户模板
  ├── BOOTSTRAP.md       ← 首次引导模板
  ├── personas/          ← 系统预置人格（由 personas.py 管理）
  └── soul_engine.py     ← 灵魂进化引擎

  data/users/{user_id}/identity/   ← 用户个性化副本
  ├── SOUL.md            ← 用户自定义灵魂
  ├── USER.md            ← 用户画像（展示层，权威数据在 data/profiles/）
  ├── BOOTSTRAP.md       ← 用户引导状态
  ├── custom_prompts/    ← 用户自定义提示词片段（*.md 自动注入）
  └── personas/          ← 用户自定义人格（由本模块管理）

规则:
  - CORE.md 永远从系统目录加载，用户不可覆盖
  - SOUL.md / USER.md / BOOTSTRAP.md 首次使用时从模板复制到用户目录
  - 用户可以直接编辑自己目录下的文件
  - custom_prompts/ 下所有 .md 文件自动注入系统提示词
"""

import shutil
from pathlib import Path
from typing import Any

from logs import get_logger

logger = get_logger("user_identity")

_SYSTEM_IDENTITY_DIR = Path(__file__).parent
_DATA_DIR = Path(__file__).parent.parent / "data"
_USERS_DIR = _DATA_DIR / "users"

# 系统级文件（不复制到用户目录）
_SYSTEM_ONLY_FILES = {"CORE.md"}

# 用户可自定义的文件（首次使用时从模板复制）
_USER_TEMPLATE_FILES = {"SOUL.md", "USER.md", "BOOTSTRAP.md"}


class UserIdentityManager:
    """多用户身份管理器。"""

    def __init__(self):
        self._cache: dict[str, dict[str, Any]] = {}  # user_id -> {path: {mtime, content}}

    def _user_identity_dir(self, user_id: str) -> Path:
        """获取用户的身份目录。"""
        safe_id = user_id.replace("/", "_").replace("\\", "_").replace("..", "_")[:64]
        return _USERS_DIR / safe_id / "identity"

    def ensure_user_dir(self, user_id: str) -> Path:
        """确保用户身份目录存在，首次使用时从模板复制。"""
        user_dir = self._user_identity_dir(user_id)
        if user_dir.exists():
            return user_dir

        user_dir.mkdir(parents=True, exist_ok=True)
        (user_dir / "custom_prompts").mkdir(exist_ok=True)
        (user_dir / "personas").mkdir(exist_ok=True)

        # 复制模板文件到用户目录
        for filename in _USER_TEMPLATE_FILES:
            src = _SYSTEM_IDENTITY_DIR / filename
            dst = user_dir / filename
            if src.exists() and not dst.exists():
                shutil.copy2(src, dst)
                logger.info(f"[{user_id}] 初始化身份文件: {filename}")

        logger.info(f"[{user_id}] 身份目录已创建: {user_dir}")
        return user_dir

    def _load_file(self, path: Path, user_id: str = "_system") -> str:
        """加载文件，带修改时间缓存。"""
        if not path.exists():
            return ""
        try:
            key = str(path)
            mtime = path.stat().st_mtime
            user_cache = self._cache.setdefault(user_id, {})
            cached = user_cache.get(key)
            if cached and cached["mtime"] == mtime:
                return cached["content"]
            content = path.read_text(encoding="utf-8").strip()
            user_cache[key] = {"mtime": mtime, "content": content}
            return content
        except Exception:
            return ""

    # ── 系统级文件（所有用户共享） ──

    def get_core(self) -> str:
        """获取不可变内核（CORE.md）。所有用户共享。"""
        return self._load_file(_SYSTEM_IDENTITY_DIR / "CORE.md")

    # ── 用户级文件（per-user，fallback 到系统默认） ──

    def get_soul(self, user_id: str) -> str:
        """获取用户的灵魂文件。优先用户自定义，fallback 系统默认。"""
        user_dir = self._user_identity_dir(user_id)
        user_soul = user_dir / "SOUL.md"
        if user_soul.exists():
            return self._load_file(user_soul, user_id)
        return self._load_file(_SYSTEM_IDENTITY_DIR / "SOUL.md")

    def get_user_profile(self, user_id: str) -> str:
        """获取用户画像。优先用户自定义，fallback 系统默认。"""
        user_dir = self._user_identity_dir(user_id)
        user_file = user_dir / "USER.md"
        if user_file.exists():
            return self._load_file(user_file, user_id)
        return self._load_file(_SYSTEM_IDENTITY_DIR / "USER.md")

    def get_bootstrap(self, user_id: str) -> str:
        """获取引导文件。优先用户自定义。"""
        user_dir = self._user_identity_dir(user_id)
        user_file = user_dir / "BOOTSTRAP.md"
        if user_file.exists():
            return self._load_file(user_file, user_id)
        return self._load_file(_SYSTEM_IDENTITY_DIR / "BOOTSTRAP.md")

    # ── 用户自定义提示词扩展 ──

    def get_custom_prompts(self, user_id: str) -> list[dict[str, str]]:
        """获取用户的所有自定义提示词片段。

        Returns:
            [{"name": "coding_style", "content": "..."}, ...]
        """
        user_dir = self._user_identity_dir(user_id)
        prompts_dir = user_dir / "custom_prompts"
        if not prompts_dir.exists():
            return []

        result = []
        for f in sorted(prompts_dir.glob("*.md")):
            content = self._load_file(f, user_id)
            if content:
                result.append({"name": f.stem, "content": content})
        return result

    # ── 用户自定义人格 ──

    def get_user_personas(self, user_id: str) -> list[dict[str, str]]:
        """获取用户的自定义人格列表。"""
        user_dir = self._user_identity_dir(user_id)
        personas_dir = user_dir / "personas"
        if not personas_dir.exists():
            return []

        result = []
        for f in sorted(personas_dir.glob("*.md")):
            content = self._load_file(f, user_id)
            if content:
                first_line = content.split("\n")[0].replace("#", "").strip()
                result.append({
                    "name": f.stem,
                    "description": first_line or f.stem,
                    "content": content,
                })
        return result

    # ── 用户身份文件写入 ──

    def update_soul(self, user_id: str, content: str) -> bool:
        """更新用户的灵魂文件。"""
        self.ensure_user_dir(user_id)
        user_dir = self._user_identity_dir(user_id)
        try:
            (user_dir / "SOUL.md").write_text(content, encoding="utf-8")
            # 清除缓存
            user_cache = self._cache.get(user_id, {})
            user_cache.pop(str(user_dir / "SOUL.md"), None)
            logger.info(f"[{user_id}] SOUL.md 已更新 ({len(content)} 字符)")
            return True
        except Exception as e:
            logger.error(f"[{user_id}] SOUL.md 更新失败: {e}")
            return False

    def update_user_profile(self, user_id: str, content: str) -> bool:
        """更新用户画像。"""
        self.ensure_user_dir(user_id)
        user_dir = self._user_identity_dir(user_id)
        try:
            (user_dir / "USER.md").write_text(content, encoding="utf-8")
            user_cache = self._cache.get(user_id, {})
            user_cache.pop(str(user_dir / "USER.md"), None)
            logger.info(f"[{user_id}] USER.md 已更新 ({len(content)} 字符)")
            return True
        except Exception as e:
            logger.error(f"[{user_id}] USER.md 更新失败: {e}")
            return False

    def add_custom_prompt(self, user_id: str, name: str, content: str) -> bool:
        """添加用户自定义提示词片段。"""
        self.ensure_user_dir(user_id)
        user_dir = self._user_identity_dir(user_id)
        prompts_dir = user_dir / "custom_prompts"
        prompts_dir.mkdir(exist_ok=True)

        safe_name = name.replace("/", "_").replace("\\", "_").replace("..", "_")[:32]
        try:
            (prompts_dir / f"{safe_name}.md").write_text(content, encoding="utf-8")
            user_cache = self._cache.get(user_id, {})
            user_cache.pop(str(prompts_dir / f"{safe_name}.md"), None)
            logger.info(f"[{user_id}] 自定义提示词 '{safe_name}' 已添加")
            return True
        except Exception as e:
            logger.error(f"[{user_id}] 自定义提示词添加失败: {e}")
            return False

    def remove_custom_prompt(self, user_id: str, name: str) -> bool:
        """删除用户自定义提示词片段。"""
        user_dir = self._user_identity_dir(user_id)
        path = user_dir / "custom_prompts" / f"{name}.md"
        if path.exists():
            path.unlink()
            user_cache = self._cache.get(user_id, {})
            user_cache.pop(str(path), None)
            logger.info(f"[{user_id}] 自定义提示词 '{name}' 已删除")
            return True
        return False

    def add_user_persona(self, user_id: str, name: str, content: str) -> bool:
        """添加用户自定义人格。"""
        self.ensure_user_dir(user_id)
        user_dir = self._user_identity_dir(user_id)
        personas_dir = user_dir / "personas"
        personas_dir.mkdir(exist_ok=True)

        safe_name = name.replace("/", "_").replace("\\", "_").replace("..", "_")[:32]
        try:
            (personas_dir / f"{safe_name}.md").write_text(content, encoding="utf-8")
            logger.info(f"[{user_id}] 自定义人格 '{safe_name}' 已添加")
            return True
        except Exception as e:
            logger.error(f"[{user_id}] 自定义人格添加失败: {e}")
            return False

    # ── 构建完整的系统提示词身份部分 ──

    def build_identity_prompt(self, user_id: str = "default", profile_context: str = "") -> str:
        """构建完整的身份提示词（供 brain._build_messages 使用）。

        结构（按注入顺序）:
          1. CORE.md — 不可变内核
          2. SOUL.md — 用户灵魂
          3. USER.md — 用户画像模板
          4. profile_context — 程序化提取的用户偏好（来自 UserProfileAdapter）
          5. custom_prompts/*.md — 用户自定义片段

        Args:
            user_id: 用户 ID
            profile_context: 来自 UserProfileAdapter.get_context_prompt() 的用户偏好文本
        """
        parts = []

        # 1. 不可变内核（所有用户共享）
        core = self.get_core()
        if core:
            parts.append(core)

        # 2. 用户灵魂
        soul = self.get_soul(user_id)
        if soul:
            parts.append(soul)

        # 3. 用户画像（USER.md 模板 + 程序化偏好）
        user_profile = self.get_user_profile(user_id)
        if user_profile:
            parts.append(user_profile)
        if profile_context:
            parts.append(profile_context)

        # 4. 用户自定义提示词
        custom = self.get_custom_prompts(user_id)
        if custom:
            custom_text = "\n\n".join(
                f"## {p['name']}\n{p['content']}" for p in custom
            )
            parts.append(custom_text)

        return "\n\n".join(parts)

    def get_user_info(self, user_id: str) -> dict[str, Any]:
        """获取用户身份信息摘要（供 API 使用）。"""
        user_dir = self._user_identity_dir(user_id)
        has_dir = user_dir.exists()
        custom_prompts = self.get_custom_prompts(user_id) if has_dir else []
        user_personas = self.get_user_personas(user_id) if has_dir else []

        return {
            "user_id": user_id,
            "has_custom_identity": has_dir,
            "files": {
                "soul": (user_dir / "SOUL.md").exists() if has_dir else False,
                "user_profile": (user_dir / "USER.md").exists() if has_dir else False,
                "bootstrap": (user_dir / "BOOTSTRAP.md").exists() if has_dir else False,
            },
            "custom_prompts": [p["name"] for p in custom_prompts],
            "custom_personas": [p["name"] for p in user_personas],
        }


# ── 单例 ──

_manager: UserIdentityManager | None = None


def get_user_identity_manager() -> UserIdentityManager:
    """获取全局 UserIdentityManager 单例。"""
    global _manager
    if _manager is None:
        _manager = UserIdentityManager()
    return _manager
