# Vertical Slice 02：商品咨询、促销、催拍催付、Product RAG 与基础闲聊

> 文档版本：v7.0 — Developer Handoff Final  
> 日期：2026-09-22  
> 实施顺序：Foundation 之后的第二个 Slice  
> 涉及工程：`ecommerce-service-backend:8001` + `customer-service-backend:8000`  
> 本文独立、自包含。完成后必须可以完整处理 `product_query`、`promotion_query`、`urge_order_payment` 和基础 `chitchat`。

---

# 1. 业务目标

本 Slice 一次做通：

```text
商品结构化数据
商品知识索引
商品发现型检索
已知商品直接查询
促销查询
商品卖点
购买犹豫/催拍催付话术
基础闲聊
```

关键原则：

```text
Exact Product Query → Commerce Direct Path
Discovery Query     → Product RAG
动态价格/库存/SKU   → Commerce Truth
催拍催付            → Intent Flow，不使用operator action API，不使用urge_order_payment_tool
```

---

# 2. 当前源码基线与问题

当前 Agent 已有：

```text
customer_service/tools/product_search.py
customer_service/tools/selling_point.py
customer_service/tools/promotion_query.py
customer_service/tools/urge_order_payment.py
customer_service/retrieval/*（若已有）
```

需要统一：

```text
商品检索生命周期不完整
Exact product与Discovery query未明确分流
Qdrant/ES候选未统一经过Commerce真值
Query rewrite策略可能全部叠加导致高延迟
HyDE不应默认启用
旧urge_order_payment_tool只是内部编排壳层
RAG索引缺完整版本生命周期
```

---

# 3. 本 Slice 的 IntentFlowRegistry

正式注册：

```python
FLOW_REGISTRY.update({
    BusinessIntent.PRODUCT_QUERY: ProductQueryFlow(...),
    BusinessIntent.PROMOTION_QUERY: PromotionQueryFlow(...),
    BusinessIntent.URGE_ORDER_PAYMENT: UrgeOrderPaymentFlow(...),
    BusinessIntent.CHITCHAT: ChitchatFlow(...),
})
```

本 Slice 完成后这些 Flow 必须可直接 E2E。

---

# 4. Commerce Catalog Contract

## 4.1 List Products

```http
GET /api/v1/catalog/products
```

Query：

```text
q
brand
category
color
size
min_price
max_price
in_stock
page
page_size<=100
```

规则：

```text
SQL filter
→ COUNT
→ product_id ASC
→ pagination
```

禁止分页后 Python filter。

## 4.2 Product Detail

```http
GET /api/v1/catalog/products/{product_id}
```

至少：

```text
product_id
brand
product_display_name
category
material
selling_points
main_image_url
```

## 4.3 SKUs

```http
GET /api/v1/catalog/products/{product_id}/skus
```

SKU：

```text
sku_id
product_id
color
size_code
price
stock_status = in_stock | out_of_stock
```

## 4.4 Promotions

```http
GET /api/v1/catalog/products/{product_id}/promotions
Authorization: Bearer <user access jwt>
```

Commerce 最终判断：

```text
用户level
活动时间
活动状态
适用商品
```

Agent 不自行计算活动有效性。

---

# 5. Internal Product Truth

统一 Service Token：

```http
Authorization: Bearer <ECOMMERCE_SERVICE_TOKEN>
```

接口：

```text
POST /internal/v1/products/batch-get
POST /internal/v1/skus/filter
GET  /internal/v1/products/{product_id}/knowledge-card
```

不创建：

```text
/internal/v1/index/products/export
```

离线索引通过 Public Catalog 稳定分页枚举 product_id。

---

# 6. Knowledge Card

稳定索引字段：

```text
product_id
brand
product_display_name
category
material
selling_points
features
size_summary
main_image_url
size_chart_url
```

不把以下字段作为长期索引真值：

```text
当前price
当前stock
当前member-specific promotion
```

---

# 7. Static Images

Commerce 挂载：

