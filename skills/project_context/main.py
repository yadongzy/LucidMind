"""项目上下文技能 — 扫描项目结构，给大脑提供代码库上下文。

用途：大脑需要了解当前项目的文件结构、技术栈、关键文件时调用。
"""

import os
from pathlib import Path
from typing import Any

from ports.tool_port import ToolPort


class ProjectContextAdapter(ToolPort):
    """扫描项目目录，返回结构化的项目上下文。"""

    _SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__",
                  ".egg-info", "dist", "build", ".mypy_cache", ".pytest_cache"}
    _KEY_FILES = {"README.md", "requirements.txt", "package.json", "pyproject.toml",
                  "Makefile", "Dockerfile", "docker-compose.yml", ".env.example",
                  "SOUL.md", "user_profile.md"}

    def list_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "scan_project",
                    "description": "扫描项目目录结构，返回文件树、技术栈、关键文件摘要",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string", "description": "项目根目录路径（默认当前目录）"},
                            "max_depth": {"type": "integer", "description": "最大扫描深度（默认3）"},
                        },
                        "required": [],
                    },
                },
            }
        ]

    async def execute(self, tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
        root = Path(params.get("path", os.getcwd()))
        max_depth = params.get("max_depth", 3)

        if not root.exists():
            return {"success": False, "error": f"路径不存在: {root}"}

        tree_lines = []
        file_count = {"py": 0, "js": 0, "ts": 0, "md": 0, "json": 0, "other": 0}
        total_size = 0
        key_files_found = []

        def _scan(p: Path, depth: int, prefix: str = ""):
            nonlocal total_size
            if depth > max_depth:
                return
            try:
                entries = sorted(p.iterdir(), key=lambda x: (x.is_file(), x.name))
            except PermissionError:
                return

            dirs = [e for e in entries if e.is_dir() and e.name not in self._SKIP_DIRS and not e.name.startswith(".")]
            files = [e for e in entries if e.is_file() and not e.name.startswith(".")]

            for d in dirs:
                child_count = sum(1 for _ in d.rglob("*") if _.is_file()) if depth < max_depth else 0
                tree_lines.append(f"{prefix}📂 {d.name}/ ({child_count} files)")
                _scan(d, depth + 1, prefix + "  ")

            for f in files[:20]:  # 每层最多显示20个文件
                size = f.stat().st_size
                total_size += size
                ext = f.suffix.lstrip(".")
                if ext in file_count:
                    file_count[ext] += 1
                else:
                    file_count["other"] += 1
                if f.name in self._KEY_FILES:
                    key_files_found.append(str(f.relative_to(root)))
                if depth <= 1:
                    size_str = f"{size / 1024:.0f}KB" if size > 1024 else f"{size}B"
                    tree_lines.append(f"{prefix}  {f.name} ({size_str})")

            if len(files) > 20:
                tree_lines.append(f"{prefix}  ... +{len(files) - 20} more files")

        _scan(root, 0)

        # 技术栈推断
        stack = []
        if file_count["py"] > 0:
            stack.append(f"Python ({file_count['py']} files)")
        if file_count["js"] > 0:
            stack.append(f"JavaScript ({file_count['js']} files)")
        if file_count["ts"] > 0:
            stack.append(f"TypeScript ({file_count['ts']} files)")
        if (root / "requirements.txt").exists():
            stack.append("pip")
        if (root / "package.json").exists():
            stack.append("npm")
        if (root / "Dockerfile").exists():
            stack.append("Docker")

        result = []
        result.append(f"📁 项目: {root.name}")
        result.append(f"📊 大小: {total_size / 1024 / 1024:.1f}MB")
        result.append(f"🔧 技术栈: {', '.join(stack) if stack else '未知'}")
        if key_files_found:
            result.append(f"📌 关键文件: {', '.join(key_files_found)}")
        result.append("\n📂 目录结构:")
        result.extend(tree_lines[:50])
        if len(tree_lines) > 50:
            result.append(f"... 共 {len(tree_lines)} 项")

        return {"success": True, "result": "\n".join(result)}
