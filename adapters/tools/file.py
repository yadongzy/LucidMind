"""File Tool Adapter — 文件读写操作。

对标 OpenAkita file.py (311行)。
我们的优势: 路径沙箱 + 原子写入 + 无额外依赖 + 更简洁。
"""

import asyncio
import functools
import os
import tempfile
from pathlib import Path
from typing import Any

from ports.tool_port import ToolPort
from logs import get_logger

logger = get_logger("tools")

# 读取文件大小上限（防止 LLM 要求读取超大文件撑爆内存）
_MAX_READ_SIZE = 200 * 1024  # 200 KB

# 写入文件大小上限
_MAX_WRITE_SIZE = 100 * 1024  # 100 KB

# 禁止操作的路径模式（安全）
_BLOCKED_PATHS = [
    ".env", ".git", "__pycache__", "node_modules",
    ".rules", "identity",
]


class FileAdapter(ToolPort):
    """文件工具适配器。在指定工作区内安全地读写文件。"""

    def __init__(self, workspace: str | None = None):
        self.workspace = Path(workspace or os.getcwd()).resolve()
        logger.info(f"初始化: 工作区={self.workspace}")

    def list_tools(self) -> list[dict[str, Any]]:
        """返回 LLM 可用的文件工具定义。"""
        return [
            {
                "type": "function",
                "function": {
                    "name": "read_file",
                    "description": "读取指定路径的文件内容。路径相对于工作区。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {
                                "type": "string",
                                "description": "文件路径（相对于工作区）",
                            },
                        },
                        "required": ["path"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "write_file",
                    "description": "将内容写入指定路径的文件。路径相对于工作区。会自动创建目录。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {
                                "type": "string",
                                "description": "文件路径（相对于工作区）",
                            },
                            "content": {
                                "type": "string",
                                "description": "要写入的内容",
                            },
                        },
                        "required": ["path", "content"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "list_directory",
                    "description": "列出目录中的文件和子目录。路径相对于工作区。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {
                                "type": "string",
                                "description": "目录路径（相对于工作区），默认为根目录",
                            },
                        },
                        "required": [],
                    },
                },
            },
        ]

    async def execute(self, tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
        """执行文件工具。"""
        if tool_name == "read_file":
            return await self._read_file(params.get("path", ""))
        elif tool_name == "write_file":
            return await self._write_file(params.get("path", ""), params.get("content", ""))
        elif tool_name == "list_directory":
            return await self._list_directory(params.get("path", "."))
        return {"success": False, "result": None, "error": f"未知工具: {tool_name}"}

    def _safe_resolve(self, path: str) -> Path | None:
        """安全解析路径，防止路径遍历攻击。返回 None 表示路径不安全。"""
        try:
            resolved = (self.workspace / path).resolve()
            # 确保路径在工作区内
            if not str(resolved).startswith(str(self.workspace)):
                logger.warning(f"路径遍历拦截: {path} → {resolved}")
                return None
            # 检查是否包含禁止路径
            rel = str(resolved.relative_to(self.workspace))
            for blocked in _BLOCKED_PATHS:
                if blocked in rel.split(os.sep):
                    logger.warning(f"禁止路径拦截: {path} 包含 {blocked}")
                    return None
            return resolved
        except (ValueError, OSError) as e:
            logger.warning(f"路径解析失败: {path}, {e}")
            return None

    async def _read_file(self, path: str) -> dict[str, Any]:
        """读取文件。"""
        if not path.strip():
            return {"success": False, "result": None, "error": "路径为空"}

        resolved = self._safe_resolve(path)
        if not resolved:
            return {"success": False, "result": None, "error": "路径不安全或被禁止"}

        logger.info(f"读取文件: {resolved}")

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, functools.partial(self._sync_read, resolved))

    def _sync_read(self, resolved: Path) -> dict[str, Any]:
        """同步读取文件（在线程池中调用）。"""
        try:
            if not resolved.exists():
                return {"success": False, "result": None, "error": f"文件不存在: {resolved.name}"}
            if not resolved.is_file():
                return {"success": False, "result": None, "error": f"不是文件: {resolved.name}"}

            size = resolved.stat().st_size
            if size > _MAX_READ_SIZE:
                return {
                    "success": False,
                    "result": None,
                    "error": f"文件过大: {size / 1024:.1f}KB (上限 {_MAX_READ_SIZE // 1024}KB)",
                }

            content = resolved.read_text(encoding="utf-8")
            logger.info(f"读取完成: {resolved.name}, {len(content)}字")
            return {"success": True, "result": content, "error": None}

        except UnicodeDecodeError:
            return {"success": False, "result": None, "error": "文件不是 UTF-8 文本"}
        except Exception as e:
            logger.error(f"读取失败: {type(e).__name__}: {e}")
            return {"success": False, "result": None, "error": str(e)}

    async def _write_file(self, path: str, content: str) -> dict[str, Any]:
        """写入文件（原子写入）。"""
        if not path.strip():
            return {"success": False, "result": None, "error": "路径为空"}
        if not content:
            return {"success": False, "result": None, "error": "内容为空"}

        if len(content.encode("utf-8")) > _MAX_WRITE_SIZE:
            return {
                "success": False,
                "result": None,
                "error": f"内容过大 (上限 {_MAX_WRITE_SIZE // 1024}KB)",
            }

        resolved = self._safe_resolve(path)
        if not resolved:
            return {"success": False, "result": None, "error": "路径不安全或被禁止"}

        logger.info(f"写入文件: {resolved}, {len(content)}字")

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, functools.partial(self._sync_write, resolved, content)
        )

    def _sync_write(self, resolved: Path, content: str) -> dict[str, Any]:
        """同步原子写入文件（在线程池中调用）。"""
        try:
            # 确保目录存在
            resolved.parent.mkdir(parents=True, exist_ok=True)

            # 原子写入：先写临时文件，再重命名
            fd, tmp_path = tempfile.mkstemp(
                dir=resolved.parent, suffix=".tmp", prefix=".lucid_"
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    f.write(content)
                # 重命名（原子操作）
                os.replace(tmp_path, resolved)
            except Exception:
                # 清理临时文件
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
                raise

            logger.info(f"写入完成: {resolved.name}, {len(content)}字")
            return {
                "success": True,
                "result": f"文件已写入: {resolved.name} ({len(content)}字)",
                "error": None,
            }

        except Exception as e:
            logger.error(f"写入失败: {type(e).__name__}: {e}")
            return {"success": False, "result": None, "error": str(e)}

    async def _list_directory(self, path: str) -> dict[str, Any]:
        """列出目录内容。"""
        resolved = self._safe_resolve(path or ".")
        if not resolved:
            return {"success": False, "result": None, "error": "路径不安全或被禁止"}

        logger.info(f"列出目录: {resolved}")

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, functools.partial(self._sync_list, resolved)
        )

    def _sync_list(self, resolved: Path) -> dict[str, Any]:
        """同步列出目录（在线程池中调用）。"""
        try:
            if not resolved.exists():
                return {"success": False, "result": None, "error": f"目录不存在: {resolved.name}"}
            if not resolved.is_dir():
                return {"success": False, "result": None, "error": f"不是目录: {resolved.name}"}

            entries = []
            for item in sorted(resolved.iterdir()):
                name = item.name
                # 跳过隐藏文件和被禁止的目录
                if name.startswith(".") or name in ("__pycache__", "node_modules"):
                    continue
                if item.is_dir():
                    entries.append(f"[DIR]  {name}/")
                else:
                    size = item.stat().st_size
                    entries.append(f"[FILE] {name} ({size} bytes)")

            result = "\n".join(entries) if entries else "(空目录)"
            logger.info(f"列出完成: {resolved.name}, {len(entries)}项")
            return {"success": True, "result": result, "error": None}

        except Exception as e:
            logger.error(f"列目录失败: {type(e).__name__}: {e}")
            return {"success": False, "result": None, "error": str(e)}
