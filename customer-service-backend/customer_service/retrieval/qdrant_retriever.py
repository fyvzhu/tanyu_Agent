import uuid
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct, Distance, VectorParams, Filter, FieldCondition, MatchValue
from customer_service.infrastructure.embedding import EmbeddingClient
from customer_service.retrieval.models import QueryContext
from loguru import logger

# P0-41 修复：定义稳定的 UUID namespace 用于生成 Point ID
CHUNK_ID_NAMESPACE = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")


class QdrantProductRetriever:
    """Qdrant 向量检索器"""
    
    COLLECTION_NAME = "product_chunks"
    VECTOR_SIZE = 1024  # BAAI/bge-m3
    
    def __init__(
        self,
        qdrant_url: str = "http://localhost:6333",
        embedding_client: EmbeddingClient | None = None,
    ):
        self.client = QdrantClient(url=qdrant_url)
        self.embedding_client = embedding_client or EmbeddingClient()
    
    async def search(
        self,
        query: str,
        context: QueryContext,
        top_k: int = 10,
    ) -> list[tuple[str, float]]:
        """
        向量检索
        
        返回: [(chunk_id, score), ...]
        """
        logger.info(f"🔍 Qdrant search: query='{query}', top_k={top_k}")
        
        try:
            # 1. 生成查询向量
            query_vector = await self.embedding_client.embed_query(query)
            
            # 2. 构造过滤条件
            filter_conditions = self._build_filter(context)
            
            # 3. 执行检索
            search_result = self.client.search(
                collection_name=self.COLLECTION_NAME,
                query_vector=query_vector,
                query_filter=filter_conditions,
                limit=top_k,
            )
            
            # 4. 提取结果
            results = [(hit.id, hit.score) for hit in search_result]
            logger.debug(f"✅ Qdrant returned {len(results)} chunks")
            return results
        
        except Exception as e:
            logger.error(f"❌ Qdrant search failed: {e}")
            raise
    
    def _build_filter(self, context: QueryContext) -> Filter | None:
        """构造 Qdrant 过滤条件"""
        must_conditions = []
        
        # 品牌过滤
        if brand := context.hard_filters.get("brand"):
            must_conditions.append(
                FieldCondition(key="brand", match=MatchValue(value=brand))
            )
        
        # 类别过滤
        if category := context.hard_filters.get("category"):
            must_conditions.append(
                FieldCondition(key="category", match=MatchValue(value=category))
            )
        
        if not must_conditions:
            return None
        
        return Filter(must=must_conditions)
    
    async def create_collection(self):
        """创建 Collection（如果不存在）"""
        try:
            collections = self.client.get_collections().collections
            collection_names = [c.name for c in collections]
            
            if self.COLLECTION_NAME not in collection_names:
                self.client.create_collection(
                    collection_name=self.COLLECTION_NAME,
                    vectors_config=VectorParams(
                        size=self.VECTOR_SIZE,
                        distance=Distance.COSINE,
                    ),
                )
                logger.info(f"✅ Created Qdrant collection: {self.COLLECTION_NAME}")
            else:
                logger.info(f"ℹ️ Qdrant collection already exists: {self.COLLECTION_NAME}")
        
        except Exception as e:
            logger.error(f"❌ Failed to create Qdrant collection: {e}")
            raise
    
    async def upsert_chunks(self, chunks: list[dict]):
        """
        批量插入 chunks

        P0-41 修复：从 chunk_id 字符串生成稳定的 UUID 作为 Point ID
        - chunk_id 保留在 payload 中用于逻辑引用
        - Point ID 使用 UUID v5 从 chunk_id 生成，保证稳定性
        """
        try:
            points = []
            for chunk in chunks:
                # P0-41: 从 chunk_id 生成稳定的 UUID
                chunk_id_str = chunk["chunk_id"]
                point_id = str(uuid.uuid5(CHUNK_ID_NAMESPACE, chunk_id_str))

                point = PointStruct(
                    id=point_id,  # UUID 格式
                    vector=chunk["vector"],
                    payload={
                        "chunk_id": chunk_id_str,  # 保留逻辑 ID
                        "product_id": chunk["product_id"],
                        "chunk_type": chunk["chunk_type"],
                        "text": chunk["text"],
                        "brand": chunk.get("brand"),
                        "category": chunk.get("category"),
                        "source_hash": chunk.get("source_hash"),
                        "index_signature": chunk.get("index_signature"),
                    }
                )
                points.append(point)

            self.client.upsert(
                collection_name=self.COLLECTION_NAME,
                points=points,
            )
            logger.info(f"✅ Upserted {len(points)} chunks to Qdrant")

        except Exception as e:
            logger.error(f"❌ Failed to upsert chunks to Qdrant: {e}")
            raise
