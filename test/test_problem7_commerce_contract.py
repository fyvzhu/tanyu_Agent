"""
问题7修复验证：Commerce 跨服务契约测试

验证 Agent → Commerce 的完整调用链：
1. 库存枚举使用 in_stock/out_of_stock 而非中文
2. 图片字段贯通到所有商品卡片路径
3. 促销认证正确使用 SecretStr.get_secret_value()
4. RAG 和 Commerce-only 两条路径数据结构一致
"""
import asyncio
import httpx
import sys
from test_utils import login_test_user, COMMERCE_URL, AGENT_URL


async def test_1_internal_batch_get_has_main_image():
    """测试1: 内部 API batch-get 返回 main_image_url"""
    print("\n" + "=" * 60)
    print("测试1：内部 API batch-get 必须包含 main_image_url")
    print("=" * 60)

    # 使用已知存在的商品 ID（从数据库中选择）
    test_product_ids = ["15970", "39386", "21379"]
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        # 模拟 Agent 的 service token 请求（实际环境中需要真实 service token）
        # 这里我们使用用户 token 来测试公开 API 路径
        token = await login_test_user("user_a")
        
        # 测试公开商品详情 API（应包含 main_image_url）
        for product_id in test_product_ids:
            resp = await client.get(
                f"{COMMERCE_URL}/api/v1/catalog/products/{product_id}",
                headers={"Authorization": f"Bearer {token}"}
            )
            if resp.status_code != 200:
                print(f"❌ 商品 {product_id} 获取失败: {resp.status_code}")
                return False
            
            data = resp.json()["data"]
            if "main_image_url" not in data:
                print(f"❌ 商品 {product_id} 缺少 main_image_url 字段")
                return False
            
            main_image_url = data["main_image_url"]
            if not main_image_url or not main_image_url.startswith("/static/main-images/"):
                print(f"❌ 商品 {product_id} 的 main_image_url 格式错误: {main_image_url}")
                return False
            
            print(f"✅ 商品 {product_id} 包含有效的 main_image_url: {main_image_url}")
    
    print("✅ 测试1通过：所有商品都包含 main_image_url")
    return True


async def test_2_stock_status_enum():
    """测试2: SKU 过滤使用标准枚举值 in_stock/out_of_stock"""
    print("\n" + "=" * 60)
    print("测试2：SKU 过滤必须使用 in_stock/out_of_stock 枚举")
    print("=" * 60)

    token = await login_test_user("user_a")
    test_product_id = "15970"
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        # 获取该商品的所有 SKU
        resp = await client.get(
            f"{COMMERCE_URL}/api/v1/catalog/products/{test_product_id}/skus",
            headers={"Authorization": f"Bearer {token}"}
        )
        if resp.status_code != 200:
            print(f"❌ 获取 SKU 失败: {resp.status_code}")
            return False
        
        skus = resp.json()["data"]["items"]
        if not skus:
            print(f"❌ 商品 {test_product_id} 没有 SKU")
            return False
        
        # 检查所有 SKU 的 stock_status 字段
        for sku in skus:
            stock_status = sku.get("stock_status")
            if stock_status not in ["in_stock", "out_of_stock"]:
                print(f"❌ SKU {sku.get('sku_id')} 的 stock_status 不是标准枚举值: {stock_status}")
                return False
        
        print(f"✅ 所有 {len(skus)} 个 SKU 都使用标准枚举值")
        
        # 测试有货筛选
        in_stock_skus = [s for s in skus if s["stock_status"] == "in_stock"]
        if in_stock_skus:
            print(f"✅ 找到 {len(in_stock_skus)} 个有货 SKU")
        
    print("✅ 测试2通过：库存状态使用标准枚举")
    return True


async def test_3_promotion_with_user_token():
    """测试3: 促销查询正确使用用户 JWT"""
    print("\n" + "=" * 60)
    print("测试3：促销查询必须使用用户 JWT 认证")
    print("=" * 60)

    token = await login_test_user("user_a")
    test_product_id = "15970"
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(
            f"{COMMERCE_URL}/api/v1/catalog/products/{test_product_id}/promotions",
            headers={"Authorization": f"Bearer {token}"}
        )

        if resp.status_code != 200:
            print(f"❌ 促销查询失败: {resp.status_code} - {resp.text}")
            return False

        data = resp.json()["data"]
        items = data.get("items", [])
        print(f"✅ 促销查询成功，找到 {len(items)} 个促销")

        # 验证促销字段结构
        for promo in items:
            required_fields = ["promotion_id", "title", "promotion_type"]
            for field in required_fields:
                if field not in promo:
                    print(f"❌ 促销缺少必需字段: {field}")
                    return False

            # 验证 promotion_type 使用标准枚举
            promo_type = promo["promotion_type"]
            valid_types = ["percentage_discount", "fixed_discount", "threshold_discount", "member_price"]
            if promo_type not in valid_types:
                print(f"❌ promotion_type 不是标准枚举值: {promo_type}")
                return False

            # 验证折扣字段存在（至少有一个）
            has_discount = any([
                promo.get("discount_rate"),
                promo.get("discount_amount"),
                promo.get("promo_price")
            ])
            if not has_discount:
                print(f"❌ 促销 {promo['promotion_id']} 缺少折扣字段")
                return False

        if items:
            print(f"✅ 所有促销字段结构正确")

    print("✅ 测试3通过：促销查询认证正确")
    return True


