"""
商品索引构建脚本（简化版）

功能：
1. 直接从 MySQL 读取商品数据
2. 为每个商品生成 ProductKnowledgeCard 的向量索引
3. 写入 Qdrant 和 Elasticsearch
4. 每次全量重建（简单直接）

使用方式：
    python -m customer_service.scripts.build_product_index --all
    python -m customer_service.scripts.build_product_index --product-ids 15970 15971 15972
"""
import sys
import asyncio
import argparse
from pathlib import Path
from loguru import logger
from sqlalchemy import select, create_engine
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

# 添加 ecommerce-service-backend 到 Python 路径
commerce_backend_path = Path(__file__).parent.parent.parent.parent / "ecommerce-service-backend"
sys.path.insert(0, str(commerce_backend_path))

from app.models.product import Product, ProductSKU
from app.schemas.internal import ProductKnowledgeCard
from customer_service.config.config import settings
from customer_service.infrastructure.embedding import EmbeddingClient
from customer_service.retrieval.service import QdrantProductRetriever, ElasticsearchProductRetriever
from customer_service.indexing.chunker import ProductChunker


def get_commerce_database_url() -> str:
    """获取 Commerce 数据库 URL（异步版本）"""
    # 从 customer_service settings 获取配置
    # Commerce 数据库连接字符串：mysql+aiomysql://zhutou:618618@localhost:43306/ecommerce_db
    return "mysql+aiomysql://zhutou:618618@localhost:43306/ecommerce_db?charset=utf8mb4"


