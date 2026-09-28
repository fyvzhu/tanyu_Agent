from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Protocol

import httpx


class Embedder(Protocol):
    async def embed(self, text: str) -> list[float]:
        ...


class SemanticRetriever(Protocol):
    async def search(self, query: str, vector: list[float], limit: int) -> list[dict[str, Any]]:
        ...


class LexicalRetriever(Protocol):
    async def search(self, query: str, limit: int) -> list[dict[str, Any]]:
        ...


class HttpEmbeddingClient:
    def __init__(self, base_url: str, http: httpx.AsyncClient | None = None):
        self.base_url = base_url.rstrip("/")
        self.http = http or httpx.AsyncClient(timeout=5.0)

    async def embed(self, text: str) -> list[float]:
        response = await self.http.post(f"{self.base_url}/embeddings", json={"text": text})
        response.raise_for_status()
        payload = response.json()
        # BGE-M3 service returns {"embeddings": [[float, ...]], ...} for single text
        embeddings = payload.get("embeddings")
        if not isinstance(embeddings, list):
            raise ValueError(f"embedding response missing embeddings, got: {type(embeddings)}")

        # 单条文本请求返回 [[vector]]，需要解包第一层
        if len(embeddings) == 0:
            raise ValueError("embedding response is empty")

        vector = embeddings[0]  # 取第一个向量
        if not isinstance(vector, list):
            raise ValueError(f"expected vector list, got: {type(vector)}")

        return vector


class DisabledEmbedder:
    async def embed(self, text: str) -> list[float]:
        raise RuntimeError("embedding disabled")


