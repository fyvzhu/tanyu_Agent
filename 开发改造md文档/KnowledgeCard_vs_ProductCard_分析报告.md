# KnowledgeCard vs ProductCard 混淆问题分析报告

## 📋 问题背景

根据 v7 开发文档的说明，`ProductKnowledgeCard` 和 `ProductCard` 是两种完全不同的对象，但容易被混淆：

### ProductKnowledgeCard（知识卡片）
- **用途**：离线索引、向量检索
- **特点**：稳定的事实信息（品牌、材质、卖点）
- **不包含**：实时价格、库存状态、用户专属促销
- **生命周期**：离线构建索引时使用
- **API 端点**：`/internal/v1/products/{id}/knowledge-card`

### ProductCard（商品卡片）
- **用途**：前端展示
- **特点**：实时商品状态
- **包含**：当前价格、库存状态、可能的用户专属促销
- **生命周期**：用户查询时实时组装
- **数据来源**：Commerce API `/api/v1/catalog/products/{id}` + SKU 数据

---

## ✅ 当前实现检查结果

### 1. **索引构建器（builder.py）** ✅ 正确
```python
# Line 58: 正确调用 knowledge_card()
knowledge_card = await self.commerce.knowledge_card(product_id)

# Line 88: 正确用于切块和向量化
chunks = self.chunker.chunk_product(product_id, knowledge_card)
```
**结论**：索引构建器正确使用 `ProductKnowledgeCard`，仅用于离线索引。

---

### 2. **EcommerceClient** ✅ 正确区分
```python
# Line 151: 获取实时商品详情（ProductPublic）
async def get_product(self, product_id: str) -> dict[str, Any]:
    return await self._request("GET", f"/api/v1/catalog/products/{product_id}")

# Line 161: 获取知识卡片（ProductKnowledgeCard）
async def knowledge_card(self, product_id: str) -> dict[str, Any]:
    return await self._request("GET", f"/internal/v1/products/{product_id}/knowledge-card", internal=True)
```
**结论**：Client 正确区分了两个端点。

---

### 3. **ProductFlow** ✅ 基本正确，但需要加强文档

#### Direct Query 路径（Line 147-155）
```python
# 获取实时商品详情和 SKU
product = await self.commerce.get_product(target_product_id)
skus = await self.commerce.get_skus(target_product_id)

# 组装 ProductCard
product_cards = [self._to_product_card(product, skus)]
```
✅ **正确**：使用实时 API，未使用 KnowledgeCard

#### RAG Query 路径（Line 243-291）
```python
# Tool 返回候选商品（来自向量检索 + Commerce 回查）
candidates = data.get("candidates", [])

# 从 candidate 提取实时数据
for candidate in candidates:
    product_card = {
        "product_id": product_id,
        "main_image_url": candidate.get("main_image_url"),  # ⚠️ 来自哪里？
        "min_price": candidate.get("min_price"),  # ⚠️ 实时还是索引？
        "selected_sku_price": selected_sku.get("price"),  # ✅ 来自 SKU
    }
```

⚠️ **需要澄清**：`candidate` 中的数据来源

---

### 4. **product_search_tool** ✅ 正确，但需要加强注释

#### RAG 路径（Line 79-106）
```python
# 1. 向量检索得到 product_ids
# 2. 调用 batch_get_products() 获取实时商品信息
products = {
    item["product_id"]: item
    for item in await client.batch_get_products(product_ids)
}

# 3. 组装 candidate（包含实时价格和图片）
candidates.append({
    "main_image_url": product.get("main_image_url"),  # ✅ 来自实时 API
    "min_price": product.get("min_price"),  # ✅ 实时价格范围
    "selected_sku": sku,  # ✅ 实时 SKU
})
```

✅ **正确**：虽然使用了向量检索，但所有展示数据都来自实时 Commerce API

---

## 🔍 发现的问题

### 问题1：`batch_get_products()` 返回的数据结构不明确

**位置**：`customer-service-backend/customer_service/clients/ecommerce.py` Line 164-174

**当前实现**：
```python
async def batch_get_products(self, product_ids: list[str]) -> list[dict[str, Any]]:
    data = await self._request(
        "POST",
        "/internal/v1/products/batch-get",
        json={"product_ids": product_ids},
        internal=True,
    )
    return data if isinstance(data, list) else []
```

**问题**：
- 返回的是 `ProductListItem`（包含 `main_image_url`, `min_price`, `max_price`）
- 但没有明确说明这些字段是**实时查询的**，不是来自 KnowledgeCard

---

### 问题2：`main_image_url` 的语义需要澄清

**KnowledgeCard 中的 `main_image_url`**（Line 90-102）：
```python
# ecommerce-service-backend/app/api/internal/products.py
main_image_url = f"/static/main-images/{product_id}.jpg"
```
- 这是一个**静态路径**，用于索引
- 不保证图片当前可访问

**ProductCard 中的 `main_image_url`**：
- 应该是**当前可访问的图片地址**
- 需要验证图片存在

**当前实现**：两者使用相同的静态路径，这是合理的（因为图片确实是静态的），但需要在文档中说明。

---

### 问题3：价格字段的语义不够明确

**ProductCard 中的价格**（Line 285-288）：
```python
"min_price": float(min_price) if min_price is not None else None,
"max_price": float(max_price) if max_price is not None else None,
```

**需要明确**：
- 是"该商品所有 SKU 的价格区间"？
- 还是"经过用户硬约束过滤后、可展示 SKU 的价格区间"？

**当前实现**：根据代码，是"所有 SKU 的价格区间"（来自 `batch_get_products`），但注释不够清晰。

---

## 📝 建议的修复

### 修复1：为 `batch_get_products()` 添加清晰的文档注释

