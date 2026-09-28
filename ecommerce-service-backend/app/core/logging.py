"""
日志模块：基于loguru的日志配置
"""
from __future__ import annotations

import sys
from pathlib import Path

from loguru import logger

from app.core.config import settings

# 移除默认handler
logger.remove()

# ==================== 控制台输出 ====================
logger.add(
    sys.stdout,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    level=settings.log_level,
    colorize=True,
)

# ==================== 文件输出 ====================
# 创建日志目录
log_path = Path(settings.log_dir)
log_path.mkdir(exist_ok=True, parents=True)

# 所有日志
logger.add(
    log_path / "app_{time:YYYY-MM-DD}.log",
    rotation="00:00",  # 每天午夜轮转
    retention="30 days",  # 保留30天
    compression="zip",  # 压缩旧日志
    encoding="utf-8",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
    level="DEBUG",
)

# 错误日志单独记录
logger.add(
    log_path / "error_{time:YYYY-MM-DD}.log",
    rotation="00:00",
    retention="90 days",  # 错误日志保留更久
    compression="zip",
    encoding="utf-8",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
    level="ERROR",
)

# 导出logger供其他模块使用
__all__ = ["logger"]
