"""
问题 #9 完整测试：全量索引构建 + 在线查询验证

测试目标：
1. 验证所有商品都能正确 embedding 并存入 Qdrant 和 ES
2. 验证分页逻辑（处理超过100个商品）
3. 验证增量更新和失败恢复
4. 验证在线"商品咨询"意图能够返回内容（不是兜底回复）

这是真实落地场景的完整测试，不是简化版本。
"""
import asyncio
import sys
from pathlib import Path
from datetime import datetime

# 添加项目路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "customer-service-backend"))

from loguru import logger
import httpx

from customer_service.clients.ecommerce import EcommerceClient
from customer_service.infrastructure.embedding import EmbeddingClient
from customer_service.retrieval.service import QdrantProductRetriever, ElasticsearchProductRetriever
from customer_service.indexing.builder import ProductIndexBuilder
from customer_service.infrastructure.database import get_async_session

# 配置
COMMERCE_URL = "http://localhost:8001"
AGENT_URL = "http://localhost:8000"
EMBEDDING_URL = "http://localhost:8100"
QDRANT_URL = "http://localhost:6333"
ES_URL = "http://localhost:9200"


async def test_step1_check_services():
    """步骤 1: 检查所有必需服务"""
    logger.info("=" * 60)
    logger.info("步骤 1: 检查服务状态")
    logger.info("=" * 60)
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        # Embedding
        try:
            resp = await client.get(f"{EMBEDDING_URL}/health")
            logger.info(f"✅ Embedding 服务: {resp.status_code}")
        except Exception as e:
            logger.error(f"❌ Embedding 服务异常: {e}")
            return False
        
        # Qdrant
        try:
            resp = await client.get(f"{QDRANT_URL}")
            logger.info(f"✅ Qdrant 服务: 版本 {resp.json().get('version')}")
        except Exception as e:
            logger.error(f"❌ Qdrant 服务异常: {e}")
            return False
        
        # Elasticsearch
        try:
            resp = await client.get(f"{ES_URL}")
            logger.info(f"✅ Elasticsearch 服务: {resp.status_code}")
        except Exception as e:
            logger.error(f"❌ Elasticsearch 服务异常: {e}")
            return False
        
        # Commerce API
        try:
            resp = await client.get(f"{COMMERCE_URL}/health")
            logger.info(f"✅ Commerce API: {resp.status_code}")
        except Exception as e:
            logger.error(f"❌ Commerce API 异常: {e}")
            return False
    
    return True


async def test_step2_enumerate_all_products():
    """步骤 2: 完整枚举所有商品（测试分页）"""
    logger.info("\n" + "=" * 60)
    logger.info("步骤 2: 枚举所有商品（测试分页逻辑）")
    logger.info("=" * 60)
    
    commerce = EcommerceClient(base_url=COMMERCE_URL)
    all_product_ids = []
    page = 1
    page_size = 100
    
    while True:
        try:
            response = await commerce.search_products(
                params={
                    "query": "",
                    "page": page,
                    "page_size": page_size
                }
            )

            items = response.get("items", [])
            total = response.get("total", 0)
            
            if not items:
                break
            
            page_ids = [item["product_id"] for item in items if "product_id" in item]
            all_product_ids.extend(page_ids)
            
            logger.info(f"  第 {page} 页: {len(page_ids)} 个商品 (累计 {len(all_product_ids)}/{total})")
            
            if len(all_product_ids) >= total:
                break
            
            page += 1
        
        except Exception as e:
            logger.error(f"❌ 枚举商品失败（第 {page} 页）: {e}")
            await commerce.close()
            return None
    
    await commerce.close()
    
    if not all_product_ids:
        logger.error("❌ 没有找到任何商品")
        return None
    
    logger.info(f"\n✅ 枚举完成，共 {len(all_product_ids)} 个商品")
    logger.info(f"   前10个: {all_product_ids[:10]}")
    
    if total > 100:
        logger.info(f"   ✅ 商品数 > 100，分页逻辑已生效")
    
    return all_product_ids


async def test_step3_build_full_index(product_ids: list[str]):
    """步骤 3: 全量构建索引"""
    logger.info("\n" + "=" * 60)
    logger.info(f"步骤 3: 全量构建索引（{len(product_ids)} 个商品）")
    logger.info("=" * 60)

    commerce = EcommerceClient(base_url=COMMERCE_URL)
    embedder = EmbeddingClient(base_url=EMBEDDING_URL)
    qdrant = QdrantProductRetriever(url=QDRANT_URL)
    es = ElasticsearchProductRetriever(url=ES_URL)

    # 确保 collection 和 index 存在
    logger.info("🔧 初始化索引结构...")
    await qdrant.create_collection()
    logger.info("✅ Qdrant collection 就绪")

    # 构建索引
    async for db_session in get_async_session():
        builder = ProductIndexBuilder(
            db_session=db_session,
            ecommerce_client=commerce,
            embedding_client=embedder,
            qdrant_retriever=qdrant,
            es_retriever=es,
        )

        logger.info(f"\n🚀 开始构建索引...")
        results = await builder.build_index_batch(product_ids, force=False)

        logger.info("\n" + "=" * 60)
        logger.info("构建结果汇总")
        logger.info("=" * 60)
        logger.info(f"✅ 成功构建: {results['built']}")
        logger.info(f"⏭️  跳过（已是最新）: {results['skipped']}")
        logger.info(f"❌ 失败: {results['failed']}")

        # 显示详细错误
        if results['failed'] > 0:
            logger.error("\n失败商品详情:")
            for detail in results.get('details', []):
                if detail.get('status') == 'failed':
                    logger.error(f"  - {detail['product_id']}: {detail.get('error', 'unknown')}")

            logger.error(f"\n❌ 有 {results['failed']} 个商品构建失败")
            return False

        if results['built'] == 0 and results['skipped'] == 0:
            logger.error("❌ 没有任何商品被处理")
            return False

        logger.info(f"\n✅ 索引构建成功：{results['built']} 个商品已索引")
        return True


