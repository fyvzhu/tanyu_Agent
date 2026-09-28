from elasticsearch import AsyncElasticsearch
from customer_service.retrieval.models import QueryContext
from loguru import logger


class ElasticsearchProductRetriever:
    """Elasticsearch BM25 关键词检索器"""
    
    INDEX_NAME = "product_chunks"
    
    def __init__(self, es_url: str = "http://localhost:9200"):
        self.client = AsyncElasticsearch([es_url])
    
    async def search(
        self,
        query: str,
        context: QueryContext,
        top_k: int = 10,
    ) -> list[tuple[str, float]]:
        """
        BM25 关键词检索
        
        返回: [(chunk_id, score), ...]
        """
        logger.info(f"🔍 ES search: query='{query}', top_k={top_k}")
        
        try:
            # 构造查询
            es_query = {
                "query": {
                    "bool": {
                        "must": [
                            {
                                "multi_match": {
                                    "query": query,
                                    "fields": ["text^2", "brand", "category"],
                                    "type": "best_fields",
                                }
                            }
                        ],
                        "filter": self._build_filters(context),
                    }
                },
                "size": top_k,
            }
            
            # 执行检索
            response = await self.client.search(index=self.INDEX_NAME, body=es_query)
            
            # 提取结果
            results = [
                (hit["_id"], hit["_score"])
                for hit in response["hits"]["hits"]
            ]
            logger.debug(f"✅ ES returned {len(results)} chunks")
            return results
        
        except Exception as e:
            logger.error(f"❌ ES search failed: {e}")
            raise
    
    def _build_filters(self, context: QueryContext) -> list[dict]:
        """构造 ES 过滤条件"""
        filters = []
        
        if brand := context.hard_filters.get("brand"):
            filters.append({"term": {"brand": brand}})
        
        if category := context.hard_filters.get("category"):
            filters.append({"term": {"category": category}})
        
        return filters
    
    async def create_index(self):
        """创建索引（如果不存在）"""
        try:
            if not await self.client.indices.exists(index=self.INDEX_NAME):
                await self.client.indices.create(
                    index=self.INDEX_NAME,
                    body={
                        "mappings": {
                            "properties": {
                                "product_id": {"type": "keyword"},
                                "chunk_id": {"type": "keyword"},
                                "chunk_type": {"type": "keyword"},
                                "text": {"type": "text", "analyzer": "standard"},
                                "brand": {"type": "keyword"},
                                "category": {"type": "keyword"},
                                "source_hash": {"type": "keyword"},
                                "index_signature": {"type": "keyword"},
                            }
                        }
                    }
                )
                logger.info(f"✅ Created ES index: {self.INDEX_NAME}")
            else:
                logger.info(f"ℹ️ ES index already exists: {self.INDEX_NAME}")
        
        except Exception as e:
            logger.error(f"❌ Failed to create ES index: {e}")
            raise
    
    async def bulk_index_chunks(self, chunks: list[dict]):
        """
        批量索引 chunks

        P0-42 修复：确保所有字段都写入 _source，包括 chunk_id
        """
        try:
            from elasticsearch.helpers import async_bulk

            actions = [
                {
                    "_index": self.INDEX_NAME,
                    "_id": chunk["chunk_id"],
                    "_source": {
                        "chunk_id": chunk["chunk_id"],  # P0-42: 显式写入 chunk_id
                        "product_id": chunk["product_id"],
                        "chunk_type": chunk["chunk_type"],
                        "text": chunk["text"],
                        "brand": chunk.get("brand"),
                        "category": chunk.get("category"),
                        "source_hash": chunk.get("source_hash"),
                        "index_signature": chunk.get("index_signature"),
                    }
                }
                for chunk in chunks
            ]

            success, failed = await async_bulk(self.client, actions)
            logger.info(f"✅ Indexed {success} chunks to ES, {failed} failed")

        except Exception as e:
            logger.error(f"❌ Failed to bulk index chunks to ES: {e}")
            raise
    
    async def close(self):
        """关闭客户端连接"""
        await self.client.close()
