"""JSON Memory Adapter — JSON 文件持久化记忆。

对标 OpenAkita core/memory.py (348行)。
我们的优势: 纯 JSON + MemoryPort 接口 + 无 DB 依赖 + 原子写入。
"""

import asyncio
import functools
import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any

from ports.memory_port import MemoryPort
from logs import get_logger

logger = get_logger("memory")

# 会话历史上限（条数）
_MAX_SESSION_MESSAGES = 100

# 长期记忆上限（条数）
_MAX_MEMORIES = 200


class JSONMemoryAdapter(MemoryPort):
    """JSON 文件记忆适配器。会话历史和长期记忆分开存储。"""

    def __init__(self, data_dir: str | None = None):
        self.data_dir = Path(data_dir or os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data"))
        self.sessions_dir = self.data_dir / "sessions"
        self.memories_file = self.data_dir / "memories.json"

        # 确保目录存在
        self.sessions_dir.mkdir(parents=True, exist_ok=True)

        # 加载长期记忆到内存
        self._memories: list[dict[str, Any]] = self._load_memories()

        logger.info(f"初始化: data_dir={self.data_dir}, 已有记忆={len(self._memories)}条")

    # === MemoryPort 接口实现 ===

    async def save(self, key: str, value: Any, category: str = "general") -> None:
        """保存一条长期记忆。"""
        entry = {
            "key": key,
            "value": value,
            "category": category,
            "timestamp": time.time(),
        }
        self._memories.append(entry)

        # 超限时删除最旧的
        if len(self._memories) > _MAX_MEMORIES:
            self._memories = self._memories[-_MAX_MEMORIES:]

        await self._persist_memories()
        logger.info(f"保存记忆: key={key}, category={category}")

    async def recall(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        """混合检索记忆：BM25 + 时间衰减 + MMR 去重 + Markdown 文件搜索。"""
        from adapters.memory.retrieval import hybrid_search
        results = hybrid_search(
            query=query,
            items=self._memories,
            text_fields=["key", "value", "category"],
            limit=limit,
            time_field="timestamp",
            half_life_days=30.0,
            mmr_lambda=0.7,
        )
        # 清理内部评分字段
        cleaned = [{k: v for k, v in r.items() if not k.startswith("_")} for r in results]

        # GAP-3: 同时搜索 Markdown 记忆文件
        try:
            from memory.markdown_store import get_markdown_store
            md_store = get_markdown_store()
            md_results = md_store.search(query, limit=limit)
            for mr in md_results:
                if mr["score"] >= 0.3:
                    cleaned.append({
                        "key": mr.get("title", ""),
                        "value": mr.get("snippet", ""),
                        "category": "memory_file",
                        "source": mr.get("file", ""),
                        "timestamp": time.time(),
                    })
        except Exception as e:
            logger.debug(f"Markdown 记忆搜索失败(降级): {e}")

        # 截断到 limit
        cleaned = cleaned[:limit]
        logger.info(f"检索记忆: query='{query}', 命中={len(cleaned)}")
        return cleaned

    async def get_context(self, session_id: str) -> list[dict[str, Any]]:
        """加载指定会话的对话历史。"""
        session_file = self.sessions_dir / f"{session_id}.json"
        if not session_file.exists():
            logger.info(f"会话不存在: {session_id}")
            return []

        loop = asyncio.get_event_loop()
        messages = await loop.run_in_executor(
            None, functools.partial(self._sync_load_session, session_file)
        )
        logger.info(f"加载会话: {session_id}, {len(messages)}条消息")
        return messages

    async def save_message(self, session_id: str, message: dict[str, Any]) -> None:
        """追加一条消息到会话历史。"""
        session_file = self.sessions_dir / f"{session_id}.json"

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None, functools.partial(self._sync_save_message, session_file, message)
        )

    # === 内部方法 ===

    def _load_memories(self) -> list[dict[str, Any]]:
        """加载长期记忆文件。"""
        if not self.memories_file.exists():
            return []
        try:
            data = json.loads(self.memories_file.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except (json.JSONDecodeError, OSError) as e:
            logger.error(f"加载记忆失败: {e}")
            return []

    async def _persist_memories(self) -> None:
        """原子写入长期记忆文件。"""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._sync_persist_memories)

    def _sync_persist_memories(self) -> None:
        """同步原子写入 + 写入前校验 + 备份。"""
        tmp = None
        try:
            # 校验：确保数据是有效列表
            if not isinstance(self._memories, list):
                logger.error("记忆校验失败: 数据不是列表，拒绝写入")
                return
            # 备份：写入前保留上一版本
            if self.memories_file.exists():
                bak = self.memories_file.with_suffix(".bak")
                try:
                    import shutil
                    shutil.copy2(self.memories_file, bak)
                except OSError as e:
                    logger.warning(f"备份失败（继续写入）: {e}")
            # 原子写入
            fd, tmp = tempfile.mkstemp(dir=self.data_dir, suffix=".tmp", prefix=".mem_")
            content = json.dumps(self._memories, ensure_ascii=False, indent=2)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(content)
            # 写后校验：确认 JSON 可解析
            json.loads(content)
            os.replace(tmp, self.memories_file)
            tmp = None
        except Exception as e:
            logger.error(f"持久化记忆失败: {e}")
        finally:
            if tmp and os.path.exists(tmp):
                os.unlink(tmp)

    def _sync_load_session(self, session_file: Path) -> list[dict[str, Any]]:
        """同步加载会话文件。"""
        try:
            data = json.loads(session_file.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except (json.JSONDecodeError, OSError) as e:
            logger.error(f"加载会话失败: {e}")
            return []

    def _sync_save_message(self, session_file: Path, message: dict[str, Any]) -> None:
        """同步追加消息并原子写入 + 备份。"""
        tmp = None
        try:
            messages = []
            if session_file.exists():
                try:
                    messages = json.loads(session_file.read_text(encoding="utf-8"))
                    if not isinstance(messages, list):
                        messages = []
                except (json.JSONDecodeError, OSError):
                    messages = []

            if "timestamp" not in message:
                message["timestamp"] = time.time()
            messages.append(message)
            if len(messages) > _MAX_SESSION_MESSAGES:
                messages = messages[-_MAX_SESSION_MESSAGES:]

            # 备份
            if session_file.exists():
                try:
                    import shutil
                    shutil.copy2(session_file, session_file.with_suffix(".bak"))
                except OSError:
                    pass

            fd, tmp = tempfile.mkstemp(dir=self.sessions_dir, suffix=".tmp", prefix=".sess_")
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(messages, f, ensure_ascii=False, indent=2)
            os.replace(tmp, session_file)
            tmp = None
        except Exception as e:
            logger.error(f"保存消息失败: {e}")
