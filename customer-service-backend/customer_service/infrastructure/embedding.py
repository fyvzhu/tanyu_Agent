"""
TEI (Text Embeddings Inference) 客户端
"""
from __future__ import annotations

import logging
from typing import Protocol

import httpx

logger = logging.getLogger(__name__)


class Embedder(Protocol):
    """Embedding 接口协议"""
    
    async def embed(self, text: str) -> list[float]:
        """单条文本 embedding"""
        ...
    
    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """批量文本 embedding"""
        ...


class EmbeddingClient:
    """
    TEI (Text Embeddings Inference) 客户端
    
    支持的 API 格式：
    - POST /embed: {"inputs": str} -> [[float, ...]]
    - POST /embed: {"inputs": [str, ...]} -> [[float, ...], ...]
    """
    
    def __init__(
        self,
        base_url: str = "http://localhost:8080",
        http_client: httpx.AsyncClient | None = None,
        timeout: float = 30.0,
    ):
        """
        Args:
            base_url: TEI 服务地址
            http_client: 复用的 HTTP 客户端（可选）
            timeout: 请求超时时间（秒）
        """
        self.base_url = base_url.rstrip("/")
        self.http_client = http_client or httpx.AsyncClient(timeout=timeout)
        self._owned_client = http_client is None
    
    async def close(self):
        """关闭 HTTP 客户端"""
        if self._owned_client and self.http_client:
            await self.http_client.aclose()
    
    async def embed(self, text: str) -> list[float]:
        """
        单条文本 embedding
        
        Args:
            text: 输入文本
            
        Returns:
            embedding 向量
            
        Raises:
            httpx.HTTPError: 请求失败
            ValueError: 响应格式错误
        """
        try:
            response = await self.http_client.post(
                f"{self.base_url}/embeddings",
                json={"text": text}
            )
            response.raise_for_status()

            # 解析响应
            data = response.json()

            # BGE-M3 service returns {"embeddings": [[float, ...]], ...} for single text
            embeddings = data.get("embeddings")

            if not isinstance(embeddings, list):
                raise ValueError(f"Expected list, got {type(embeddings)}")

            if len(embeddings) == 0:
                raise ValueError("Embedding response is empty")

            # 单条文本请求返回 [[vector]]，需要解包第一层
            embedding = embeddings[0]
            if not isinstance(embedding, list):
                raise ValueError(f"Expected vector list, got {type(embedding)}")

            logger.debug(f"✓ Embedded text (length={len(text)}) -> vector dim={len(embedding)}")
            return embedding
            
        except httpx.HTTPError as e:
            logger.error(f"❌ Embedding request failed: {e}")
            raise
        except Exception as e:
            logger.error(f"❌ Failed to parse embedding response: {e}")
            raise ValueError(f"Invalid embedding response: {e}") from e
    
    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """
        批量文本 embedding

        P0-38 修复：统一使用 {"embeddings": [...]} 响应格式

        Args:
            texts: 输入文本列表

        Returns:
            embedding 向量列表

        Raises:
            httpx.HTTPError: 请求失败
            ValueError: 响应格式错误
        """
        if not texts:
            return []

        try:
            response = await self.http_client.post(
                f"{self.base_url}/embeddings",
                json={"text": texts}
            )
            response.raise_for_status()

            # P0-38: 解析 {"embeddings": [[float, ...], ...]} 格式
            data = response.json()

            embeddings = data.get("embeddings")
            if not isinstance(embeddings, list):
                raise ValueError(f"Expected 'embeddings' list in response, got {type(embeddings)}")

            if len(embeddings) != len(texts):
                raise ValueError(
                    f"Embedding count mismatch: got {len(embeddings)}, expected {len(texts)}"
                )

            logger.debug(
                f"✓ Embedded {len(texts)} texts -> vectors "
                f"dim={len(embeddings[0]) if embeddings else 0}"
            )
            return embeddings

        except httpx.HTTPError as e:
            logger.error(f"❌ Batch embedding request failed: {e}")
            raise
        except Exception as e:
            logger.error(f"❌ Failed to parse batch embedding response: {e}")
            raise ValueError(f"Invalid batch embedding response: {e}") from e
    
    async def health_check(self) -> bool:
        """
        健康检查
        
        Returns:
            服务是否可用
        """
        try:
            response = await self.http_client.get(
                f"{self.base_url}/health",
                timeout=5.0
            )
            return response.status_code == 200
        except Exception as e:
            logger.warning(f"Health check failed: {e}")
            return False