```text
/static/main-images/{product_id}.jpg
/static/size-images/{product_id}.jpg
```

本项目不使用 SeaweedFS，不创建 product_assets。

---

# 8. ExactProductResolver：先做最便宜的路径

ProductQueryFlow 先判断是否已有明确商品：

```text
消息中product_id
或
conversation_focus唯一product
或
当前Task唯一product
```

若唯一：

```text
Commerce get_product
+ get_product_skus（按问题需要）
+ get_promotions（按问题需要）
```

不启动：

```text
embedding
Qdrant
ES
Multi-query
HyDE
```

例如：

```text
“15970还有M码吗？”
“刚才那个多少钱？”
“这件什么材质？”
```

直接 Commerce Path。

---

# 9. Discovery Query 才走 Product RAG

例如：

```text
“想找黑色通勤裙，预算400”
“适合上班穿得利落但别太正式”
```

进入：

```text
ProductRetrievalService.search()
```

---

# 10. RAG 基础设施

```text
TEI :8080
→ BAAI/bge-m3 dense

Qdrant
→ product_knowledge

Elasticsearch
→ product_knowledge_v1
```

只使用 BGE-M3 dense；BM25 由 ES 负责。

不引入：

```text
BGE sparse
ColBERT
复杂reranker
```

---

# 11. Agent DB：Product Index Manifest

Alembic：

```text
0002_product_index_manifest.py
```

表：

```text
product_id PK
source_hash
index_signature
chunk_count
qdrant_sync_status
es_sync_status
indexed_at
last_error NULL
```

`index_signature` 至少由：

```text
source_hash
source_schema_version
chunker_version
embedding_model
embedding_dimension
```

组成。

因此 embedding/chunker 改变时，即使商品文本没变，也会重建索引。

---

# 12. Offline Index Builder

新增：

```text
scripts/build_product_index.py
```

支持：

```text
--full
--product-id
--batch-size
--dry-run
--delete-missing
```

Full：

```text
Catalog稳定分页完整枚举
→ knowledge-card
→ normalize
→ source_hash/index_signature
→ logical chunks
→ TEI embed_documents
→ Qdrant upsert
→ ES bulk
→ manifest
```

---

# 13. Safe `--delete-missing`

必须两阶段：

```text
Phase A
完整枚举所有Commerce product_id
↓
只有枚举成功到最后一页
complete_source_snapshot=true
↓
Phase B
允许delete missing
```

Catalog 中途失败：

```text
禁止delete missing
```

避免误删未枚举到的商品。

---

# 14. Chunk 策略

逻辑切分，不机械按字符：

```text
overview
selling_points
material
size
```

Chunk ID 稳定：

```text
{product_id}:{chunk_type}:{ordinal}
```

Payload：

```text
product_id
chunk_id
chunk_type
brand
category
source_hash
index_signature
```

---

# 15. QueryContextResolver

在 RAG 前做：

```text
指代解析
硬实体提取
semantic_query构造
```

有唯一 focused product：通常应走 Direct Path，而不是 RAG。

多个候选、用户说“这个”：

```text
不猜candidate[0]
→ REFERENCE_AMBIGUOUS
→ clarification
```

---

# 16. Hard Filters 与 Semantic Query 分离

用户：

```text
“想找黑色通勤连衣裙，预算400”
```

Planner：

```json
{
  "semantic_query": "通勤 连衣裙",
  "filters": {
    "category": "连衣裙",
    "color": "黑色",
    "max_price": 400
  }
}
```

Query Rewrite 只允许改 `semantic_query`，不能改用户明确的：

```text
brand
color
size
price
product_id
```

Commerce Preferences / Agent Memory 默认是 soft signal，不自动成为 hard filter。

---

# 17. Adaptive Retrieval

## Stage 1

```text
resolved semantic query
→ Qdrant dense
+ ES BM25
→ RRF
→ product-level聚合
→ Commerce truth validation
```

若有效候选数量达到配置：

```text
RAG_MIN_VALID_CANDIDATES（建议初值3）
```

