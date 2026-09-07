"""Core Memory Block — 高频记忆直注（对标 Letta memory blocks）。

将高频记忆（高 helpful_count、用户偏好、关键事实）提取为固定 Block，
直接注入 prompt 顶部，跳过搜索管线，零延迟。

Block 更新频率低（每 N 次会话刷新一次），极度节省 token。
"""

from datetime import datetime, timezone
from memory.store import MemoryStore
from memory.types import MemoryResult
from logs import get_logger

logger = get_logger("memory.block_inject")

# 核心 Block 刷新间隔（秒）
_BLOCK_REFRESH_INTERVAL = 300  # 5 分钟


class CoreMemoryBlock:
    """高频记忆 Block 管理器。

    从 MemoryStore 中提取 helpful_count 最高的记忆，
    格式化为固定文本 Block 注入 system prompt。
    """

    def __init__(self, store: MemoryStore, max_items: int = 5):
        self._store = store
        self._max_items = max_items
        self._cached_block: str = ""
        self._cached_items: list[MemoryResult] = []
        self._last_refresh: float = 0.0

    def get_block(self) -> str:
        """获取核心记忆 Block 文本（带缓存）。

        Returns:
            格式化的核心记忆文本，为空时返回空字符串
        """
        now = datetime.now(timezone.utc).timestamp()
        if self._cached_block and (now - self._last_refresh) < _BLOCK_REFRESH_INTERVAL:
            return self._cached_block

        self._refresh()
        return self._cached_block

    def get_items(self) -> list[MemoryResult]:
        """获取核心记忆条目列表（带缓存）。"""
        now = datetime.now(timezone.utc).timestamp()
        if self._cached_items and (now - self._last_refresh) < _BLOCK_REFRESH_INTERVAL:
            return self._cached_items

        self._refresh()
        return self._cached_items

    def _refresh(self) -> None:
        """从 MemoryStore 刷新核心记忆。

        选择策略:
        1. helpful_count >= 2 的条目（被多次验证有用）
        2. 用户偏好类条目（category=user_pref）
        3. 按 helpful_count 降序排列
        """
        try:
            all_memories = self._store.get_all(limit=500)
        except Exception as e:
            logger.warning(f"核心记忆刷新失败: {e}")
            return

        # 筛选高价值记忆
        candidates = []
        for mem in all_memories:
            meta = mem.metadata or {}
            helpful = meta.get("helpful_count", 0)
            harmful = meta.get("harmful_count", 0)
            category = meta.get("category", "")
            net_score = helpful - harmful

            # 条件: helpful >= 2 OR 用户偏好类
            if helpful >= 2 or category == "user_pref":
                candidates.append((mem, net_score, category))

        # 排序: 用户偏好优先，然后按净分降序
        candidates.sort(key=lambda x: (
            1 if x[2] == "user_pref" else 0,
            x[1],
        ), reverse=True)

        self._cached_items = [c[0] for c in candidates[:self._max_items]]

        # 格式化为 Block 文本
        if self._cached_items:
            lines = []
            for item in self._cached_items:
                meta = item.metadata or {}
                category = meta.get("category", "")
                prefix = "⭐" if category == "user_pref" else "📌"
                content = item.content.strip()
                if len(content) > 150:
                    content = content[:147] + "..."
                lines.append(f"- {prefix} {content}")
            self._cached_block = "\n".join(lines)
        else:
            self._cached_block = ""

        self._last_refresh = datetime.now(timezone.utc).timestamp()
        if self._cached_items:
            logger.debug(f"核心记忆 Block 刷新: {len(self._cached_items)} 条")

    def invalidate(self) -> None:
        """强制失效缓存（新记忆写入后调用）。"""
        self._last_refresh = 0.0
        self._cached_block = ""
        self._cached_items = []