class DisabledEmbedder:
    """禁用的 Embedder（用于降级场景）"""

    async def embed(self, text: str) -> list[float]:
        raise RuntimeError("Embedding service is disabled")

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        raise RuntimeError("Embedding service is disabled")


class LocalEmbedder:
    """
    本地 Sentence Transformers Embedder

    作为 TEI 的 fallback，使用本地模型生成 embeddings
    """

    def __init__(self, model_name: str = "BAAI/bge-base-zh-v1.5", batch_size: int = 32):
        """
        Args:
            model_name: 模型名称或路径
            batch_size: 批处理大小
        """
        self.model_name = model_name
        self.batch_size = batch_size
        self._model = None

        from loguru import logger as loguru_logger
        self.logger = loguru_logger

    def _load_model(self):
        """懒加载模型"""
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer

                self.logger.info(f"加载本地 Embedding 模型: {self.model_name}")
                self._model = SentenceTransformer(self.model_name)
                self.logger.info(f"模型加载成功，向量维度: {self._model.get_sentence_embedding_dimension()}")
            except Exception as e:
                self.logger.error(f"加载本地模型失败: {e}")
                raise

        return self._model

    async def embed(self, text: str) -> list[float]:
        """
        单条文本 embedding

        Args:
            text: 输入文本

        Returns:
            embedding 向量
        """
        embeddings = await self.embed_batch([text])
        return embeddings[0]

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """
        批量文本 embedding

        Args:
            texts: 输入文本列表

        Returns:
            embedding 向量列表
        """
        if not texts:
            return []

        model = self._load_model()

        # 生成 embeddings
        embeddings_np = model.encode(
            texts,
            batch_size=self.batch_size,
            show_progress_bar=False,
            convert_to_numpy=True,
            normalize_embeddings=True,  # 归一化，便于余弦相似度计算
        )

        self.logger.debug(f"本地模型生成 {len(texts)} 个 embeddings，维度: {embeddings_np.shape[1]}")

        # 转为 list[list[float]]
        return embeddings_np.tolist()


class EmbeddingServiceWithFallback:
    """
    带 Fallback 的 Embedding 服务

    优先使用 TEI，失败时自动切换到本地模型
    """

    def __init__(
        self,
        tei_url: str | None = None,
        enable_tei: bool = True,
        local_model_name: str = "BAAI/bge-base-zh-v1.5",
        batch_size: int = 32,
    ):
        """
        Args:
            tei_url: TEI 服务地址
            enable_tei: 是否启用 TEI
            local_model_name: 本地 fallback 模型
            batch_size: 批处理大小
        """
        from loguru import logger as loguru_logger
        self.logger = loguru_logger

        self.enable_tei = enable_tei and tei_url is not None

        if self.enable_tei:
            self.tei_client = EmbeddingClient(base_url=tei_url)
            self.logger.info(f"Embedding 服务初始化: TEI 启用 ({tei_url})")
        else:
            self.tei_client = None
            self.logger.info("Embedding 服务初始化: TEI 禁用")

        self.local_embedder = LocalEmbedder(
            model_name=local_model_name,
            batch_size=batch_size
        )

        self._tei_failed = False  # 记录 TEI 是否已失败

    async def embed(self, text: str) -> list[float]:
        """单条文本 embedding"""
        return (await self.embed_batch([text]))[0]

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """批量文本 embedding"""
        if not texts:
            return []

        # 尝试 TEI
        if self.enable_tei and not self._tei_failed:
            try:
                embeddings = await self.tei_client.embed_batch(texts)
                self.logger.debug(f"TEI 生成 {len(embeddings)} 个 embeddings")
                return embeddings
            except Exception as e:
                self.logger.warning(f"TEI 调用失败，切换到本地模型: {e}")
                self._tei_failed = True

        # Fallback 到本地模型
        embeddings = await self.local_embedder.embed_batch(texts)
        return embeddings

    async def close(self):
        """关闭资源"""
        if self.tei_client:
            await self.tei_client.close()


# 全局单例
_embedding_service: EmbeddingServiceWithFallback | None = None


def get_embedding_service() -> EmbeddingServiceWithFallback:
    """获取全局 Embedding Service 单例"""
    global _embedding_service

    if _embedding_service is None:
        from customer_service.config.config import settings

        _embedding_service = EmbeddingServiceWithFallback(
            tei_url=settings.embedding_service_url if settings.embedding_enabled else None,
            enable_tei=settings.embedding_enabled,
            local_model_name=settings.embedding_model_name,
            batch_size=settings.embedding_batch_size,
        )

    return _embedding_service
