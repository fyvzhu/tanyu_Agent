"""
离线索引构建脚本

用法:
  python scripts/build_product_index.py --all                    # 全量构建
  python scripts/build_product_index.py --product-ids 15970 15971  # 指定商品
  python scripts/build_product_index.py --force                  # 强制重建
  python scripts/build_product_index.py --dry-run                # 试运行
"""
import sys
import os
import asyncio
import argparse
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from loguru import logger

from customer_service.clients.ecommerce import EcommerceClient
from customer_service.infrastructure.embedding import get_embedding_service
from customer_service.retrieval.qdrant_retriever import QdrantProductRetriever
from customer_service.retrieval.es_retriever import ElasticsearchProductRetriever
from customer_service.indexing.builder import ProductIndexBuilder
from customer_service.infrastructure.database import get_async_session
from customer_service.config.config import settings

async def main():
    parser = argparse.ArgumentParser(description="构建商品索引")
    parser.add_argument("--all", action="store_true", help="全量构建所有商品")
    parser.add_argument("--product-ids", nargs="+", help="指定商品ID列表")
    parser.add_argument("--force", action="store_true", help="强制重建（忽略manifest）")
    parser.add_argument("--dry-run", action="store_true", help="试运行（不实际写入）")
    args = parser.parse_args()
    
    logger.info("🚀 开始构建商品索引")

    # 初始化依赖
    commerce_client = EcommerceClient(
        base_url=settings.commerce_api_base_url,
        service_token=settings.commerce_service_token,
    )
    embedding_service = get_embedding_service()
    qdrant_retriever = QdrantProductRetriever()
    es_retriever = ElasticsearchProductRetriever()

    logger.info(f"Qdrant: {settings.qdrant_url}")
    logger.info(f"Elasticsearch: {settings.elasticsearch_url}")
    logger.info(f"Commerce API: {settings.commerce_api_base_url}")

    # 确保 Collection 和 Index 存在
    await qdrant_retriever.create_collection()
    await es_retriever.create_index()
    
    # 获取待索引的商品列表
    if args.all:
        # 从 Commerce API 获取所有商品（完整分页枚举）
        product_ids = []
        page = 1
        page_size = 100

        while True:
            catalog = await commerce_client.search_products(
                params={"page": page, "page_size": page_size}
            )
            items = catalog.get("items", [])
            product_ids.extend([p["product_id"] for p in items])

            current_page = catalog.get("page", page)
            total_pages = catalog.get("total_pages", 1)

            logger.info(f"📄 已加载第 {current_page}/{total_pages} 页，累计 {len(product_ids)} 个商品")

            if current_page >= total_pages:
                break

            page += 1

        logger.info(f"📦 全量构建，共 {len(product_ids)} 个商品")
    elif args.product_ids:
        product_ids = args.product_ids
        logger.info(f"📦 指定商品构建，共 {len(product_ids)} 个")
    else:
        logger.error("❌ 请指定 --all 或 --product-ids")
        return

    if args.dry_run:
        logger.info("🔍 试运行模式，将跳过实际写入")
        for product_id in product_ids[:5]:
            logger.info(f"  - {product_id}")
        return

    # 构建索引
    async for db in get_async_session():
        builder = ProductIndexBuilder(
            db_session=db,
            ecommerce_client=commerce_client,
            embedding_client=embedding_service,
            qdrant_retriever=qdrant_retriever,
            es_retriever=es_retriever,
        )

        results = await builder.build_index_batch(product_ids, force=args.force)

    logger.info(f"✅ 索引构建完成: {results}")

    # 关闭连接
    await commerce_client.close()
    await es_retriever.close()
    await embedding_service.close()

if __name__ == "__main__":
    asyncio.run(main())