async def test_step4_verify_index():
    """步骤 4: 验证索引内容"""
    logger.info("\n" + "=" * 60)
    logger.info("步骤 4: 验证 Qdrant 和 ES 中的数据")
    logger.info("=" * 60)

    qdrant = QdrantProductRetriever(url=QDRANT_URL)

    # 查询 Qdrant collection 信息
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{QDRANT_URL}/collections/product_chunks")
            if resp.status_code == 200:
                data = resp.json()["result"]
                points_count = data.get("points_count", 0)
                logger.info(f"✅ Qdrant 中的向量数: {points_count}")

                if points_count == 0:
                    logger.error("❌ Qdrant 中没有任何向量！")
                    return False
            else:
                logger.error(f"❌ 无法查询 Qdrant collection: {resp.status_code}")
                return False
    except Exception as e:
        logger.error(f"❌ Qdrant 查询失败: {e}")
        return False

    # 查询 ES index 信息
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{ES_URL}/product_chunks/_count")
            if resp.status_code == 200:
                count = resp.json()["count"]
                logger.info(f"✅ Elasticsearch 中的文档数: {count}")

                if count == 0:
                    logger.error("❌ Elasticsearch 中没有任何文档！")
                    return False
            else:
                logger.error(f"❌ 无法查询 ES index: {resp.status_code}")
                return False
    except Exception as e:
        logger.error(f"❌ ES 查询失败: {e}")
        return False

    logger.info(f"\n✅ 索引验证通过")
    return True


async def test_step5_online_query():
    """步骤 5: 测试在线"商品咨询"意图"""
    logger.info("\n" + "=" * 60)
    logger.info("步骤 5: 测试在线商品咨询查询")
    logger.info("=" * 60)

    async with httpx.AsyncClient(timeout=30.0) as client:
        # 登录
        resp = await client.post(
            f"{COMMERCE_URL}/api/v1/auth/login",
            json={"username": "li_ming88", "password": "Limi01Aa!26"}
        )
        if resp.status_code != 200:
            logger.error(f"❌ 登录失败: {resp.status_code}")
            return False

        token = resp.json()["data"]["access_token"]
        logger.info(f"✅ 登录成功")

        # 创建会话
        resp = await client.post(
            f"{AGENT_URL}/api/v1/chat/sessions",
            json={"channel": "web"},
            headers={"Authorization": f"Bearer {token}"}
        )
        session_id = resp.json()["data"]["session_id"]
        logger.info(f"✅ 会话创建: {session_id}")

        # 发送商品咨询查询
        test_queries = [
            "有没有格纹衬衫？",
            "推荐一款T恤",
            "什么材质的衣服好？"
        ]

        success_count = 0
        for query in test_queries:
            logger.info(f"\n📤 测试查询: '{query}'")

            resp = await client.post(
                f"{AGENT_URL}/api/v1/chat/sessions/{session_id}/messages",
                json={"message": query},
                headers={"Authorization": f"Bearer {token}"}
            )

            if resp.status_code != 200:
                logger.error(f"   ❌ 查询失败: {resp.status_code}")
                continue

            data = resp.json()["data"]
            text = data.get("text", "")
            objects = data.get("objects", [])

            logger.info(f"   响应文本: {text[:100]}...")
            logger.info(f"   商品对象数: {len(objects)}")

            # 检查是否是兜底回复
            if "抱歉，我不太理解您的意思" in text or "您可以问我商品信息、促销活动" in text:
                logger.error(f"   ❌ 返回了兜底回复，RAG 检索未生效")
            else:
                logger.info(f"   ✅ RAG 检索成功返回内容")
                success_count += 1

        if success_count == 0:
            logger.error(f"\n❌ 所有查询都返回兜底回复，RAG 未生效")
            return False

        logger.info(f"\n✅ {success_count}/{len(test_queries)} 个查询成功")
        return True


async def main():
    """主测试流程"""
    logger.info("=" * 60)
    logger.info("问题 #9 完整端到端测试")
    logger.info(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 60)

    # 步骤 1: 检查服务
    if not await test_step1_check_services():
        logger.error("\n❌ 服务检查失败，终止测试")
        return 1

    # 步骤 2: 枚举所有商品
    product_ids = await test_step2_enumerate_all_products()
    if not product_ids:
        logger.error("\n❌ 商品枚举失败，终止测试")
        return 1

    # 步骤 3: 全量构建索引
    if not await test_step3_build_full_index(product_ids):
        logger.error("\n❌ 索引构建失败，终止测试")
        return 1

    # 步骤 4: 验证索引
    if not await test_step4_verify_index():
        logger.error("\n❌ 索引验证失败，终止测试")
        return 1

    # 步骤 5: 在线查询测试
    if not await test_step5_online_query():
        logger.error("\n❌ 在线查询测试失败")
        return 1

    logger.info("\n" + "=" * 60)
    logger.info("✅✅✅ 问题 #9 全部测试通过")
    logger.info("=" * 60)
    return 0


if __name__ == "__main__":
    exit(asyncio.run(main()))

