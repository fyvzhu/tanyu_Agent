"""
应用配置模块
使用环境变量管理所有配置项
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


# 项目根目录：ecommerce-service-backend/
PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """应用配置"""

    # ==================== 基础配置 ====================
    app_name: str = "Tanyu E-commerce Service"
    app_version: str = "1.0.0"
    app_host: str = "0.0.0.0"
    app_port: int = 8001
    debug: bool = False

    # ==================== 数据库配置 ====================
    database_url: str = "mysql+pymysql://zhutou:618618@localhost:43306/ecommerce_db?charset=utf8mb4"

    # ==================== JWT配置 ====================
    jwt_algorithm: str = "RS256"
    jwt_issuer: str = "tanyu-ecommerce-service"
    jwt_audience: str = "tanyu-services"
    # 移除默认值，强制从环境变量读取
    jwt_private_key_path: str
    jwt_public_key_path: str
    jwt_access_token_expire_minutes: int = 30
    jwt_refresh_token_expire_days: int = 7

    # ==================== 密码加密配置 ====================
    password_hash_algorithm: str = "argon2"  # argon2 或 bcrypt

    # ==================== Internal API Token ====================
    internal_service_token: str = "tanyu-internal-service-token-change-in-production"

    # ==================== Phase 2 预留配置 ====================
    # Redis
    redis_url: str | None = "redis://:618618@localhost:6379/0"
    redis_enabled: bool = False  # Phase 1不使用

    # Qdrant
    qdrant_url: str | None = "http://localhost:6333"
    qdrant_enabled: bool = False  # Phase 1不使用

    # Elasticsearch
    elasticsearch_url: str | None = "http://localhost:9200"
    elasticsearch_enabled: bool = False  # Phase 1不使用

    # Embedding服务
    embedding_service_url: str | None = "http://localhost:8100"
    embedding_enabled: bool = False  # Phase 1不使用

    # Langfuse
    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None
    langfuse_host: str | None = "http://localhost:3000"
    langfuse_enabled: bool = False  # Phase 1不使用

    # ==================== 静态文件配置 ====================
    static_images_dir: str = "static/images"

    # ==================== 日志配置 ====================
    log_level: str = "INFO"
    log_dir: str = "logs"

    # ==================== CORS配置 ====================
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )


def absolute_project_path(value: str) -> Path:
    """
    将相对路径转换为项目根目录的绝对路径

    Args:
        value: 文件路径（可以是相对路径或绝对路径）

    Returns:
        绝对路径
    """
    p = Path(value).expanduser()
    return p if p.is_absolute() else PROJECT_ROOT / p


@lru_cache
def get_settings() -> Settings:
    """获取配置实例（单例）"""
    return Settings()


# 全局配置实例
settings = get_settings()
