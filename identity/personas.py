"""Persona Manager — 多角色/分身系统。

支持多个人格配置，共享记忆但独立上下文和身份。
对标 OpenClaw agents/ 的多角色架构。

用法:
- 默认人格: identity/SOUL.md + CORE.md
- 自定义人格: identity/personas/<name>.md
- 切换人格: persona_manager.switch("coder")
- 列出人格: persona_manager.list_personas()
"""

import json
from pathlib import Path
from typing import Any

from logs import get_logger

logger = get_logger("persona")

_PERSONAS_DIR = Path(__file__).parent / "personas"
_CONFIG_PATH = Path(__file__).parent.parent / "data" / "persona_config.json"

# 默认人格模板
_DEFAULT_PERSONA_TEMPLATE = """# {name}

## 角色定义
{description}

## 行为特征
{traits}

## 专长领域
{expertise}

## 约束
- 遵守 CORE.md 铁律（诚实、安全、隐私）
- 共享主记忆库，但以本角色视角回应
"""


class PersonaManager:
    """人格管理器 — 管理多个AI角色/分身。"""

    def __init__(self):
        self._current: str = "default"
        self._personas: dict[str, dict] = {}
        self._personas_dir = _PERSONAS_DIR
        self._personas_dir.mkdir(parents=True, exist_ok=True)
        self._load_config()
        self._discover_personas()

    def _load_config(self) -> None:
        """加载人格配置。"""
        if _CONFIG_PATH.exists():
            try:
                cfg = json.loads(_CONFIG_PATH.read_text())
                self._current = cfg.get("current", "default")
            except Exception:
                pass

    def _save_config(self) -> None:
        """保存人格配置。"""
        _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        cfg = {"current": self._current, "personas": list(self._personas.keys())}
        _CONFIG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2))

    def _discover_personas(self) -> None:
        """扫描 personas/ 目录，加载所有人格定义。"""
        self._personas["default"] = {
            "name": "default",
            "description": "默认人格（SOUL.md定义）",
            "file": None,
            "prompt_override": None,
        }
        for f in self._personas_dir.glob("*.md"):
            name = f.stem
            content = f.read_text(encoding="utf-8")
            # 提取第一行标题作为描述
            first_line = content.strip().split("\n")[0].replace("#", "").strip()
            self._personas[name] = {
                "name": name,
                "description": first_line or name,
                "file": str(f),
                "prompt_override": content,
            }
        logger.info(f"人格发现: {len(self._personas)} 个 ({', '.join(self._personas.keys())})")

    def list_personas(self) -> list[dict[str, Any]]:
        """列出所有可用人格。"""
        result = []
        for name, p in self._personas.items():
            result.append({
                "name": name,
                "description": p["description"],
                "active": name == self._current,
            })
        return result

    def get_current(self) -> str:
        """获取当前人格名称。"""
        return self._current

    def get_persona_prompt(self, name: str | None = None) -> str | None:
        """获取人格的 prompt override（用于注入到 system prompt）。"""
        name = name or self._current
        persona = self._personas.get(name)
        if not persona or not persona.get("prompt_override"):
            return None
        return persona["prompt_override"]

    def switch(self, name: str) -> dict:
        """切换当前人格。"""
        if name not in self._personas:
            return {"success": False, "error": f"人格 '{name}' 不存在"}
        self._current = name
        self._save_config()
        logger.info(f"人格切换: → {name}")
        return {"success": True, "persona": name, "description": self._personas[name]["description"]}

    def create(self, name: str, description: str, traits: str = "", expertise: str = "") -> dict:
        """创建新人格。"""
        if name in self._personas:
            return {"success": False, "error": f"人格 '{name}' 已存在"}
        # 生成人格文件
        content = _DEFAULT_PERSONA_TEMPLATE.format(
            name=name,
            description=description or f"{name} 角色",
            traits=traits or "- 待定义",
            expertise=expertise or "- 通用",
        )
        filepath = self._personas_dir / f"{name}.md"
        filepath.write_text(content, encoding="utf-8")
        self._personas[name] = {
            "name": name,
            "description": description,
            "file": str(filepath),
            "prompt_override": content,
        }
        self._save_config()
        logger.info(f"人格创建: {name} — {description}")
        return {"success": True, "persona": name}

    def delete(self, name: str) -> dict:
        """删除人格（不能删除 default）。"""
        if name == "default":
            return {"success": False, "error": "不能删除默认人格"}
        if name not in self._personas:
            return {"success": False, "error": f"人格 '{name}' 不存在"}
        filepath = self._personas.get(name, {}).get("file")
        if filepath:
            Path(filepath).unlink(missing_ok=True)
        del self._personas[name]
        if self._current == name:
            self._current = "default"
        self._save_config()
        logger.info(f"人格删除: {name}")
        return {"success": True}


# 单例
_manager: PersonaManager | None = None

def get_persona_manager() -> PersonaManager:
    global _manager
    if _manager is None:
        _manager = PersonaManager()
    return _manager
