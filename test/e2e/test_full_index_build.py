"""
完整全量 RAG 索引构建测试

使用部署的 Docker 服务：
- MySQL (43306) - 获取全部 83 个商品
- Embedding (8100) - BGE-M3 模型（1024维）
- Qdrant (6333) - 向量存储
- Elasticsearch (9200) - BM25 全文检索
"""
import sys
import asyncio
from pathlib import Path

project_root = Path(__file__).parent / "customer-service-backend"
sys.path.insert(0, str(project_root))

from loguru import logger
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from elasticsearch import AsyncElasticsearch
import httpx

from customer_service.config.config import settings
from customer_service.clients.ecommerce import EcommerceClient
from customer_service.indexing.chunker import ProductChunker
from customer_service.indexing.manifest import compute_source_hash, compute_index_signature


async def get_all_product_ids():
    """从 MySQL 直接获取所有商品ID"""
    import aiomysql

    # 连接 MySQL
    conn = await aiomysql.connect(
        host='127.0.0.1',
        port=43306,
        user='zhutou',
        password='618618',
        db='ecommerce_db',
    )

    async with conn.cursor() as cursor:
        await cursor.execute("SELECT product_id FROM products ORDER BY product_id")
        rows = await cursor.fetchall()
        product_ids = [row[0] for row in rows]

    conn.close()
    return product_ids


async def call_embedding_service(texts: list[str]) -> list[list[float]]:
    """调用 Docker embedding 服务（BGE-M3）"""
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            f"{settings.embedding_service_url}/embeddings",
            json={"text": texts, "model": "bge-m3"}
        )
        response.raise_for_status()
        
        data = response.json()
        return data["embeddings"]


async def build_full_index():
    """构建完整索引"""
    logger.info("=" * 80)
    logger.info("🚀 开始完整全量索引构建")
    logger.info("=" * 80)
    
    # 1. 获取所有商品ID
    logger.info("\n📦 Step 1: 获取所有商品ID...")
    product_ids = await get_all_product_ids()
    logger.info(f"✓ 从 MySQL 获取到 {len(product_ids)} 个商品")
    
    # 2. 初始化客户端
    logger.info("\n🔧 Step 2: 初始化服务...")
    commerce = EcommerceClient(
        base_url=settings.commerce_api_base_url,
        service_token=settings.commerce_service_token,
    )
    qdrant = QdrantClient(url=settings.qdrant_url)
    es = AsyncElasticsearch([settings.elasticsearch_url])
    chunker = ProductChunker()
    
    # 检查 embedding 服务
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{settings.embedding_service_url}/health")
            health = resp.json()
            logger.info(f"✓ Embedding 服务: {health}")
    except Exception as e:
        logger.error(f"❌ Embedding 服务不可用: {e}")
        return
    
    # 3. 创建 Collection 和 Index
    logger.info("\n🗄️  Step 3: 创建 Qdrant Collection 和 ES Index...")
    
    # 删除旧的
    try:
        qdrant.delete_collection(settings.qdrant_collection_name)
        logger.info("✓ 删除旧的 Qdrant Collection")
    except:
        pass
    
    # 创建新的 Collection（1024维，BGE-M3）
    qdrant.create_collection(
        collection_name=settings.qdrant_collection_name,
        vectors_config=VectorParams(
            size=settings.qdrant_vector_size,
            distance=Distance.COSINE,
        ),
    )
    logger.info(f"✓ Qdrant Collection 创建成功（{settings.qdrant_vector_size}维）")
    
    # 删除旧的 ES Index
    if await es.indices.exists(index=settings.elasticsearch_index_name):
        await es.indices.delete(index=settings.elasticsearch_index_name)
        logger.info("✓ 删除旧的 ES Index")
    
    # 创建新的 ES Index
    await es.indices.create(
        index=settings.elasticsearch_index_name,
        body={
            "mappings": {
                "properties": {
                    "chunk_id": {"type": "keyword"},
                    "product_id": {"type": "keyword"},
                    "chunk_type": {"type": "keyword"},
                    "text": {"type": "text", "analyzer": "ik_max_word"},
                    "brand": {"type": "keyword"},
                    "category": {"type": "keyword"},
                }
            }
        }
    )
    logger.info("✓ ES Index 创建成功")
    
    # 4. 索引所有商品
    logger.info(f"\n📊 Step 4: 索引 {len(product_ids)} 个商品...")
    logger.info("=" * 80)
    
    success_count = 0
    failed_count = 0
    total_chunks = 0
    
    for i, product_id in enumerate(product_ids, 1):
        try:
            # 获取 Knowledge Card
            knowledge_card = await commerce.get_product_knowledge_card(product_id)
            if not knowledge_card:
                logger.warning(f"[{i}/{len(product_ids)}] ⚠️  {product_id}: 商品不存在")
                failed_count += 1
                continue
            
            # 切分
            chunks = chunker.chunk_product(product_id, knowledge_card)
            
            # 生成向量
            texts = [chunk.text for chunk in chunks]
            vectors = await call_embedding_service(texts)
            
            # 计算哈希
            source_hash = compute_source_hash(knowledge_card)
            index_signature = compute_index_signature(
                source_hash=source_hash,
                schema_version="v1",
                chunker_version="v1",
                embedding_model=settings.embedding_model_name,
                embedding_dimension=settings.qdrant_vector_size,
            )
            
            # 写入 Qdrant
            points = []
            for chunk, vector in zip(chunks, vectors):
                points.append(PointStruct(
                    id=hash(chunk.chunk_id) % (2**63),
                    vector=vector,
                    payload={
                        "chunk_id": chunk.chunk_id,
                        "product_id": chunk.product_id,
                        "chunk_type": chunk.chunk_type,
                        "text": chunk.text,
                        "brand": chunk.metadata.get("brand"),
                        "category": chunk.metadata.get("category"),
                    }
                ))
            
            qdrant.upsert(
                collection_name=settings.qdrant_collection_name,
                points=points,
            )
            
            # 写入 ES
            bulk_data = []
            for chunk in chunks:
                bulk_data.append({"index": {"_index": settings.elasticsearch_index_name, "_id": chunk.chunk_id}})
                bulk_data.append({
                    "chunk_id": chunk.chunk_id,
                    "product_id": chunk.product_id,
                    "chunk_type": chunk.chunk_type,
                    "text": chunk.text,
                    "brand": chunk.metadata.get("brand"),
                    "category": chunk.metadata.get("category"),
                })
            
            await es.bulk(operations=bulk_data)
            
            logger.info(
                f"[{i}/{len(product_ids)}] ✅ {product_id}: "
                f"{knowledge_card['brand']} {knowledge_card['product_display_name']} "
                f"({len(chunks)} chunks)"
            )
            
            success_count += 1
            total_chunks += len(chunks)
            
        except Exception as e:
            logger.error(f"[{i}/{len(product_ids)}] ❌ {product_id}: {e}")
            failed_count += 1
    
    # 5. 总结
    await commerce.close()
    await es.close()
    
    logger.info("\n" + "=" * 80)
    logger.info("🎉 索引构建完成！")
    logger.info("=" * 80)
    logger.info(f"✅ 成功: {success_count} 个商品")
    logger.info(f"❌ 失败: {failed_count} 个商品")
    logger.info(f"📦 总 chunks: {total_chunks}")
    logger.info(f"💾 Qdrant: {total_chunks} 个向量 ({settings.qdrant_vector_size}维)")
    logger.info(f"🔍 Elasticsearch: {total_chunks} 个文档")
    logger.info("=" * 80)


if __name__ == "__main__":
    asyncio.run(build_full_index())
