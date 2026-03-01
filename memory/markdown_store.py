"""Markdown Memory Store — 对标 OpenClaw Markdown 文件记忆系统。

OpenClaw 以 Markdown 文件为 source of truth:
  - memory/YYYY-MM-DD.md — 每日记忆
  - memory/MEMORY.md — 常青记忆

本模块让 LucidMind 也能:
  1. 读写 data/memory/*.md 文件
  2. 跨文件全文搜索
  3. 将 Markdown 内容索引到 SQLite MemoryStore（双向同步）
  4. 用户可直接编辑 Markdown 文件
"""

import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from logs import get_logger

logger = get_logger("memory.markdown")

_MEMORY_DIR = Path(__file__).parent.parent / "data" / "memory"


class MarkdownMemoryStore:
    """Markdown 文件记忆管理器。"""

    def __init__(self, memory_dir: Path | None = None):
        self.memory_dir = memory_dir or _MEMORY_DIR
        self.memory_dir.mkdir(parents=True, exist_ok=True)

    # ── 文件操作 ──

    def list_files(self) -> list[dict[str, Any]]:
        """列出所有记忆 Markdown 文件。"""
        files = []
        for p in sorted(self.memory_dir.glob("*.md"), reverse=True):
            stat = p.stat()
            files.append({
                "name": p.name,
                "path": str(p),
                "size": stat.st_size,
                "modified_at": datetime.fromtimestamp(
                    stat.st_mtime, tz=timezone.utc
                ).isoformat(),
                "is_evergreen": not re.match(r"\d{4}-\d{2}-\d{2}\.md$", p.name),
            })
        return files

    def read_file(self, filename: str) -> str | None:
        """读取一个记忆文件内容。"""
        path = self._safe_path(filename)
        if not path or not path.exists():
            return None
        return path.read_text(encoding="utf-8")

    def write_file(self, filename: str, content: str) -> bool:
        """写入/覆盖一个记忆文件。"""
        path = self._safe_path(filename)
        if not path:
            return False
        path.write_text(content, encoding="utf-8")
        logger.info(f"记忆文件写入: {filename} ({len(content)} 字)")
        return True

    def append_entry(self, filename: str, entry: str,
                     heading: str | None = None) -> bool:
        """向记忆文件追加条目（带去重）。"""
        path = self._safe_path(filename)
        if not path:
            return False
        existing = ""
        if path.exists():
            existing = path.read_text(encoding="utf-8")
            # 去重: 前50字符已存在则跳过
            if entry[:50] in existing:
                logger.debug(f"跳过重复条目: {filename}")
                return False

        if not existing:
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            existing = f"# {today} 记忆日志\n"

        if heading:
            existing += f"\n## {heading}\n"
        existing += entry + "\n"
        path.write_text(existing, encoding="utf-8")
        return True

    def delete_file(self, filename: str) -> bool:
        """删除一个记忆文件。"""
        path = self._safe_path(filename)
        if not path or not path.exists():
            return False
        path.unlink()
        logger.info(f"记忆文件删除: {filename}")
        return True

    def ensure_evergreen(self) -> Path:
        """确保 MEMORY.md 常青记忆文件存在。"""
        path = self.memory_dir / "MEMORY.md"
        if not path.exists():
            path.write_text(
                "# 常青记忆\n\n"
                "> 此文件存储重要的持久信息，不受时间衰减影响。\n"
                "> 你可以直接编辑此文件来管理长期记忆。\n\n",
                encoding="utf-8"
            )
            logger.info("创建 MEMORY.md 常青记忆文件")
        return path

    # ── 搜索 ──

    def search(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        """跨文件全文搜索 Markdown 记忆。

        返回匹配的片段，按相关性排序。
        """
        if not query or not query.strip():
            return []

        keywords = [k.lower() for k in query.split() if k.strip()]
        results: list[dict[str, Any]] = []

        for md_file in self.memory_dir.glob("*.md"):
            try:
                content = md_file.read_text(encoding="utf-8")
            except Exception:
                continue

            # 按段落分割（## 标题或空行分隔）
            sections = re.split(r"\n##\s+", content)
            for i, section in enumerate(sections):
                section = section.strip()
                if not section:
                    continue
                section_lower = section.lower()
                # 计算匹配度
                hits = sum(1 for k in keywords if k in section_lower)
                if hits == 0:
                    continue
                score = hits / len(keywords)

                # 提取标题
                lines = section.split("\n")
                title = lines[0].strip("#").strip() if lines else ""
                snippet = "\n".join(lines[:5])[:300]

                results.append({
                    "file": md_file.name,
                    "title": title,
                    "snippet": snippet,
                    "score": score,
                    "is_evergreen": not re.match(
                        r"\d{4}-\d{2}-\d{2}\.md$", md_file.name
                    ),
                })

        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:limit]

    # ── 索引到 SQLite ──

    def index_to_store(self, store) -> dict[str, int]:
        """将所有 Markdown 文件索引到 MemoryStore。

        用于启动时或文件变更后重建索引。
        返回 {"indexed": N, "skipped": M}。
        """
        indexed = 0
        skipped = 0

        for md_file in self.memory_dir.glob("*.md"):
            try:
                content = md_file.read_text(encoding="utf-8")
            except Exception:
                skipped += 1
                continue

            is_evergreen = not re.match(
                r"\d{4}-\d{2}-\d{2}\.md$", md_file.name
            )
            collection = "facts" if is_evergreen else "sessions"

            # 按段落分块索引
            sections = re.split(r"\n##\s+", content)
            for section in sections:
                section = section.strip()
                if not section or len(section) < 10:
                    continue
                # 截断过长的段落
                chunk = section[:1000]

                # 检查是否已存在（基于内容前50字符）
                existing = store.search_text(chunk[:50], collection=collection, limit=1)
                if existing and existing[0].content[:50] == chunk[:50]:
                    skipped += 1
                    continue

                metadata = {
                    "source": f"markdown:{md_file.name}",
                    "is_evergreen": is_evergreen,
                }
                store.add(
                    collection=collection,
                    content=chunk,
                    metadata=metadata,
                    skip_noise_filter=True,
                )
                indexed += 1

        logger.info(f"Markdown 索引完成: indexed={indexed}, skipped={skipped}")
        return {"indexed": indexed, "skipped": skipped}

    # ── 内部 ──

    def _safe_path(self, filename: str) -> Path | None:
        """验证文件名安全性（防止路径遍历）。"""
        if not filename:
            return None
        # 只允许 .md 文件名，不允许路径分隔符
        clean = Path(filename).name
        if not clean.endswith(".md"):
            clean += ".md"
        if ".." in clean or "/" in filename or "\\" in filename:
            logger.warning(f"不安全的文件名: {filename}")
            return None
        return self.memory_dir / clean


# 全局单例
_instance: MarkdownMemoryStore | None = None


def get_markdown_store() -> MarkdownMemoryStore:
    global _instance
    if _instance is None:
        _instance = MarkdownMemoryStore()
    return _instance
