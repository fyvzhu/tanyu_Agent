"""
问题#6 测试 - 第一层：纯 Schema 验证（无需 Docker）

验证 ProductCard 和 PromotionCard Schema 定义是否正确拒绝无效数据
"""
import sys
from pathlib import Path

# 添加后端路径
backend_path = Path(__file__).parent.parent / "customer-service-backend"
sys.path.insert(0, str(backend_path))

from customer_service.schemas.chat import ProductCard, PromotionCard
from pydantic import ValidationError


def test_valid_product_card():
    """测试：完整的商品卡片应该通过验证"""
    print("\n📝 测试1：完整商品卡片验证")
    try:
        card = ProductCard(
            type="product_card",
            product_id="15970",
            title="时尚连衣裙",
            brand="优雅女装",
            main_image_url="/static/main-images/15970.jpg",
            min_price=199.0,
            max_price=299.0,
            selected_sku_id="15970-001",
            selected_sku_price=249.0,
            stock_status="in_stock"
        )
        print(f"✅ 通过：{card.product_id} - {card.title}")
        print(f"   价格区间: ¥{card.min_price} - ¥{card.max_price}")
        print(f"   库存状态: {card.stock_status}")
        return True
    except ValidationError as e:
        print(f"❌ 失败（不应该）: {e}")
        return False


def test_missing_product_id():
    """测试：缺少 product_id 应该失败"""
    print("\n📝 测试2：缺少 product_id")
    try:
        card = ProductCard(
            type="product_card",
            title="时尚连衣裙"
        )
        print(f"❌ 失败：卡片通过验证（不应该）")
        return False
    except ValidationError as e:
        print(f"✅ 通过：正确拒绝缺少 product_id 的卡片")
        print(f"   错误: {e.error_count()} 个字段错误")
        return True


def test_missing_title():
    """测试：缺少 title 应该失败"""
    print("\n📝 测试3：缺少 title")
    try:
        card = ProductCard(
            type="product_card",
            product_id="15970"
        )
        print(f"❌ 失败：卡片通过验证（不应该）")
        return False
    except ValidationError as e:
        print(f"✅ 通过：正确拒绝缺少 title 的卡片")
        return True


def test_wrong_type():
    """测试：type 字段错误应该失败"""
    print("\n📝 测试4：type 字段错误")
    try:
        card = ProductCard(
            type="wrong_type",  # 应该是 "product_card"
            product_id="15970",
            title="测试商品"
        )
        print(f"❌ 失败：卡片通过验证（不应该）")
        return False
    except ValidationError as e:
        print(f"✅ 通过：正确拒绝 type 错误的卡片")
        return True


def test_empty_shell_detection():
    """测试：检测空壳对象模式"""
    print("\n📝 测试5：检测空壳对象")
    
    # 旧 Schema 的空壳模式（已废弃）
    empty_shell = {
        "type": "product_card",
        "product": None,
        "sku": None,
        "assets": None,
        "data": {}
    }
    
    try:
        # 新 Schema 应该拒绝这种结构（缺少必需字段）
        card = ProductCard(**empty_shell)
        print(f"❌ 失败：空壳对象通过验证（不应该）")
        return False
    except ValidationError as e:
        print(f"✅ 通过：新 Schema 正确拒绝旧的空壳对象")
        print(f"   缺少字段: product_id, title")
        return True


def test_promotion_card():
    """测试：促销卡片验证"""
    print("\n📝 测试6：促销卡片验证")
    try:
        card = PromotionCard(
            type="promotion",
            promotion_id="PROMO123",
            title="双11大促",
            promotion_type="percentage_discount",
            description="全场8折优惠",
            discount_rate=0.2,
            applicable=True
        )
        print(f"✅ 通过：{card.promotion_id} - {card.title}")
        print(f"   折扣率: {card.discount_rate * 100}%")
        return True
    except ValidationError as e:
        print(f"❌ 失败（不应该）: {e}")
        return False


def main():
    print("=" * 60)
    print("问题#6 测试 - 第一层：Schema 验证")
    print("=" * 60)
    
    results = {
        "test_1": test_valid_product_card(),
        "test_2": test_missing_product_id(),
        "test_3": test_missing_title(),
        "test_4": test_wrong_type(),
        "test_5": test_empty_shell_detection(),
        "test_6": test_promotion_card(),
    }
    
    print("\n" + "=" * 60)
    print("测试总结")
    print("=" * 60)
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    for test, result in results.items():
        status = "✅ 通过" if result else "❌ 失败"
        print(f"{test}: {status}")
    
    print(f"\n通过: {passed}/{total}")
    
    if passed == total:
        print("\n✅ 所有 Schema 验证测试通过！")
        print("   ProductCard 和 PromotionCard 定义正确")
        print("   下一步：需要启动服务进行端到端测试")
        return 0
    else:
        print("\n❌ 部分测试失败，Schema 定义有问题")
        return 1


if __name__ == "__main__":
    exit(main())
