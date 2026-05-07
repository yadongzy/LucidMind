"""Memory Types — 记忆系统数据类型定义。"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class MemoryResult:
    """单条记忆检索结果。"""
    id: str
    collection: str
    content: str
    score: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""
    source_type: str = ""      # markdown | session | lesson | profile | tool | user_confirmed
    source_path: str = ""      # 来源文件路径
    confidence: str = ""       # confirmed | inferred | user_confirmed | stale

    def to_dict(self) -> dict:
        d = {
            "id": self.id,
            "collection": self.collection,
            "content": self.content,
            "score": self.score,
            "metadata": self.metadata,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
        if self.source_type:
            d["source_type"] = self.source_type
        if self.source_path:
            d["source_path"] = self.source_path
        if self.confidence:
            d["confidence"] = self.confidence
        return d


@dataclass
class MemoryConfig:
    """记忆系统配置 — 支持从 data/memory_config.json 加载。"""
    enabled: bool = True
    embedding_provider: str = "ollama"        # "ollama" | "openai" | "local"
    embedding_model: str = "nomic-embed-text"
    embedding_dim: int = 768

    # 检索配置
    max_results: int = 6
    min_score: float = 0.35
    hybrid_enabled: bool = True
    vector_weight: float = 0.7
    text_weight: float = 0.3

    # Chunking 配置
    chunk_tokens: int = 400
    chunk_overlap: int = 80

    # 同步配置
    sync_on_session_start: bool = True
    sync_on_search: bool = True
    sync_delta_messages: int = 50

    # 缓存配置
    cache_enabled: bool = True
    cache_max_entries: int = 100

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items()}

    @classmethod
    def from_dict(cls, d: dict) -> "MemoryConfig":
        cfg = cls()
        for k, v in d.items():
            if hasattr(cfg, k):
                expected_type = type(getattr(cfg, k))
                try:
                    setattr(cfg, k, expected_type(v))
                except (ValueError, TypeError):
                    pass
        # Clamp values
        cfg.min_score = max(0.0, min(1.0, cfg.min_score))
        cfg.vector_weight = max(0.0, min(1.0, cfg.vector_weight))
        cfg.text_weight = max(0.0, min(1.0, cfg.text_weight))
        cfg.chunk_tokens = max(50, cfg.chunk_tokens)
        cfg.chunk_overlap = max(0, min(cfg.chunk_tokens - 1, cfg.chunk_overlap))
        cfg.max_results = max(1, min(50, cfg.max_results))
        cfg.cache_max_entries = max(1, cfg.cache_max_entries)
        # Normalize weights
        total = cfg.vector_weight + cfg.text_weight
        if total > 0:
            cfg.vector_weight /= total
            cfg.text_weight /= total
        else:
            cfg.vector_weight = 0.7
            cfg.text_weight = 0.3
        return cfg


# 默认集合定义
COLLECTIONS = {
    "lessons": "从对话中学到的经验和模式",
    "facts": "用户偏好、项目事实等持久知识",
    "sessions": "历史会话摘要（自动生成）",
    "skills": "技能使用经验和最佳实践",
}