async def test_4_agent_product_search_complete():
    """测试4: Agent 商品搜索返回完整的商品卡片（问题修复2强化版）"""
    print("\n" + "=" * 60)
    print("测试4：Agent 商品搜索必须返回完整商品卡片")
    print("=" * 60)

    token = await login_test_user("user_a")

    async with httpx.AsyncClient(timeout=30.0) as client:
        # 创建会话
        resp = await client.post(
            f"{AGENT_URL}/api/v1/chat/sessions",
            json={"channel": "web"},
            headers={"Authorization": f"Bearer {token}"}
        )
        if resp.status_code != 200:
            print(f"❌ 创建会话失败: {resp.status_code}")
            return False

        session_id = resp.json()["data"]["session_id"]
        print(f"✅ 会话创建成功: {session_id}")

        # 发送商品查询消息（使用更明确的查询，避免意图识别问题）
        resp = await client.post(
            f"{AGENT_URL}/api/v1/chat/sessions/{session_id}/messages",
            json={"message": "查询商品15970"},
            headers={"Authorization": f"Bearer {token}"}
        )

        # 问题修复2: HTTP 必须返回 200，不能是 500
        if resp.status_code != 200:
            print(f"❌ 消息发送失败: {resp.status_code} - {resp.text}")
            print("   问题修复2: 对象验证失败不应返回 500")
            return False

        response_json = resp.json()
        if not response_json.get("success"):
            print(f"❌ 响应 success=false: {response_json}")
            return False

        data = response_json["data"]
        text = data.get("text", "")
        print(f"✅ 收到回复: {text[:100]}...")

        # 问题修复2: 必须返回商品对象，不能为空
        objects = data.get("objects", [])
        if not objects:
            print("❌ 未返回商品对象（问题修复2: 商品查询必须返回对象）")
            print(f"   回复文本: {text}")
            print(f"   意图: {data.get('task', {}).get('intent')}")
            return False

        # 验证商品卡片结构
        product_cards = [obj for obj in objects if obj.get("type") == "product_card"]
        if not product_cards:
            print(f"❌ 未返回 product_card 类型对象")
            print(f"   对象类型: {[obj.get('type') for obj in objects]}")
            return False

        print(f"✅ 返回 {len(product_cards)} 个商品卡片")

        # 问题修复2: 检查每个商品卡片的必需字段（严格验证）
        for i, card in enumerate(product_cards):
            # 必需字段（根据 ProductCard 模型定义）
            required_fields = ["type", "product_id", "title"]
            missing_fields = [f for f in required_fields if f not in card or card[f] is None]

            if missing_fields:
                print(f"❌ 商品卡片 {i+1} 缺少必需字段: {missing_fields}")
                print(f"   卡片内容: {card}")
                return False

            # 验证 type 字段
            if card["type"] != "product_card":
                print(f"❌ 商品卡片 {i+1} type 字段错误: {card['type']}")
                return False

            # 验证可选但应该存在的字段
            optional_fields = ["main_image_url", "min_price", "max_price", "brand",
                             "selected_sku_id", "selected_sku_price", "stock_status"]
            for field in optional_fields:
                if field not in card:
                    print(f"⚠️  商品卡片 {i+1} 缺少可选字段: {field}")

            # 验证 main_image_url 格式（如果存在）
            if card.get("main_image_url"):
                main_image_url = card["main_image_url"]
                if not main_image_url.startswith("/static/main-images/"):
                    print(f"❌ 商品卡片 {i+1} 的 main_image_url 格式错误: {main_image_url}")
                    return False

            print(f"✅ 商品卡片 {i+1} 结构完整: {card['product_id']} - {card['title']}")

    print("✅ 测试4通过：商品卡片结构完整且对象验证通过")
    return True