class QdrantProductRetriever:
    def __init__(self, url: str, collection_name: str = "product_knowledge", http: httpx.AsyncClient | None = None):
        self.url = url.rstrip("/")
        self.collection_name = collection_name
        self.http = http or httpx.AsyncClient(timeout=5.0)

    async def search(self, query: str, vector: list[float], limit: int) -> list[dict[str, Any]]:
        response = await self.http.post(
            f"{self.url}/collections/{self.collection_name}/points/search",
            json={
                "vector": vector,
                "limit": limit,
                "with_payload": True,
            },
        )
        response.raise_for_status()
        results = response.json().get("result") or []
        candidates: list[dict[str, Any]] = []
        for item in results:
            payload = item.get("payload") or {}
            product_id = payload.get("product_id")
            if product_id:
                candidates.append(
                    {
                        "product_id": str(product_id),
                        "score": float(item.get("score") or 0),
                        "source": "qdrant",
                        "matched_reasons": payload.get("usage_tags") or payload.get("style_tags") or [],
                    }
                )
        return candidates

    async def create_collection(self, vector_size: int = 1024) -> None:
        """创建 Qdrant Collection"""
        try:
            response = await self.http.put(
                f"{self.url}/collections/{self.collection_name}",
                json={
                    "vectors": {
                        "size": vector_size,
                        "distance": "Cosine"
                    }
                }
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            if e.response.status_code != 409:  # 409 表示 collection 已存在
                raise

    async def upsert_chunks(self, chunk_payloads: list[dict[str, Any]]) -> None:
        """批量插入或更新 chunks"""
        points = []
        for chunk in chunk_payloads:
            points.append({
                "id": chunk["chunk_id"],
                "vector": chunk["vector"],
                "payload": {
                    "chunk_id": chunk["chunk_id"],
                    "product_id": chunk["product_id"],
                    "chunk_type": chunk["chunk_type"],
                    "text": chunk["text"],
                    "brand": chunk.get("brand"),
                    "category": chunk.get("category"),
                    "source_hash": chunk.get("source_hash"),
                    "index_signature": chunk.get("index_signature"),
                }
            })

        response = await self.http.put(
            f"{self.url}/collections/{self.collection_name}/points",
            json={"points": points}
        )
        response.raise_for_status()


class ElasticsearchProductRetriever:
    def __init__(self, url: str, index_name: str = "product_knowledge", http: httpx.AsyncClient | None = None):
        self.url = url.rstrip("/")
        self.index_name = index_name
        self.http = http or httpx.AsyncClient(timeout=5.0)

    async def search(self, query: str, limit: int) -> list[dict[str, Any]]:
        response = await self.http.post(
            f"{self.url}/{self.index_name}/_search",
            json={
                "size": limit,
                "query": {
                    "multi_match": {
                        "query": query,
                        "fields": [
                            "brand^2",
                            "product_display_name^3",
                            "category^2",
                            "material",
                            "selling_points",
                            "usage_tags",
                            "style_tags",
                        ],
                    }
                },
            },
        )
        response.raise_for_status()
        hits = response.json().get("hits", {}).get("hits", [])
        candidates: list[dict[str, Any]] = []
        for item in hits:
            source = item.get("_source") or {}
            product_id = source.get("product_id")
            if product_id:
                candidates.append(
                    {
                        "product_id": str(product_id),
                        "score": float(item.get("_score") or 0),
                        "source": "elasticsearch",
                        "matched_reasons": source.get("usage_tags") or source.get("style_tags") or [],
                    }
                )
        return candidates


@dataclass
class RetrievalOutcome:
    product_ids: list[str]
    mode: str
    evidence: list[dict[str, Any]]
    scores: dict[str, float]
    matched_reasons: dict[str, list[str]]


class ProductRetrievalService:
    def __init__(
        self,
        *,
        embedder: Embedder | None = None,
        semantic: SemanticRetriever | None = None,
        lexical: LexicalRetriever | None = None,
    ):
        self.embedder = embedder
        self.semantic = semantic
        self.lexical = lexical

    async def retrieve(self, query: str, limit: int = 20) -> RetrievalOutcome:
        semantic_candidates: list[dict[str, Any]] = []
        lexical_candidates: list[dict[str, Any]] = []
        evidence: list[dict[str, Any]] = []
        failures: list[str] = []

        if self.semantic and self.embedder:
            try:
                from loguru import logger
                logger.info(f"[DEBUG] 开始 Qdrant 检索，query: {query}")
                vector = await self.embedder.embed(query)
                logger.info(f"[DEBUG] Embedding 生成成功，vector length: {len(vector)}")
                semantic_candidates = await self.semantic.search(query, vector, limit)
                logger.info(f"[DEBUG] Qdrant 检索成功，返回 {len(semantic_candidates)} 个结果")
                evidence.extend({"source": "qdrant", "product_id": item["product_id"]} for item in semantic_candidates)
            except Exception as exc:
                from loguru import logger
                logger.error(f"[DEBUG] Qdrant 检索失败: {type(exc).__name__} - {str(exc)}", exc_info=True)
                failures.append(f"qdrant:{type(exc).__name__}")

        if self.lexical:
            try:
                from loguru import logger
                logger.info(f"[DEBUG] 开始 Elasticsearch 检索，query: {query}")
                lexical_candidates = await self.lexical.search(query, limit)
                logger.info(f"[DEBUG] Elasticsearch 检索成功，返回 {len(lexical_candidates)} 个结果")
                evidence.extend({"source": "elasticsearch", "product_id": item["product_id"]} for item in lexical_candidates)
            except Exception as exc:
                from loguru import logger
                logger.error(f"[DEBUG] Elasticsearch 检索失败: {type(exc).__name__} - {str(exc)}", exc_info=True)
                failures.append(f"elasticsearch:{type(exc).__name__}")

        fused = self._rrf([semantic_candidates, lexical_candidates])
        if semantic_candidates and lexical_candidates:
            mode = "qdrant_es_commerce"
        elif semantic_candidates:
            mode = "qdrant_commerce_degraded"
        elif lexical_candidates:
            mode = "es_commerce_degraded"
        else:
            mode = "commerce_only_degraded"

        if failures:
            evidence.append({"source": "retrieval", "failures": failures})

        return RetrievalOutcome(
            product_ids=list(fused.keys())[:limit],
            mode=mode,
            evidence=evidence,
            scores=fused,
            matched_reasons=self._matched_reasons([semantic_candidates, lexical_candidates]),
        )

    @staticmethod
    def _rrf(candidate_lists: list[list[dict[str, Any]]], k: int = 60) -> dict[str, float]:
        """
        P1-44 修复：先聚合到商品级，再做跨来源融合
        避免同一商品的多个 chunk 在同一来源中重复加分

        步骤：
        1. 对每个来源，同一 product_id 只保留第一次出现的排名
        2. 然后再进行跨来源的 RRF 融合
        """
        scores: dict[str, float] = {}

        for candidates in candidate_lists:
            # P1-44: 对当前来源去重，每个 product_id 只取最高排名（第一次出现）
            seen_products: set[str] = set()

            for rank, item in enumerate(candidates, start=1):
                product_id = item["product_id"]

                # 同一商品在当前来源中只计算一次
                if product_id in seen_products:
                    continue

                seen_products.add(product_id)
                scores[product_id] = scores.get(product_id, 0.0) + 1.0 / (k + rank)

        return dict(sorted(scores.items(), key=lambda item: item[1], reverse=True))

    @staticmethod
    def _matched_reasons(candidate_lists: list[list[dict[str, Any]]]) -> dict[str, list[str]]:
        reasons: dict[str, list[str]] = {}
        for candidates in candidate_lists:
            for item in candidates:
                product_id = item["product_id"]
                existing = reasons.setdefault(product_id, [])
                for reason in item.get("matched_reasons") or []:
                    if reason not in existing:
                        existing.append(str(reason))
        return reasons


def sku_filter_payload(
    *,
    product_ids: list[str] | None,
    colors: list[str] | None,
    sizes: list[str] | None,
    min_price: Decimal | None,
    max_price: Decimal | None,
    stock_status: str | None,
) -> dict[str, Any]:
    return {
        "product_ids": product_ids,
        "colors": colors,
        "sizes": sizes,
        "min_price": str(min_price) if min_price is not None else None,
        "max_price": str(max_price) if max_price is not None else None,
        "stock_status": stock_status,
    }
