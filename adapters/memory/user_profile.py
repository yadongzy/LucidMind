"""S56: 用户画像 — 自动记住用户偏好。

从对话中提取用户偏好（语言、风格、常用工具、专业领域等），
持久化存储，在后续对话中自动注入上下文。
新 Adapter，不修改 brain.py（规则 06）。
"""
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from logs import get_logger

logger = get_logger("profile")

DATA_DIR = Path(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))) / "data"
PROFILES_DIR = DATA_DIR / "profiles"


class UserProfileAdapter:
    """用户画像管理 — 提取、存储、检索用户偏好。"""

    def __init__(self):
        PROFILES_DIR.mkdir(parents=True, exist_ok=True)

    def _path(self, user_id: str) -> Path:
        safe = user_id.replace("/", "_").replace("\\", "_")[:64]
        return PROFILES_DIR / f"{safe}.json"

    def get_profile(self, user_id: str) -> dict[str, Any]:
        """获取用户画像。"""
        p = self._path(user_id)
        if not p.exists():
            return {"user_id": user_id, "preferences": {}, "facts": [], "updated_at": None}
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {"user_id": user_id, "preferences": {}, "facts": [], "updated_at": None}

    def update_preference(self, user_id: str, key: str, value: Any) -> None:
        """更新单个偏好。"""
        profile = self.get_profile(user_id)
        profile["preferences"][key] = value
        profile["updated_at"] = datetime.now(timezone.utc).isoformat()
        self._save(user_id, profile)
        logger.info(f"偏好更新: user={user_id}, {key}={value}")

    def add_fact(self, user_id: str, fact: str) -> None:
        """添加用户事实（去重）。"""
        profile = self.get_profile(user_id)
        facts = profile.get("facts", [])
        if fact not in facts:
            facts.append(fact)
            if len(facts) > 50:
                facts = facts[-50:]
            profile["facts"] = facts
            profile["updated_at"] = datetime.now(timezone.utc).isoformat()
            self._save(user_id, profile)
            logger.info(f"事实添加: user={user_id}, fact={fact[:60]}")

    def get_context_prompt(self, user_id: str) -> str:
        """生成用户画像上下文提示（注入到 LLM 对话中）。"""
        profile = self.get_profile(user_id)
        prefs = profile.get("preferences", {})
        facts = profile.get("facts", [])
        if not prefs and not facts:
            return ""
        parts = ["[用户画像]"]
        if prefs:
            parts.append("偏好: " + "; ".join(f"{k}={v}" for k, v in prefs.items()))
        if facts:
            parts.append("已知: " + "; ".join(facts[-10:]))
        return "\n".join(parts)

    async def extract_preferences(self, user_input: str, llm_adapter=None) -> dict:
        """从用户输入中提取偏好（可选 LLM 辅助）。"""
        extracted = {}
        lower = user_input.lower()
        if "中文" in lower or "chinese" in lower:
            extracted["language"] = "zh-CN"
        elif "english" in lower or "英文" in lower:
            extracted["language"] = "en"
        if "简洁" in lower or "简短" in lower:
            extracted["style"] = "concise"
        elif "详细" in lower or "详尽" in lower:
            extracted["style"] = "detailed"
        if "代码" in lower or "code" in lower:
            extracted["focus"] = "coding"
        return extracted

    def _save(self, user_id: str, profile: dict) -> None:
        p = self._path(user_id)
        try:
            p.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError as e:
            logger.error(f"画像保存失败: {e}")