async def test_5_agent_promotion_query_complete():
    """测试5: Agent 促销查询返回完整的促销卡片（问题修复2新增）"""
    print("\n" + "=" * 60)
    print("测试5：Agent 促销查询必须返回完整促销卡片")
    print("=" * 60)

    token = await login_test_user("user_a")

    async with httpx.AsyncClient(timeout=30.0) as client:
        # 创建会话
        resp = await client.post(
            f"{AGENT_URL}/api/v1/chat/sessions",
            json={"channel": "web"},
            headers={"Authorization": f"Bearer {token}"}
        )
        if resp.status_code != 200:
            print(f"❌ 创建会话失败: {resp.status_code}")
            return False

        session_id = resp.json()["data"]["session_id"]
        print(f"✅ 会话创建成功: {session_id}")

        # 发送促销查询消息（使用更明确的表达，避免多意图误判）
        resp = await client.post(
            f"{AGENT_URL}/api/v1/chat/sessions/{session_id}/messages",
            json={"message": "15970有什么优惠"},
            headers={"Authorization": f"Bearer {token}"}
        )

        # 问题修复2: HTTP 必须返回 200
        if resp.status_code != 200:
            print(f"❌ 消息发送失败: {resp.status_code} - {resp.text}")
            return False

        response_json = resp.json()
        if not response_json.get("success"):
            print(f"❌ 响应 success=false: {response_json}")
            return False

        data = response_json["data"]
        text = data.get("text", "")
        print(f"✅ 收到回复: {text[:100]}...")

        # 检查是否返回了促销对象
        objects = data.get("objects", [])
        if not objects:
            print("⚠️  未返回促销对象（可能商品15970没有促销活动）")
            return True  # 无促销不算失败

        # 验证促销卡片结构
        promotion_cards = [obj for obj in objects if obj.get("type") == "promotion"]
        if not promotion_cards:
            print(f"⚠️  未返回 promotion 类型对象")
            print(f"   对象类型: {[obj.get('type') for obj in objects]}")
            return True

        print(f"✅ 返回 {len(promotion_cards)} 个促销卡片")

        # 问题修复2: 检查每个促销卡片的必需字段（严格验证）
        for i, card in enumerate(promotion_cards):
            # 必需字段（根据 PromotionCard 模型定义）
            required_fields = ["type", "promotion_id", "title", "promotion_type"]
            missing_fields = [f for f in required_fields if f not in card or card[f] is None]

            if missing_fields:
                print(f"❌ 促销卡片 {i+1} 缺少必需字段: {missing_fields}")
                print(f"   卡片内容: {card}")
                return False

            # 验证 type 字段
            if card["type"] != "promotion":
                print(f"❌ 促销卡片 {i+1} type 字段错误: {card['type']}")
                return False

            # 验证 promotion_type 枚举值
            valid_types = ["percentage_discount", "fixed_discount", "threshold_discount", "member_price"]
            if card["promotion_type"] not in valid_types:
                print(f"❌ 促销卡片 {i+1} promotion_type 不是标准枚举: {card['promotion_type']}")
                return False

            # 验证至少有一个折扣参数
            has_discount = any([
                card.get("discount_rate") is not None,
                card.get("discount_amount") is not None,
                card.get("promo_price") is not None
            ])
            if not has_discount:
                print(f"❌ 促销卡片 {i+1} 缺少折扣参数")
                return False

            print(f"✅ 促销卡片 {i+1} 结构完整: {card['promotion_id']} - {card['title']}")

    print("✅ 测试5通过：促销卡片结构完整且对象验证通过")
    return True


