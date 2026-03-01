"""File Watcher — 监控 data/memory/*.md 变更并自动重索引。

对标 OpenClaw chokidar 文件监听，使用 Python 标准库轮询实现（无外部依赖）。

工作方式:
1. 后台线程定期扫描 data/memory/*.md 的 mtime
2. 检测到变更时调用 markdown_store.index_to_store() 增量索引
3. 仅处理 .md 文件，忽略其他格式
"""

import threading
import time
from pathlib import Path
from typing import Any

from logs import get_logger

logger = get_logger("memory.file_watcher")

_MEMORY_DIR = Path(__file__).parent.parent / "data" / "memory"
_POLL_INTERVAL = 30  # 秒


class MemoryFileWatcher:
    """轮询式文件变更检测器。"""

    def __init__(self, memory_dir: Path | None = None,
                 poll_interval: float = _POLL_INTERVAL):
        self._dir = memory_dir or _MEMORY_DIR
        self._interval = poll_interval
        self._mtimes: dict[str, float] = {}
        self._store = None
        self._thread: threading.Thread | None = None
        self._running = False

    def start(self, store: Any) -> None:
        """启动后台监听线程。

        Args:
            store: MemoryStore 实例，用于 index_to_store()
        """
        if self._running:
            return
        self._store = store
        self._running = True
        # 初始化 mtime 快照
        self._snapshot()
        self._thread = threading.Thread(target=self._poll_loop, daemon=True,
                                         name="memory-file-watcher")
        self._thread.start()
        logger.info(f"文件监听启动: {self._dir} (间隔 {self._interval}s)")

    def stop(self) -> None:
        """停止监听。"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None
        logger.info("文件监听已停止")

    def _snapshot(self) -> None:
        """记录当前所有 .md 文件的 mtime。"""
        self._mtimes.clear()
        if not self._dir.exists():
            return
        for f in self._dir.glob("*.md"):
            try:
                self._mtimes[str(f)] = f.stat().st_mtime
            except OSError:
                pass

    def _poll_loop(self) -> None:
        """后台轮询主循环。"""
        while self._running:
            time.sleep(self._interval)
            if not self._running:
                break
            try:
                self._check_changes()
            except Exception as e:
                logger.debug(f"文件监听异常: {e}")

    def _check_changes(self) -> None:
        """检查文件变更并触发重索引。"""
        if not self._dir.exists():
            return

        current: dict[str, float] = {}
        for f in self._dir.glob("*.md"):
            try:
                current[str(f)] = f.stat().st_mtime
            except OSError:
                pass

        # 检测新增或修改的文件
        changed = []
        for path, mtime in current.items():
            old_mtime = self._mtimes.get(path)
            if old_mtime is None or mtime > old_mtime:
                changed.append(Path(path).name)

        # 检测删除的文件
        deleted = set(self._mtimes.keys()) - set(current.keys())

        self._mtimes = current

        if not changed and not deleted:
            return

        if changed:
            logger.info(f"检测到 {len(changed)} 个 .md 文件变更: {', '.join(changed[:5])}")
        if deleted:
            logger.info(f"检测到 {len(deleted)} 个 .md 文件删除")

        # 触发增量重索引
        if self._store and changed:
            try:
                from memory.markdown_store import get_markdown_store
                md_store = get_markdown_store()
                result = md_store.index_to_store(self._store)
                if result.get("indexed", 0) > 0:
                    logger.info(f"文件变更重索引: {result}")
            except Exception as e:
                logger.warning(f"文件变更重索引失败: {e}")


# 全局单例
_watcher: MemoryFileWatcher | None = None


def get_file_watcher() -> MemoryFileWatcher:
    global _watcher
    if _watcher is None:
        _watcher = MemoryFileWatcher()
    return _watcher
