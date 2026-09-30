"""
Contract 测试 - 验证 Commerce API 响应符合公开 Schema

测试目标：
1. 商品列表返回 category、main_image_url、min_price、max_price、has_stock
2. 商品详情返回统一的 category 和 main_image_url
3. SKU 列表使用 in_stock/out_of_stock
4. 促销信息包含完整字段和标准枚举
"""
import pytest
from httpx import AsyncClient
from decimal import Decimal


@pytest.mark.asyncio
async def test_product_list_contract(async_client: AsyncClient):
    """测试商品列表契约"""
    response = await async_client.get("/api/v1/catalog/products?page=1&page_size=5")
    
    assert response.status_code == 200
    data = response.json()
    
    assert "success" in data
    assert data["success"] is True
    assert "data" in data
    
    items = data["data"]["items"]
    assert len(items) > 0
    
    # 验证第一个商品的字段
    product = items[0]
    assert "product_id" in product
    assert "product_display_name" in product
    assert "category" in product  # 统一分类字段
    assert "main_image_url" in product  # 主图 URL
    assert "min_price" in product  # 最低价格
    assert "max_price" in product  # 最高价格
    assert "has_stock" in product  # 库存状态
    
    # 验证类型
    assert isinstance(product["category"], str)
    assert product["main_image_url"].startswith("/static/main-images/")
    assert isinstance(product["min_price"], (int, float, str))
    assert isinstance(product["max_price"], (int, float, str))
    assert isinstance(product["has_stock"], bool)


@pytest.mark.asyncio
async def test_product_detail_contract(async_client: AsyncClient):
    """测试商品详情契约"""
    # 使用已知存在的商品ID
    product_id = "15970"
    response = await async_client.get(f"/api/v1/catalog/products/{product_id}")
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["success"] is True
    product = data["data"]
    
    # 验证必需字段
    assert product["product_id"] == product_id
    assert "product_display_name" in product
    assert "category" in product  # 统一分类
    assert "main_image_url" in product  # 主图URL
    
    # 验证主图URL格式
    assert product["main_image_url"] == f"/static/main-images/{product_id}.jpg"


@pytest.mark.asyncio
async def test_sku_list_contract(async_client: AsyncClient):
    """测试SKU列表契约 - 验证库存状态使用新枚举"""
    product_id = "15970"
    response = await async_client.get(f"/api/v1/catalog/products/{product_id}/skus")
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["success"] is True
    skus = data["data"]["items"]
    assert len(skus) > 0
    
    # 验证SKU字段
    sku = skus[0]
    assert "sku_id" in sku
    assert "product_id" in sku
    assert "price" in sku
    assert "stock_status" in sku
    
    # 验证库存状态使用新枚举值
    assert sku["stock_status"] in ["in_stock", "out_of_stock"]
    
    # 验证所有SKU都使用标准枚举
    for sku in skus:
        assert sku["stock_status"] in ["in_stock", "out_of_stock"], \
            f"SKU {sku['sku_id']} has invalid stock_status: {sku['stock_status']}"


@pytest.mark.asyncio
async def test_promotion_contract(async_client: AsyncClient, auth_headers: dict):
    """测试促销信息契约 - 验证促销类型和字段完整性"""
    # 找一个有促销的商品
    product_id = "54924"  # PROMO20260001 对应的商品
    
    response = await async_client.get(
        f"/api/v1/catalog/products/{product_id}/promotions",
        headers=auth_headers
    )
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["success"] is True
    promotions = data["data"]["items"]
    
    if len(promotions) > 0:
        promo = promotions[0]
        
        # 验证必需字段
        assert "promotion_id" in promo
        assert "title" in promo  # 不再是 promotion_name
        assert "promotion_type" in promo
        assert "start_at" in promo
        assert "end_at" in promo
        assert "applicable" in promo
        
        # 验证促销类型使用新枚举
        valid_types = ["percentage_discount", "fixed_discount", "threshold_discount", "member_price"]
        assert promo["promotion_type"] in valid_types, \
            f"Invalid promotion_type: {promo['promotion_type']}"


@pytest.mark.asyncio
async def test_main_image_accessibility(async_client: AsyncClient):
    """测试主图URL可访问性"""
    product_id = "15970"
    
    # 测试主图
    response = await async_client.get(f"/static/main-images/{product_id}.jpg")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/")
    
    # 测试尺码图
    response = await async_client.get(f"/static/size-images/{product_id}.jpg")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/")