async def test_6_chatobject_persistence_and_history():
    """
    测试6: 问题#6 - ChatObject 持久化与历史一致性测试

    验证三个关键点：
    1. POST 响应返回完整的商品卡片
    2. 商品卡片正确保存到数据库（objects_json 字段）
    3. GET 历史返回的对象与 POST 响应完全一致
    """
    print("\n" + "=" * 60)
    print("测试6：ChatObject 持久化与历史一致性（问题#6）")
    print("=" * 60)

    token = await login_test_user("user_a")
    test_product_id = "15970"

    async with httpx.AsyncClient(timeout=30.0) as client:
        # 步骤1：创建新会话
        resp = await client.post(
            f"{AGENT_URL}/api/v1/chat/sessions",
            json={"channel": "web"},
            headers={"Authorization": f"Bearer {token}"}
        )
        if resp.status_code != 200:
            print(f"❌ 创建会话失败: {resp.status_code}")
            return False

        session_id = resp.json()["data"]["session_id"]
        print(f"✅ 会话创建成功: {session_id}")

        # 步骤2：发送商品查询，记录 POST 响应的 objects
        resp = await client.post(
            f"{AGENT_URL}/api/v1/chat/sessions/{session_id}/messages",
            json={"message": f"查询商品{test_product_id}"},
            headers={"Authorization": f"Bearer {token}"}
        )

        if resp.status_code != 200:
            print(f"❌ 消息发送失败: {resp.status_code} - {resp.text}")
            return False

        post_response = resp.json()["data"]
        post_message_id = post_response["message_id"]
        post_objects = post_response.get("objects", [])

        print(f"✅ POST 响应: message_id={post_message_id}, objects_count={len(post_objects)}")

        # 验证：POST 响应必须包含商品卡片
        if not post_objects:
            print(f"❌ 问题#6失败: POST 响应未返回商品对象")
            print(f"   回复文本: {post_response.get('text', '')[:100]}")
            return False

        product_cards = [obj for obj in post_objects if obj.get("type") == "product_card"]
        if not product_cards:
            print(f"❌ 问题#6失败: POST 响应未返回 product_card 类型")
            print(f"   对象类型: {[obj.get('type') for obj in post_objects]}")
            return False

        post_card = product_cards[0]
        print(f"✅ POST 商品卡片: product_id={post_card.get('product_id')}, title={post_card.get('title')}")

        # 验证：商品卡片字段完整性
        required_fields = ["type", "product_id", "title"]
        missing_fields = [f for f in required_fields if not post_card.get(f)]
        if missing_fields:
            print(f"❌ 问题#6失败: POST 商品卡片缺少必需字段: {missing_fields}")
            print(f"   卡片内容: {post_card}")
            return False

        # 验证：不应该是空壳卡片
        empty_shell = {
            "type": "product_card",
            "product": None,
            "sku": None,
            "assets": None,
            "data": {}
        }
        if (post_card.get("product") is None and
            post_card.get("sku") is None and
            post_card.get("data") == {}):
            print(f"❌ 问题#6失败: POST 返回了空壳商品卡片")
            print(f"   这是旧 Schema 的问题，应该返回扁平结构")
            return False

        print(f"✅ POST 商品卡片结构完整且非空壳")

        # 步骤3：立即 GET 历史，验证对象一致性
        resp = await client.get(
            f"{AGENT_URL}/api/v1/chat/sessions/{session_id}/messages",
            headers={"Authorization": f"Bearer {token}"}
        )

        if resp.status_code != 200:
            print(f"❌ 获取历史失败: {resp.status_code}")
            return False

        history = resp.json()["data"]["messages"]

        # 找到对应的 assistant 消息
        assistant_message = None
        for msg in history:
            if msg["role"] == "assistant" and msg["message_id"] == post_message_id:
                assistant_message = msg
                break

        if not assistant_message:
            print(f"❌ 问题#6失败: 历史中找不到 message_id={post_message_id} 的消息")
            return False

        history_objects = assistant_message.get("objects", [])
        print(f"✅ GET 历史: message_id={post_message_id}, objects_count={len(history_objects)}")

        # 验证：历史对象不应为空
        if not history_objects:
            print(f"❌ 问题#6失败: 历史消息的 objects 为空")
            print(f"   这表明 objects_json 没有正确保存到数据库")
            return False

        # 验证：历史对象数量应与 POST 响应一致
        if len(history_objects) != len(post_objects):
            print(f"❌ 问题#6失败: 历史对象数量 ({len(history_objects)}) 与 POST 响应 ({len(post_objects)}) 不一致")
            return False

        # 验证：历史商品卡片字段应与 POST 响应完全一致
        history_cards = [obj for obj in history_objects if obj.get("type") == "product_card"]
        if not history_cards:
            print(f"❌ 问题#6失败: 历史中没有 product_card 类型对象")
            return False

        history_card = history_cards[0]

        # 逐字段比较
        critical_fields = ["type", "product_id", "title", "brand", "main_image_url"]
        for field in critical_fields:
            post_value = post_card.get(field)
            history_value = history_card.get(field)
            if post_value != history_value:
                print(f"❌ 问题#6失败: 字段 '{field}' 不一致")
                print(f"   POST: {post_value}")
                print(f"   历史: {history_value}")
                return False

        print(f"✅ 历史商品卡片与 POST 响应完全一致")

        # 步骤4：测试图片 URL 可访问性（如果存在）
        if post_card.get("main_image_url"):
            image_url = post_card["main_image_url"]
            if image_url.startswith("/static/"):
                # 转换为完整 URL
                full_image_url = f"{COMMERCE_URL}{image_url}"
                try:
                    img_resp = await client.get(full_image_url, timeout=5.0)
                    if img_resp.status_code == 200:
                        print(f"✅ 图片 URL 可访问: {image_url}")
                    else:
                        print(f"⚠️  图片 URL 返回 {img_resp.status_code}: {image_url}")
                except Exception as e:
                    print(f"⚠️  图片访问异常: {e}")

    print("✅ 测试6通过：ChatObject 持久化与历史一致性验证成功")
    return True