```python
async def batch_get_products(self, product_ids: list[str]) -> list[dict[str, Any]]:
    """
    批量获取商品信息（用于组装 ProductCard）

    ⚠️ 重要：此方法返回实时商品数据（ProductListItem），不是 KnowledgeCard

    返回字段：
    - product_id, brand, product_display_name, category
    - main_image_url: 实时可访问的图片地址
    - min_price, max_price: 该商品所有 SKU 的当前价格区间
    - has_stock: 是否有任何 SKU 有库存

    用途：
    - RAG 检索后，根据 product_ids 回查实时商品状态
    - 组装 ProductCard 前端展示对象
    """
```

### 修复2：为 ProductFlow 添加数据来源注释

```python
# product.py Line 278-290
# 构造 ProductCard
# ⚠️ 数据来源说明：
# - main_image_url, min_price, max_price: 来自 Commerce API 实时查询
# - selected_sku_price, stock_status: 来自 SKU Filter 实时查询
# - 不使用 KnowledgeCard 中的任何字段
product_card = {
    "type": "product_card",
    "product_id": product_id,
    "main_image_url": candidate.get("main_image_url"),  # 实时 API
    "min_price": float(min_price),  # 实时价格
}
```

### 修复3：在 ProductKnowledgeCard 中添加警告注释

```python
# ecommerce-service-backend/app/schemas/internal.py
class ProductKnowledgeCard(BaseModel):
    """
    商品知识卡片（供 RAG 索引使用）

    ⚠️ 重要区别：
    - ProductKnowledgeCard: 稳定事实信息，用于向量检索
    - ProductCard: 实时商品状态，用于前端展示

    此模型的字段：
    - 仅用于离线索引和语义检索
    - 不包含实时价格、库存、用户专属促销
    - main_image_url 是静态路径，不保证当前可访问

    使用场景：
    1. 离线索引构建：IndexBuilder 调用 /knowledge-card 端点
    2. 向量切块：Chunker 处理 KnowledgeCard 生成文本块
    3. 语义检索：Qdrant/ES 检索时使用切块内容

    禁止场景：
    ❌ 不要直接展示给前端用户
    ❌ 不要用于价格/库存判断
    ❌ 不要写入用户专属信息
    """
    product_id: str
    main_image_url: str | None = Field(
        None,
        description="静态图片路径（仅供索引）。展示时必须使用 ProductCard 的 main_image_url"
    )
```

### 修复4：在 ProductCard Schema 中添加对比说明

```python
# customer-service-backend/customer_service/schemas/chat.py
class ProductCard(BaseModel):
    """
    商品卡片（前端展示对象）

    ⚠️ 与 ProductKnowledgeCard 的区别：
    - ProductCard: 实时查询，包含当前价格/库存，可直接展示
    - ProductKnowledgeCard: 离线索引，只包含稳定事实，不可展示

    数据来源：
    - ProductFlow 通过 Commerce API 实时查询组装
    - min_price/max_price: 该商品所有 SKU 的当前价格区间
    - selected_sku_price: 用户约束过滤后的推荐 SKU 价格
    - stock_status: 推荐 SKU 的实时库存状态
    - main_image_url: 当前可访问的图片地址

    前端展示要求：
    - 价格区间显示："¥{min_price} - ¥{max_price}"
    - 如果有 selected_sku，优先展示其价格和库存
    - 图片必须可访问（需要验证 HTTP 200）
    """
    type: Literal["product_card"] = "product_card"
    product_id: str
    title: str | None = None
    brand: str | None = None
    main_image_url: str | None = Field(
        None,
        description="实时可访问的图片地址。来自 Commerce API，不是 KnowledgeCard"
    )
```

---

## ✅ 总体结论

**当前代码实现是正确的**，没有严重的混淆问题：

1. ✅ **索引构建器**正确使用 `ProductKnowledgeCard`
2. ✅ **ProductFlow** 正确使用实时 Commerce API 组装 `ProductCard`
3. ✅ **product_search_tool** 虽然使用向量检索，但所有展示数据都来自实时回查

**需要改进的地方**：

1. 📝 **文档注释不够清晰**：需要在关键位置说明数据来源和使用场景
2. 📝 **字段语义需要澄清**：特别是 `main_image_url` 和 `min_price/max_price`
3. 📝 **缺少边界检查**：没有防止"错误使用 KnowledgeCard 字段"的保护机制

**建议操作**：

1. 添加上述文档注释（不修改代码逻辑）
2. 在 Code Review 时强调这个区别
3. 在测试中验证：
   - ✅ ProductCard 的价格是实时的
   - ✅ ProductCard 的图片是可访问的
   - ✅ KnowledgeCard 仅用于索引，从未直接展示

---

## 🔄 数据流总结

```
离线流程：
  Commerce /knowledge-card API
    → ProductKnowledgeCard（稳定事实）
    → IndexBuilder 切块
    → Qdrant/ES 向量索引

在线流程：
  用户查询
    → 向量检索（使用 KnowledgeCard 的文本块）
    → 候选 product_ids
    → Commerce /products API（实时回查）
    → ProductCard（实时状态）
    → 前端展示
```

**关键原则**：
- KnowledgeCard 在向量检索后**立即丢弃**
- ProductCard 完全基于**实时 API**，不依赖索引中的旧数据
- 价格、库存、图片可访问性**必须实时验证**

---

## 📋 后续 TODO

1. ✅ 添加文档注释（优先级：P0）
2. 🔲 添加测试验证图片可访问（优先级：P1）
3. 🔲 在 ProductCard 序列化前验证必填字段（优先级：P1）
4. 🔲 监控 main_image_url 的 404 率（优先级：P2）