async def load_products_from_db(product_ids: list[str] | None = None) -> list[dict]:
    """
    从 MySQL 直接加载商品数据

    Args:
        product_ids: 指定商品 ID 列表，None 表示加载所有

    Returns:
        商品字典列表
    """
    logger.info("🔍 从数据库加载商品...")

    # 创建异步引擎
    engine = create_async_engine(get_commerce_database_url(), echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        # 构建查询
        query = select(Product, ProductSKU).join(
            ProductSKU, Product.product_id == ProductSKU.product_id
        )

        if product_ids:
            query = query.where(Product.product_id.in_(product_ids))

        result = await session.execute(query)
        rows = result.all()

        if not rows:
            logger.warning("⚠️  没有找到任何商品")
            return []

        # 组装商品数据（按商品 ID 分组）
        products_dict = {}
        for product, sku in rows:
            if product.product_id not in products_dict:
                products_dict[product.product_id] = {
                    "product_id": product.product_id,
                    "brand": product.brand,
                    "product_display_name": product.product_display_name,
                    "gender": product.gender,
                    "master_category": product.master_category,
                    "sub_category": product.sub_category,
                    "type": product.type,
                    "season": product.season,
                    "year": product.year,
                    "usage": product.usage,
                    "material": product.material,
                    "selling_points": product.selling_points,
                    "size_data": product.size_data,
                    "skus": []
                }

            # 添加 SKU
            products_dict[product.product_id]["skus"].append({
                "sku_id": sku.sku_id,
                "color": sku.color,
                "size_code": sku.size_code,
                "price": float(sku.price) if sku.price else None,
                "stock_status": sku.stock_status
            })

        products = list(products_dict.values())
        logger.info(f"✅ 加载完成，共 {len(products)} 个商品")

    # 关闭引擎
    await engine.dispose()
    return products


async def build_product_index(product_data: dict, embedder: EmbeddingClient,
                              qdrant: QdrantProductRetriever, es: ElasticsearchProductRetriever) -> bool:
    """
    为单个商品构建索引

    Args:
        product_data: 商品原始数据
        embedder: Embedding 客户端
        qdrant: Qdrant 检索器
        es: Elasticsearch 检索器

    Returns:
        是否成功
    """
    product_id = product_data["product_id"]

    try:
        # 1. 转换为 ProductKnowledgeCard
        # 注意：ProductKnowledgeCard 的字段和数据库 Product 字段不完全一致
        # 需要做字段映射和数据转换
        card = ProductKnowledgeCard(
            product_id=product_data["product_id"],
            brand=product_data.get("brand"),
            product_display_name=product_data["product_display_name"],
            category=product_data.get("master_category"),  # 使用 master_category 作为 category
            material=product_data.get("material"),
            selling_points=product_data.get("selling_points") or [],  # 确保是列表
            features=[],  # 从 selling_points 或其他字段提取
            size_summary=None,  # 可以从 size_data 生成摘要
            main_image_url=None,  # 数据库中没有图片字段
            size_chart_url=None
        )

        # 2. 切分成 chunks
        chunker = ProductChunker()
        chunks = chunker.chunk_product(product_id, card.model_dump())
        logger.debug(f"[{product_id}] 生成 {len(chunks)} 个 chunks")

        # 3. 生成向量
        texts = [chunk.text for chunk in chunks]
        embeddings = await embedder.embed_batch(texts)

        # 4. 准备 chunk payloads
        chunk_payloads = []
        for chunk, embedding in zip(chunks, embeddings):
            chunk_payloads.append({
                "chunk_id": chunk.chunk_id,
                "logical_id": chunk.logical_id,
                "product_id": product_id,
                "chunk_type": chunk.chunk_type,
                "text": chunk.text,
                "vector": embedding,  # Qdrant 需要的字段名是 vector
                "metadata": chunk.metadata
            })

        # 5. 批量写入 Qdrant
        await qdrant.upsert_chunks(chunk_payloads)

        # 6. 批量写入 Elasticsearch
        await es.bulk_index_chunks(chunk_payloads)

        logger.info(f"✅ [{product_id}] 索引构建成功 ({len(chunks)} chunks)")
        return True

    except Exception as e:
        logger.error(f"❌ [{product_id}] 索引构建失败: {e}")
        return False


async def main():
    parser = argparse.ArgumentParser(description="构建商品索引（简化版）")
    parser.add_argument("--all", action="store_true", help="构建所有商品索引")
    parser.add_argument("--product-ids", nargs="+", help="指定商品 ID 列表")

    args = parser.parse_args()

    if not args.all and not args.product_ids:
        parser.error("必须指定 --all 或 --product-ids")

    logger.info("=" * 60)
    logger.info("商品索引构建（简化版）")
    logger.info("=" * 60)
    logger.info(f"配置:")
    logger.info(f"  - Embedding: {settings.embedding_service_url}")
    logger.info(f"  - Qdrant: {settings.qdrant_url}")
    logger.info(f"  - Elasticsearch: {settings.elasticsearch_url}")
    logger.info(f"  - 数据源: MySQL 直连")
    logger.info("=" * 60)

    try:
        # 初始化客户端
        embedder = EmbeddingClient(base_url=settings.embedding_service_url)
        qdrant = QdrantProductRetriever(url=settings.qdrant_url)
        es = ElasticsearchProductRetriever(url=settings.elasticsearch_url)

        # 确保 collection 和 index 存在
        logger.info("🔧 初始化索引结构...")
        await qdrant.create_collection()
        logger.info("✅ Qdrant collection 就绪")

        # 从数据库加载商品
        products = await load_products_from_db(args.product_ids if not args.all else None)

        if not products:
            logger.warning("⚠️  没有找到任何商品")
            return 0

        logger.info(f"\n📦 将处理 {len(products)} 个商品\n")

        # 构建索引
        success_count = 0
        failed_count = 0

        for i, product in enumerate(products, 1):
            logger.info(f"[{i}/{len(products)}] 处理商品 {product['product_id']}")

            if await build_product_index(product, embedder, qdrant, es):
                success_count += 1
            else:
                failed_count += 1

        # 输出结果
        logger.info("\n" + "=" * 60)
        logger.info("构建结果汇总")
        logger.info("=" * 60)
        logger.info(f"✅ 成功构建: {success_count}")
        logger.info(f"❌ 失败: {failed_count}")
        logger.info("=" * 60)

        return 1 if failed_count > 0 else 0

    except Exception as e:
        logger.error(f"索引构建失败: {e}")
        logger.exception(e)
        return 1


if __name__ == "__main__":
    exit(asyncio.run(main()))
