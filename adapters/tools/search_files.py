"""Search Files Tool Adapter — 文件搜索（grep + find）。

对标 OpenClaw: grep (搜索文件内容) + find (按名称查找文件)。
超越维度: 安全沙箱 + 结果格式化 + 更简洁（单文件 vs OpenClaw 分散在多个模块）。
"""

import asyncio
import fnmatch
import functools
import os
from pathlib import Path
from typing import Any

from ports.tool_port import ToolPort
from logs import get_logger

logger = get_logger("tools")

_MAX_RESULTS = 50
_MAX_LINE_LEN = 200
_SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv", "data"}
_SKIP_EXTS = {".pyc", ".pyo", ".exe", ".dll", ".so", ".bin", ".jpg", ".png", ".gif", ".zip"}


class SearchFilesAdapter(ToolPort):
    """文件搜索工具：grep（内容搜索）+ find（文件查找）。"""

    def __init__(self, workspace: str | None = None):
        self.workspace = Path(workspace or os.getcwd()).resolve()
        logger.info(f"初始化: 工作区={self.workspace}")

    def list_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "grep",
                    "description": "在工作区文件中搜索包含指定文本的行。返回匹配的文件名、行号和内容。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "pattern": {
                                "type": "string",
                                "description": "要搜索的文本（大小写不敏感）",
                            },
                            "path": {
                                "type": "string",
                                "description": "搜索范围（相对路径，默认整个工作区）",
                            },
                        },
                        "required": ["pattern"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "find_files",
                    "description": "按文件名模式查找文件。支持通配符如 *.py、test_*。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "pattern": {
                                "type": "string",
                                "description": "文件名模式（支持 * 和 ? 通配符）",
                            },
                            "path": {
                                "type": "string",
                                "description": "搜索范围（相对路径，默认整个工作区）",
                            },
                        },
                        "required": ["pattern"],
                    },
                },
            },
        ]

    async def execute(self, tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
        if tool_name == "grep":
            return await self._grep(params.get("pattern", ""), params.get("path", "."))
        elif tool_name == "find_files":
            return await self._find(params.get("pattern", ""), params.get("path", "."))
        return {"success": False, "result": None, "error": f"未知工具: {tool_name}"}

    def _resolve_search_root(self, path: str) -> Path | None:
        try:
            resolved = (self.workspace / (path or ".")).resolve()
            if not str(resolved).startswith(str(self.workspace)):
                return None
            return resolved
        except (ValueError, OSError):
            return None

    async def _grep(self, pattern: str, path: str) -> dict[str, Any]:
        if not pattern.strip():
            return {"success": False, "result": None, "error": "搜索模式为空"}
        root = self._resolve_search_root(path)
        if not root:
            return {"success": False, "result": None, "error": "路径不安全"}
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, functools.partial(self._sync_grep, root, pattern))

    def _sync_grep(self, root: Path, pattern: str) -> dict[str, Any]:
        try:
            pattern_lower = pattern.lower()
            matches = []
            for dirpath, dirnames, filenames in os.walk(root):
                dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
                for fname in filenames:
                    if any(fname.endswith(ext) for ext in _SKIP_EXTS):
                        continue
                    fpath = Path(dirpath) / fname
                    try:
                        text = fpath.read_text(encoding="utf-8", errors="replace")
                        for i, line in enumerate(text.splitlines(), 1):
                            if pattern_lower in line.lower():
                                rel = fpath.relative_to(self.workspace)
                                display = line.strip()[:_MAX_LINE_LEN]
                                matches.append(f"{rel}:{i}: {display}")
                                if len(matches) >= _MAX_RESULTS:
                                    break
                    except (OSError, UnicodeDecodeError):
                        continue
                    if len(matches) >= _MAX_RESULTS:
                        break
                if len(matches) >= _MAX_RESULTS:
                    break

            if not matches:
                result = f"未找到包含 '{pattern}' 的内容"
            else:
                truncated = f"\n(结果已截断，最多显示 {_MAX_RESULTS} 条)" if len(matches) >= _MAX_RESULTS else ""
                result = "\n".join(matches) + truncated

            logger.info(f"grep 完成: pattern='{pattern}', 匹配={len(matches)}条")
            return {"success": True, "result": result, "error": None}
        except Exception as e:
            logger.error(f"grep 失败: {e}")
            return {"success": False, "result": None, "error": str(e)}

    async def _find(self, pattern: str, path: str) -> dict[str, Any]:
        if not pattern.strip():
            return {"success": False, "result": None, "error": "文件名模式为空"}
        root = self._resolve_search_root(path)
        if not root:
            return {"success": False, "result": None, "error": "路径不安全"}
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, functools.partial(self._sync_find, root, pattern))

    def _sync_find(self, root: Path, pattern: str) -> dict[str, Any]:
        try:
            matches = []
            for dirpath, dirnames, filenames in os.walk(root):
                dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
                for fname in filenames:
                    if fnmatch.fnmatch(fname.lower(), pattern.lower()):
                        fpath = Path(dirpath) / fname
                        rel = fpath.relative_to(self.workspace)
                        size = fpath.stat().st_size
                        matches.append(f"{rel} ({size} bytes)")
                        if len(matches) >= _MAX_RESULTS:
                            break
                if len(matches) >= _MAX_RESULTS:
                    break

            if not matches:
                result = f"未找到匹配 '{pattern}' 的文件"
            else:
                truncated = f"\n(结果已截断，最多 {_MAX_RESULTS} 条)" if len(matches) >= _MAX_RESULTS else ""
                result = "\n".join(matches) + truncated

            logger.info(f"find 完成: pattern='{pattern}', 匹配={len(matches)}个")
            return {"success": True, "result": result, "error": None}
        except Exception as e:
            logger.error(f"find 失败: {e}")
            return {"success": False, "result": None, "error": str(e)}
