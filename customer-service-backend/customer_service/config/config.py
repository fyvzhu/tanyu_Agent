from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


# 项目根目录：customer-service-backend/
PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE_PATH = PROJECT_ROOT / ".env"


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


class Settings(BaseSettings):
    """Runtime settings for the Phase 2 presales agent service."""

    model_config = SettingsConfigDict(
        env_file=ENV_FILE_PATH,
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "Tanyu Presales Agent Service"
    app_host: str = "0.0.0.0"
    app_port: int = 8000

    # LLM 配置
    llm_model: str = "qwen3.5-plus"
    llm_base_url: str = ""
    llm_api_key: str = ""

    # Commerce Service 配置
    commerce_api_base_url: str = "http://127.0.0.1:8001"
    commerce_service_token: str = "tanyu-internal-service-token-change-in-production"

    # JWT 配置 - RS256 验证（Agent 只验证，不签发）
    jwt_algorithm: str = "RS256"
    jwt_public_key_path: str  # 移除默认值，强制从环境变量读取
    jwt_audience: str = "tanyu-services"  # JWT audience
    jwt_issuer: str = "tanyu-ecommerce-service"  # JWT issuer

    # 数据库配置（双 URL 模式）
    agent_async_database_url: str = "mysql+aiomysql://zhutou:618618@127.0.0.1:43306/customer_service?charset=utf8mb4"
    agent_sync_database_url: str = "mysql+pymysql://zhutou:618618@127.0.0.1:43306/customer_service?charset=utf8mb4"

    # Redis 配置（LangGraph Checkpointer + Cache）
    redis_url: str = "redis://:618618@localhost:6379/0"
    redis_enabled: bool = True
    redis_checkpoint_ttl_seconds: int = 86400  # Checkpoint 过期时间 24h

    # 向量数据库和 RAG 配置
    qdrant_url: str = "http://localhost:6333"
    qdrant_enabled: bool = True  # Slice02 启用
    qdrant_collection_name: str = "product_chunks"  # P0-40 修复：统一为 product_chunks
    qdrant_vector_size: int = 1024  # BGE-M3 的向量维度

    elasticsearch_url: str = "http://localhost:9200"
    elasticsearch_enabled: bool = True  # Slice02 启用
    elasticsearch_index_name: str = "product_chunks"  # P0-40 修复：统一为 product_chunks

    # Embedding 服务配置
    embedding_service_url: str = "http://localhost:8100"  # Docker embedding 服务
    embedding_enabled: bool = True  # 启用 TEI/自建服务
    embedding_model_name: str = "BAAI/bge-m3"  # BGE-M3 模型
    embedding_batch_size: int = 32

    # RAG 检索配置
    rag_top_k: int = 10  # 初始检索数量
    rag_min_valid_candidates: int = 3  # 最少候选数
    rag_rerank_top_k: int = 5  # 重排后返回数量
    rag_enable_multi_query: bool = False  # Multi-query 默认关闭
    rag_enable_hyde: bool = False  # HyDE 默认关闭
    rag_rrf_k: int = 60  # RRF 参数

    # Langfuse 可观测性（fail-open）
    langfuse_enabled: bool = False
    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None
    langfuse_host: str = "http://localhost:3000"

    # CORS 配置
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    # Task Stack 配置
    max_concurrent_tasks: int = 3  # 最大并发任务数
    task_timeout_seconds: int = 300  # 单个任务超时时间 5min


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
