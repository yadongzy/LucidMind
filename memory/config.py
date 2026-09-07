"""Memory Config — 记忆系统配置加载/保存（对标 OpenClaw memory-search.ts 28个参数）。"""

import json
from pathlib import Path

from memory.types import MemoryConfig
from logs import get_logger

logger = get_logger("memory.config")

_CONFIG_PATH = Path(__file__).parent.parent / "data" / "memory_config.json"
_cached_config: MemoryConfig | None = None


def load_config() -> MemoryConfig:
    """从 data/memory_config.json 加载配置（不存在时用默认值）。"""
    global _cached_config
    if _cached_config is not None:
        return _cached_config

    if _CONFIG_PATH.exists():
        try:
            raw = json.loads(_CONFIG_PATH.read_text("utf-8"))
            _cached_config = MemoryConfig.from_dict(raw)
            logger.info(f"记忆配置已加载: {_CONFIG_PATH}")
            return _cached_config
        except Exception as e:
            logger.warning(f"记忆配置加载失败: {e}，使用默认值")

    _cached_config = MemoryConfig()
    return _cached_config


def save_config(config: MemoryConfig) -> None:
    """保存配置到 data/memory_config.json。"""
    global _cached_config
    _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    _CONFIG_PATH.write_text(
        json.dumps(config.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    _cached_config = config
    logger.info(f"记忆配置已保存: {_CONFIG_PATH}")


def reload_config() -> MemoryConfig:
    """强制重新加载配置（热更新）。"""
    global _cached_config
    _cached_config = None
    return load_config()
