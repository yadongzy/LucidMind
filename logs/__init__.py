"""LucidMind 模块日志系统。

每个模块一个独立日志文件，存放在 logs/ 目录下。
日志是给人看的，不是给机器看的。
"""

import io
import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOGS_DIR = Path(__file__).parent
LOGS_DIR.mkdir(exist_ok=True)

# 日志格式：时间 | 模块 | 级别 | 消息
_FORMAT = "%(asctime)s | %(name)s | %(levelname)s | %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def get_logger(module_name: str) -> logging.Logger:
    """获取模块专属 logger，自动写入对应的日志文件。

    Args:
        module_name: 模块名，如 "brain", "llm", "tools", "memory", "stream", "learning", "api"

    Returns:
        配置好的 Logger，同时输出到文件和控制台。
    """
    logger = logging.getLogger(f"lucid.{module_name}")

    # 避免重复添加 handler
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)

    # 文件 handler — 写入 logs/{module_name}.log（自动轮转，单文件5MB，保留3个备份）
    log_file = LOGS_DIR / f"{module_name}.log"
    file_handler = RotatingFileHandler(
        log_file, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(_FORMAT, datefmt=_DATE_FORMAT))

    # 控制台 handler — INFO 及以上（强制 UTF-8，修复 Windows GBK 乱码）
    if sys.platform == "win32" and hasattr(sys.stderr, "buffer"):
        utf8_stream = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
        console_handler = logging.StreamHandler(utf8_stream)
    else:
        console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(logging.Formatter(_FORMAT, datefmt=_DATE_FORMAT))

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    # 不向上传播，避免重复输出
    logger.propagate = False

    return logger