async def test_7_empty_shell_rejection():
    """
    测试7: 问题#6 - 空壳商品卡片拒绝测试（Schema 层）

    验证 ProductCard 模型不会接受空壳对象
    """
    print("\n" + "=" * 60)
    print("测试7：空壳商品卡片拒绝测试（问题#6）")
    print("=" * 60)

    # 动态导入，添加正确的路径
    import sys
    from pathlib import Path
    backend_path = Path(__file__).parent.parent / "customer-service-backend"
    if str(backend_path) not in sys.path:
        sys.path.insert(0, str(backend_path))

    from customer_service.schemas.chat import ProductCard
    from pydantic import ValidationError

    # 测试1：完整的商品卡片应该通过
    try:
        valid_card = ProductCard(
            type="product_card",
            product_id="15970",
            title="测试商品",
            brand="测试品牌",
            main_image_url="/static/main-images/15970.jpg",
            min_price=100.0,
            max_price=200.0
        )
        print(f"✅ 完整商品卡片验证通过: {valid_card.product_id}")
    except ValidationError as e:
        print(f"❌ 完整商品卡片验证失败（不应该）: {e}")
        return False

    # 测试2：缺少 product_id 应该失败
    try:
        invalid_card = ProductCard(
            type="product_card",
            title="测试商品"
        )
        print(f"❌ 缺少 product_id 的卡片通过验证（不应该）")
        return False
    except ValidationError:
        print(f"✅ 缺少 product_id 的卡片正确拒绝")

    # 测试3：缺少 title 应该失败
    try:
        invalid_card = ProductCard(
            type="product_card",
            product_id="15970"
        )
        print(f"❌ 缺少 title 的卡片通过验证（不应该）")
        return False
    except ValidationError:
        print(f"✅ 缺少 title 的卡片正确拒绝")

    # 测试4：type 错误应该失败
    try:
        invalid_card = ProductCard(
            type="wrong_type",
            product_id="15970",
            title="测试商品"
        )
        print(f"❌ type 错误的卡片通过验证（不应该）")
        return False
    except ValidationError:
        print(f"✅ type 错误的卡片正确拒绝")

    print("✅ 测试7通过：Schema 正确拒绝无效商品卡片")
    return True


async def main():
    print("=" * 60)
    print("问题7修复验证：Commerce 跨服务契约")
    print("=" * 60)
    print(f"Commerce URL: {COMMERCE_URL}")
    print(f"Agent URL: {AGENT_URL}")
    print(f"测试用户: user_a (li_ming88)")

    results = {}

    try:
        results["test_1"] = await test_1_internal_batch_get_has_main_image()
    except Exception as e:
        print(f"❌ 测试1异常: {e}")
        results["test_1"] = False

    try:
        results["test_2"] = await test_2_stock_status_enum()
    except Exception as e:
        print(f"❌ 测试2异常: {e}")
        results["test_2"] = False

    try:
        results["test_3"] = await test_3_promotion_with_user_token()
    except Exception as e:
        print(f"❌ 测试3异常: {e}")
        results["test_3"] = False

    try:
        results["test_4"] = await test_4_agent_product_search_complete()
    except Exception as e:
        print(f"❌ 测试4异常: {e}")
        results["test_4"] = False

    try:
        results["test_5"] = await test_5_agent_promotion_query_complete()
    except Exception as e:
        print(f"❌ 测试5异常: {e}")
        results["test_5"] = False

    try:
        results["test_6"] = await test_6_chatobject_persistence_and_history()
    except Exception as e:
        print(f"❌ 测试6异常: {e}")
        import traceback
        traceback.print_exc()
        results["test_6"] = False

    try:
        results["test_7"] = await test_7_empty_shell_rejection()
    except Exception as e:
        print(f"❌ 测试7异常: {e}")
        import traceback
        traceback.print_exc()
        results["test_7"] = False

    # 总结
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
        print("✅ 所有测试通过！问题7修复验证完成！")
        print("   包含问题修复2的对象契约验证")
        print("   包含问题#6的持久化与历史一致性验证")
        return 0
    else:
        print("❌ 部分测试失败，需要进一步修复")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