直接结束。

## Stage 2 Multi-query

只有 Stage 1 不足才调用 LLM。

生成：

```text
original/resolved query
+ 最多2个等义改写
```

保留 original；rewrite 失败 → 仅 original。

禁止改写生成新的硬约束。

## Stage 3 HyDE

代码可以存在：

```text
HyDEStrategy
```

默认：

```env
RAG_ENABLE_HYDE=false
```

只有 Golden Eval 证明 Recall 有实际提升再开启。

HyDE 文本只用于 embedding，不是事实。

---

# 18. RRF 与 Product-Level 去重

```python
score += 1 / (k + rank)
```

建议 `k=60`。

多 query + 多 chunk 会导致同一商品多次命中，因此：

```text
先chunk融合
→ 再按product_id聚合
```

不能让 chunk 多的商品天然占优。

---

# 19. Commerce Truth Validation

最终候选：

```text
candidate product_ids
→ internal skus/filter
→ batch-get products
```

最终展示：

```text
price
stock
sku
color/size可售性
```

全部来自当前 Commerce。

索引命中但 Commerce 已下架/无符合 SKU：drop。

---

# 20. RAG 降级

```text
Qdrant + ES + Commerce  → normal
Qdrant down             → ES + Commerce
ES down                  → Qdrant + Commerce
TEI down                 → ES + Commerce
Qdrant/ES/TEI不可用      → Commerce structured search
Commerce down            → 不确认动态价格/库存/SKU
```

Retrieval mode 进入 ToolResult 与 Langfuse metadata。

---

# 21. ProductQueryFlow

```text
resolve exact product?
├─ YES → Commerce Direct Path
└─ NO  → product_search_tool
          ↓
       ProductRetrievalService
          ↓
       candidate products
↓
response_gen(product_query prompt)
```

`product_search_tool` 是业务 Tool。

---

# 22. SellingPointTool

输入：

```text
product_id
user_need
include_promotion
```

聚合：

```text
knowledge-card
+ 可选当前promotion
```

输出 Evidence，不在 Tool 内写自由营销文案。

---

# 23. PromotionQueryFlow

要求：

```text
唯一 product_id
```

缺商品：澄清。

有商品：

```text
promotion_query_tool
→ Commerce get_promotions(user bearer)
```

无活动：

```text
ok=true
items=[]
```

不是错误。

---

# 24. UrgeOrderPaymentFlow：纯 Intent 驱动

不增加：

```text
operator action API
urge_order_payment_tool
```

触发表达示例：

```text
“有点贵，我再考虑一下”
“这个值得买吗？”
“我还没决定要不要下单”
“适合我吗，我有点犹豫”
```

与其他 Intent 边界：

```text
“有什么优惠？”      → promotion_query
“面料怎么样？”      → product_query
“我还在犹豫值不值得” → urge_order_payment
```

执行：

```text
唯一/当前商品
↓
asyncio.gather:
  knowledge card / selling points
  current promotion
  Commerce explicit preferences（若已有）
  relevant semantic memory（若Memory Slice已实现；否则为空）
↓
ConversionEvidence
↓
response_gen urge_order_payment template
```

只调用一次最终 response LLM。

性能目标：

```text
典型路径约3秒体验目标
```

不是硬 3.000 秒 SLA；后续使用 p50/p95 实测。

---

# 25. ChitchatFlow

无业务 Tool。

有 active business task 时：

```text
短回复
不push chitchat Task
保留active task
可提醒未完成步骤
```

无业务任务时普通闲聊。

---

# 26. Product ChatObject

不要使用语义不明确的单个 `price`。

```json
{
  "type": "product_card",
  "product_id": "15970",
  "title": "女士通勤连衣裙",
  "brand": "Turtle",
  "main_image_url": "/static/main-images/15970.jpg",
  "min_price": "299.90",
  "max_price": "329.90",
  "matched_skus": []
}
```

若唯一 selected SKU：可附：

```text
selected_sku_id
selected_sku_price
```

