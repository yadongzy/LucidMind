"""身份管理技能 — 允许大脑读取和演化自己的身份文件。

安全规则：
- CORE.md 只读，不可修改
- SOUL.md 可读写（大脑自我演化）
- USER.md 可读写（学习用户信息）
- BOOTSTRAP.md 可读写（完成引导后标记）
"""

from pathlib import Path
from datetime import datetime
from typing import Any

from ports.tool_port import ToolPort
from logs import get_logger

logger = get_logger("skills.identity")

_IDENTITY_DIR = Path(__file__).parent.parent.parent / "identity"
_ALLOWED_FILES = {"SOUL.md", "USER.md", "BOOTSTRAP.md"}
_READONLY_FILES = {"CORE.md"}


class IdentityAdapter(ToolPort):
    """身份文件读写工具。"""

    def list_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "identity_read",
                    "description": "读取身份文件内容。可读取: CORE.md(不可变铁律), SOUL.md(个性), USER.md(用户画像), BOOTSTRAP.md(引导)",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "file": {
                                "type": "string",
                                "description": "文件名: CORE.md / SOUL.md / USER.md / BOOTSTRAP.md",
                                "enum": ["CORE.md", "SOUL.md", "USER.md", "BOOTSTRAP.md"],
                            },
                        },
                        "required": ["file"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "identity_update",
                    "description": "更新身份文件。CORE.md不可修改。SOUL.md用于演化自己的个性，USER.md用于记录用户信息，BOOTSTRAP.md用于标记引导完成。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "file": {
                                "type": "string",
                                "description": "要更新的文件: SOUL.md / USER.md / BOOTSTRAP.md",
                                "enum": ["SOUL.md", "USER.md", "BOOTSTRAP.md"],
                            },
                            "content": {
                                "type": "string",
                                "description": "新的文件完整内容",
                            },
                            "reason": {
                                "type": "string",
                                "description": "修改原因（会记录在日志中）",
                            },
                        },
                        "required": ["file", "content", "reason"],
                    },
                },
            },
        ]

    async def execute(self, name: str, args: dict, **kwargs) -> dict:
        if name == "identity_read":
            result = self._read(args.get("file", ""))
            ok = not result.startswith("❌")
            return {"success": ok, "result": result, "error": None if ok else result}
        elif name == "identity_update":
            result = self._update(args.get("file", ""), args.get("content", ""), args.get("reason", ""))
            ok = result.startswith("✅")
            return {"success": ok, "result": result, "error": None if ok else result}
        return {"success": False, "result": None, "error": f"未知工具: {name}"}

    def _read(self, filename: str) -> str:
        all_files = _ALLOWED_FILES | _READONLY_FILES
        if filename not in all_files:
            return f"❌ 不支持的文件: {filename}。可选: {', '.join(sorted(all_files))}"
        path = _IDENTITY_DIR / filename
        if not path.exists():
            return f"文件不存在: {filename}"
        try:
            content = path.read_text(encoding="utf-8")
            return f"=== {filename} ===\n{content}"
        except Exception as e:
            return f"读取失败: {e}"

    def _update(self, filename: str, content: str, reason: str) -> str:
        if filename in _READONLY_FILES:
            return f"❌ {filename} 是不可变文件，禁止修改。安全铁律不可更改。"
        if filename not in _ALLOWED_FILES:
            return f"❌ 不支持的文件: {filename}。可写: {', '.join(sorted(_ALLOWED_FILES))}"
        if not content.strip():
            return "❌ 内容不能为空"
        path = _IDENTITY_DIR / filename
        try:
            # 备份旧文件
            if path.exists():
                old = path.read_text(encoding="utf-8")
                backup = _IDENTITY_DIR / f".{filename}.bak"
                backup.write_text(old, encoding="utf-8")
            path.write_text(content, encoding="utf-8")
            logger.info(f"✏️ 身份文件更新: {filename} — {reason}")
            return f"✅ {filename} 已更新。原因: {reason}"
        except Exception as e:
            return f"❌ 写入失败: {e}"
