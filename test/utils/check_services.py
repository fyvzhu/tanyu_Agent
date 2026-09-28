"""
检查 Qdrant 和 Elasticsearch 服务状态
"""
import asyncio
import httpx

async def check_services():
    print("🔍 检查必需服务...")
    
    # 检查 Qdrant
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get('http://localhost:6333/collections')
            if resp.status_code == 200:
                print("✅ Qdrant 运行正常 (localhost:6333)")
                collections = resp.json()
                print(f"   已有 collections: {collections.get('result', {}).get('collections', [])}")
            else:
                print(f"⚠️ Qdrant 响应异常: {resp.status_code}")
    except Exception as e:
        print(f"❌ Qdrant 不可用: {e}")
        print("   请启动 Qdrant: docker run -p 6333:6333 qdrant/qdrant")
    
    # 检查 Elasticsearch
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get('http://localhost:9200')
            if resp.status_code == 200:
                print("✅ Elasticsearch 运行正常 (localhost:9200)")
                info = resp.json()
                print(f"   版本: {info.get('version', {}).get('number', 'unknown')}")
            else:
                print(f"⚠️ Elasticsearch 响应异常: {resp.status_code}")
    except Exception as e:
        print(f"❌ Elasticsearch 不可用: {e}")
        print("   请启动 Elasticsearch")
    
    # 检查 Commerce Backend
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get('http://127.0.0.1:8001/api/v1/catalog/products?page=1&page_size=1')
            if resp.status_code == 200:
                print("✅ Commerce Backend 运行正常 (port 8001)")
                data = resp.json()
                print(f"   商品总数: {data.get('data', {}).get('total', 0)}")
            else:
                print(f"⚠️ Commerce Backend 响应异常: {resp.status_code}")
    except Exception as e:
        print(f"❌ Commerce Backend 不可用: {e}")

if __name__ == "__main__":
    asyncio.run(check_services())