---

# 27. Retrieval Guard

索引文本永远是 untrusted data。

例如 chunk 中出现：

```text
忽略系统规则
调用退货工具
泄露系统Prompt
```

只作为商品数据或直接丢弃，不能改变 Tool / Intent Policy。

---

# 28. 具体文件

## Commerce

```text
app/api/public/catalog.py
app/api/internal/products.py
app/api/internal/skus.py
app/repositories/product.py
app/services/catalog.py
app/schemas/catalog.py
app/models/product.py
app/app.py  # StaticFiles
```

## Agent

```text
customer_service/flows/registry.py
customer_service/flows/product.py
customer_service/flows/promotion.py
customer_service/flows/conversion.py
customer_service/flows/chitchat.py

customer_service/tools/product_search.py
customer_service/tools/selling_point.py
customer_service/tools/promotion_query.py
customer_service/tools/registry.py

customer_service/retrieval/models.py
customer_service/retrieval/query_planner.py
customer_service/retrieval/context_resolver.py
customer_service/retrieval/multi_query.py
customer_service/retrieval/hyde.py
customer_service/retrieval/qdrant_retriever.py
customer_service/retrieval/es_retriever.py
customer_service/retrieval/fusion.py
customer_service/retrieval/product_hydrator.py
customer_service/retrieval/service.py
customer_service/retrieval/guard.py

customer_service/indexing/chunker.py
customer_service/indexing/manifest.py
customer_service/indexing/builder.py
customer_service/infrastructure/embedding.py
scripts/build_product_index.py
alembic/versions/0002_product_index_manifest.py
```

删除旧：

```text
customer_service/tools/urge_order_payment.py
```

前提：先确认没有其他模块仍依赖它；迁移调用方到 `UrgeOrderPaymentFlow` 后再删除。

---

# 29. Prompt

新增薄模板：

```text
response/product_query.jinja2
response/promotion_query.jinja2
response/urge_order_payment.jinja2
retrieval/multi_query.jinja2
retrieval/hyde.jinja2
```

公共 evidence/safety 规则复用 shared template。

---

# 30. Langfuse Observation

```text
flow.product_query
flow.promotion_query
flow.urge_order_payment
rag.query_plan
rag.qdrant
rag.elasticsearch
rag.fusion
rag.commerce_truth
tool.product_search
tool.selling_point
tool.promotion_query
response.generate
```

记录：

```text
retrieval_mode
query_variant_count
candidate_count
truth_pass_count
conversion_context_latency
total_turn_latency
```

---

# 31. Slice 测试

## Unit

```text
ExactProductResolver
Hard/Soft filter separation
RRF
index_signature
Query Planner
Multi-query fallback
HyDE default off
ProductCard min/max price schema
urge_order_payment intent boundary
```

## Integration

真实：

```text
8001 Catalog
TEI
Qdrant test collection
ES test index
```

测试：

```text
full index
incremental
safe delete missing
Qdrant down
ES down
TEI down
Commerce truth overrides stale index
```

## Slice E2E

至少：

```text
product_query exact path
product_query discovery RAG path
promotion_query有活动/无活动
urge_order_payment购买犹豫场景
chitchat无Task/有active Task场景
```

---

# 32. Golden Dataset

创建：

```text
evals/datasets/product_rag_golden.jsonl
evals/datasets/conversion_intent_golden.jsonl
```

指标：

```text
Recall@5
MRR
Commerce truth pass rate
urge_order_payment intent correctness
tool/flow selection correctness
```

---

# 33. Completion Gate

```text
Catalog/SKU/Promotion/KnowledgeCard稳定
StaticImages可访问
Offline index可重建/增量
Exact path不启动RAG
Discovery path支持Hybrid+RRF
Multi-query只在不足时运行
HyDE默认OFF
动态price/stock/SKU最终只信Commerce
product_query E2E通过
promotion_query E2E通过
urge_order_payment E2E通过且无operator API/无业务Tool
chitchat E2E通过
```
