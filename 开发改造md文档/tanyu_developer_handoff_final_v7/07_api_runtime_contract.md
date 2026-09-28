# 探域电商售前 Agent：最终 HTTP / Runtime Contract

> 文档版本：v7.0 — Developer Handoff Final  
> 日期：2026-09-22  
> 适用：`ecommerce-service-backend:8001`、`customer-service-backend:8000`  
> 本文独立、自包含，是开发期 Living Contract 的完整人工规范。FastAPI `/openapi.json` 是可执行 Contract；Cross-Service E2E 全通过后导出 v1.0 Snapshot 并冻结。

---

# 1. Living Contract 规则

开发期允许跨服务 coordinated change，但必须同步：

```text
8001 implementation
8001 tests
本Contract
8000 EcommerceClient
Agent Flow/Tool
Slice tests
```

禁止只改一侧。

最终 Freeze：

```text
Cross-Service E2E全绿
→ openapi-commerce-v1.json
→ openapi-agent-v1.json
→ tag v1.0
```

---

# 2. 通用 HTTP

```text
Commerce :8001
Agent    :8000
Frontend :5173
```

JSON：

```http
Content-Type: application/json
```

SSE：

```http
Content-Type: text/event-stream
```

---

# 3. Request-ID

```http
X-Request-ID: <id>
```

缺失/非法则生成。

所有 Response header 回写；8000→8001 传播相同 request_id。

---

# 4. Standard Envelope

成功：

```json
{
  "success": true,
  "data": {},
  "request_id": "..."
}
```

失败：

```json
{
  "success": false,
  "error": {
    "code": "ORDER_NOT_FOUND",
    "message": "订单不存在",
    "details": {}
  },
  "request_id": "..."
}
```

---

# 5. Auth Contract

## Access JWT

```text
alg=RS256
iss=tanyu-ecommerce-service
aud=tanyu-services
sub=user_id
type=access
exp
iat
```

## Refresh

```text
Opaque random token
HttpOnly Cookie
DB SHA-256 hash
rotation/revocation
```

## Internal Service Token

```http
Authorization: Bearer <ECOMMERCE_SERVICE_TOKEN>
```

仅 `/internal/v1/*`。

---

# Part I：Commerce API :8001

# 6. Auth

```text
POST /api/v1/auth/login
POST /api/v1/auth/refresh
POST /api/v1/auth/logout
GET  /api/v1/auth/me
```

Login data：

```json
{
  "access_token": "...",
  "token_type": "bearer",
  "expires_in": 1800,
  "user": {
    "user_id": "U001",
    "username": "user01",
    "nickname": "小明",
    "level": "PLUS"
  }
}
```

---

# 7. User Profile Aggregate

## Profile

```text
GET   /api/v1/users/me/profile
PATCH /api/v1/users/me/profile
```

## Preferences

```text
GET /api/v1/users/me/preferences
PUT /api/v1/users/me/preferences
```

PUT replace-all explicit preferences。

## Measurements

```text
GET   /api/v1/users/me/measurements
PATCH /api/v1/users/me/measurements
```

PATCH partial update；explicit null 当前 422。

示例：

```json
{
  "height_cm": 165,
  "weight_kg": 57,
  "bust_cm": 88,
  "waist_cm": 70,
  "hip_cm": 92,
  "shoulder_cm": 38
}
```

---

# 8. Common Enums

## OrderStatus

```text
pending_payment
pending_shipment
awaiting_pickup
in_transit
awaiting_receipt
completed
canceled
```

## StockStatus

```text
in_stock
out_of_stock
```

## AfterSaleType

```text
return
exchange
```

## RequestStatus

```text
submitted
processing
completed
rejected
canceled
```

---

# 9. Catalog List

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
page>=1
page_size<=100
```

`page_size>100` → 422。

Response：

```json
{
  "items": [
    {
      "product_id": "15970",
      "brand": "Turtle",
      "product_display_name": "女士通勤连衣裙",
      "category": "连衣裙",
      "main_image_url": "/static/main-images/15970.jpg",
      "min_price": "299.90",
      "max_price": "329.90",
      "has_stock": true
    }
  ],
  "page": 1,
  "page_size": 20,
  "total": 100
}
```

默认 `product_id ASC`。

---

# 10. Product Detail

```http
GET /api/v1/catalog/products/{product_id}
```

```json
{
  "product_id": "15970",
  "brand": "Turtle",
  "product_display_name": "女士通勤连衣裙",
  "category": "连衣裙",
  "material": "聚酯纤维",
  "selling_points": ["..."],
  "main_image_url": "/static/main-images/15970.jpg"
}
```

---

# 11. Product SKUs

```http
GET /api/v1/catalog/products/{product_id}/skus
```

```json
{
  "items": [
    {
      "sku_id": "SKU15970_02",
      "product_id": "15970",
      "color": "黑色",
      "size_code": "M",
      "price": "299.90",
      "stock_status": "in_stock"
    }
  ]
}
```

---

# 12. Size Chart + Recommendation Range

```http
GET /api/v1/catalog/products/{product_id}/size-chart
```

商品不存在：

```text
404 PRODUCT_NOT_FOUND
```

`available` 只表示“SizeChart rows 是否可用”。

商品存在但没有尺码表：

```json
{
  "product_id": "15970",
  "category": "衬衫",
  "available": false,
  "rows": [],
  "recommendation": null,
  "size_chart_url": null
}
```

商品有尺码表但没有配置 Range Recommendation：

```json
{
  "product_id": "15970",
  "category": "衬衫",
  "available": true,
  "rows": [
    {
      "size_code": "M",
      "measurements": {
        "bust_cm": 92,
        "waist_cm": 76,
        "shoulder_cm": 39
      }
    }
  ],
  "recommendation": null,
  "size_chart_url": "/static/size-images/15970.jpg"
}
```

此时 Agent 可以展示尺码表，但不能自动声称推荐了某个尺码。

可用：

```json
{
  "product_id": "15970",
  "category": "衬衫",
  "available": true,
  "rows": [
    {
      "size_code": "S",
      "measurements": {
        "bust_cm": 88,
        "waist_cm": 72,
        "shoulder_cm": 38
      }
    },
    {
      "size_code": "M",
      "measurements": {
        "bust_cm": 92,
        "waist_cm": 76,
        "shoulder_cm": 39
      }
    }
  ],
  "recommendation": {
    "policy": "range_match",
    "required_measurements": [
      "height_cm",
      "weight_kg"
    ],
    "rules": [
      {
        "rule_id": "R-S",
        "priority": 100,
        "conditions": {
          "height_cm": {"min": 150, "max": 160},
          "weight_kg": {"min": 40, "max": 48}
        },
        "recommended_sizes": ["S"]
      },
      {
        "rule_id": "R-M",
        "priority": 100,
        "conditions": {
          "height_cm": {"min": 160, "max": 168},
          "weight_kg": {"min": 48, "max": 55}
        },
        "recommended_sizes": ["M"]
      }
    ]
  },
  "size_chart_url": "/static/size-images/15970.jpg"
}
```

Range Contract：

```text
每个字段范围统一解释为 [min,max)
min=null → 无下界
max=null → 无上界
同一Rule内多个conditions → AND
priority越大优先级越高
recommended_sizes必须非空
recommended_sizes必须属于该商品合法size_code
```

`rows` 与 `recommendation` 是两种不同业务数据：

```text
rows
→ 商品尺码/成衣尺寸事实，用于展示

recommendation
→ 用户身体数据适配范围，用于确定性尺码推荐
```

禁止从 `rows` 自动推导人体推荐范围。

Commerce 持久化建议使用：

```text
products.size_recommendation_rules JSON NULL
```

只存：

```text
policy
required_measurements
rules
```

不建立通用 Rule Engine / Rule Admin / Rule Version 平台。

---

# 13. Promotions

```http
GET /api/v1/catalog/products/{product_id}/promotions
Authorization: Bearer <user JWT>
```

```json
{
  "items": [
    {
      "promotion_id": "PR1",
      "title": "满300减30",
      "promotion_type": "threshold_discount",
      "description": "满300减30",
      "start_at": "...",
      "end_at": "...",
      "applicable": true
    }
  ]
}
```

---

# 14. Orders List

```http
GET /api/v1/orders?status=&page=1&page_size=20
```

只返回当前用户。

---

# 15. Order Detail

```http
GET /api/v1/orders/{order_id}
```

Non-owner/不存在统一 404。

```json
{
  "order_id": "O1001",
  "status": "completed",
  "status_label": "已完成",
  "amount": "299.90",
  "created_at": "...",
  "items": [
    {
      "product_id": "15970",
      "sku_id": "SKU15970_02",
      "quantity": 1,
      "price": "299.90",
      "amount": "299.90",
      "return_eligible": true,
      "exchange_eligible": true,
      "active_after_sale": null
    }
  ]
}
```

Eligibility 由 Commerce 计算。

---

# 16. Logistics

```http
GET /api/v1/orders/{order_id}/logistics
```

```json
{
  "order_id": "O2",
  "order_status": "in_transit",
  "latest_trace": {
    "status": "in_transit",
    "description": "...",
    "time": "..."
  },
  "traces": []
}
```

---

# 17. Return

```http
POST /api/v1/orders/{order_id}/return-requests
Authorization: Bearer <USER_ACCESS_TOKEN>
Idempotency-Key: <stable-key>
```

```json
{
  "product_id": "15970",
  "sku_id": "SKU15970_02",
  "reason": "尺码太小"
}
```

Response：

```json
{
  "return_request_id": "R1",
  "status": "submitted",
  "refund_amount": "299.90"
}
```

`refund_amount=order_item.amount`，请求不能传金额和 quantity。

---

# 18. Exchange

```http
POST /api/v1/orders/{order_id}/exchange-requests
Authorization: Bearer <USER_ACCESS_TOKEN>
Idempotency-Key: <stable-key>
```

```json
{
  "product_id": "15970",
  "original_sku_id": "SKU15970_02",
  "exchange_sku_id": "SKU15970_03",
  "reason": "换大一码"
}
```

Response：

```json
{
  "exchange_request_id": "E1",
  "status": "submitted",
  "refund_amount": "0.00"
}
```

---

# 19. Shipping Urge

```http
POST /api/v1/orders/{order_id}/shipping-urge-requests
Authorization: Bearer <USER_ACCESS_TOKEN>
Idempotency-Key: <stable-key>
```

```json
{
  "reason_code": "NORMAL_URGE",
  "reason_detail": "用户后天急用，希望尽快发出"
}
```

仅 `pending_shipment` 可创建。

---

# 20. Idempotency

适用：

```text
return
exchange
shipping urge
```

```text
same key + same completed payload → replay
same key + different payload → 409 IDEMPOTENCY_KEY_REUSED
processing lock timeout → 409 REQUEST_IN_PROGRESS
different key + active business duplicate → 409 BUSINESS_CONFLICT
```

---

# 21. Static Images

```text
GET /static/main-images/{product_id}.jpg
GET /static/size-images/{product_id}.jpg
```

---

# 22. Internal Product Truth

统一 Service Token。

## Batch Get

```http
POST /internal/v1/products/batch-get
```

```json
{
  "product_ids": ["15970", "15971"]
}
```

Response：

```json
{
  "items": [
    {
      "product_id": "15970",
      "brand": "Turtle",
      "product_display_name": "女士连衣裙",
      "category": "连衣裙",
      "material": "聚酯纤维",
      "main_image_url": "/static/main-images/15970.jpg"
    }
  ],
  "missing_product_ids": []
}
```

## SKU Filter

```http
POST /internal/v1/skus/filter
```

```json
{
  "product_ids": ["15970"],
  "colors": ["黑色"],
  "sizes": ["M"],
  "min_price": null,
  "max_price": "400.00",
  "stock_status": "in_stock"
}
```

Response `items[]` 使用标准 SKU schema。

## Knowledge Card

```http
GET /internal/v1/products/{product_id}/knowledge-card
```

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

---

# Part II：Agent API :8000

# 23. Chat Sessions

```http
POST /api/v1/chat/sessions
Authorization: Bearer <access jwt>
```

```json
{
  "channel": "web"
}
```

Response：

```json
{
  "session_id": "S1",
  "status": "active",
  "channel": "web",
  "created_at": "..."
}
```

---

# 24. Chat Message

```http
POST /api/v1/chat/sessions/{session_id}/messages
```

```json
{
  "message": "想要黑色通勤连衣裙，预算400"
}
```

Response：

```json
{
  "turn_id": "T1",
  "message_id": "M2",
  "text": "...",
  "objects": [],
  "task": {
    "intent": "product_query",
    "status": "completed"
  },
  "dialogue_reason": null
}
```

Task 只返回安全摘要，不返回完整 AgentState。

---

# 25. Chat Stream

```http
POST /api/v1/chat/sessions/{session_id}/messages:stream
Accept: text/event-stream
```

事件：

```text
status
delta
objects
done
error
```

### status

```json
{"stage":"retrieving"}
```

Stage：

```text
understanding
retrieving
checking_business_data
generating
finalizing
```

### delta

```json
{"text":"这款..."}
```

### objects

```json
{"items":[...]}
```

### done

```json
{"turn_id":"T1","message_id":"M2"}
```

### error

```json
{
  "code":"COMMERCE_UNAVAILABLE",
  "message":"暂时无法查询业务数据",
  "request_id":"..."
}
```

正常澄清不发 error event。

---

# 26. Chat History

```http
GET /api/v1/chat/sessions/{session_id}/messages?limit=50&cursor=...
```

Cursor pagination。

---

# 27. Delete Session

```http
DELETE /api/v1/chat/sessions/{session_id}
```

```json
{
  "session_id": "S1",
  "status": "closed"
}
```

Checkpoint 删除；messages保留；session不能继续POST。

---

# 28. Chat Object Types

## ProductCard

```text
type=product_card
product_id
title
brand
main_image_url
min_price
max_price
matched_skus[]
selected_sku_id optional
selected_sku_price optional
```

## OrderItemChoice

```text
type=order_item_choice
order_id
items[]
```

## SizeRecommendation

```text
type=size_recommendation
product_id
primary_size
recommended_sizes[]
matching_skus[]
used_measurements
matched_rule_ids[]
reason_codes[]
size_chart_url
```

`primary_size` 规则：

```text
最终recommended_sizes只有1个 → 该size
最终recommended_sizes>1个 → null
```

如果多个最高 priority Rule 同时命中：

```text
合并recommended_sizes
去重
禁止candidate[0]
```

## ActionReceipt

```text
type=action_receipt
action=return|exchange|urge_shipping|save_measurements
resource_id optional
status
order_id optional
refund_amount optional

resource_id 约束：
return/exchange/urge_shipping → resource_id required
save_measurements → resource_id=null
```

---

# 29. Intent Runtime Contract

固定 9 个 BusinessIntent。

```text
recognized=false → intent=null
```

ActionMode：

```text
informational
action_request
```

IntentDecision：

```text
accept
clarify
out_of_scope
classifier_failure
```

Decision 语义固定：

```text
accept
→ recognized=true, intent=<一个BusinessIntent>

clarify
→ 有 plausible business candidate 但 confidence/margin 不足，或没有可靠业务候选
→ recognized=false, intent=null, fallback_reason=low_confidence

out_of_scope
→ classifier 明确判定不属于 9 类业务范围
→ recognized=false, intent=null, fallback_reason=out_of_scope

classifier_failure
→ LLM/API/schema parse 真正失败
→ recognized=false, intent=null, fallback_reason=classifier_failure
```

禁止把 `<0.55` 直接映射成 `out_of_scope` 或 `classifier_failure`；confidence 只是 DecisionEngine 信号。

---

# 30. Task Runtime Contract

Status：

```text
active
waiting_slot
waiting_confirmation
ready
paused
completed
canceled
failed
```

普通槽位补充不使用 `interrupt()`。

---

# 30.1 IntentPolicy Matrix

| BusinessIntent | allowed_tools | can_write | requires_action_request | requires_execute_confirmation |
|---|---|---:|---:|---:|
| `product_query` | `product_search_tool`, `selling_point_tool` | false | false | false |
| `size_recommend` | `size_recommend_tool` | false | false | false |
| `urge_order_payment` | 无 | false | false | false |
| `promotion_query` | `promotion_query_tool` | false | false | false |
| `logistics_query` | `logistics_query_tool` | false | false | false |
| `return` | `return_request_tool` | true | true | true |
| `exchange` | `exchange_request_tool` | true | true | true |
| `chitchat` | 无 | false | false | false |
| `urge_shipping` | `urge_shipping_tool` | true | true | false |

`save_measurements` 不属于 BusinessIntent Tool；它只能由 `UserContextWriteService` 在 `SAVE_MEASUREMENTS` 明确确认后执行。

---

# 31. Tool Contract

8 个业务 Tool：

```text
product_search_tool
selling_point_tool
size_recommend_tool
promotion_query_tool
logistics_query_tool
return_request_tool
exchange_request_tool
urge_shipping_tool
```

无：

```text
urge_order_payment_tool
chitchat_tool
```

Tool args 不含 user_id/token。

---

# 32. IntentFlow Contract

9 个 Flow：

```text
ProductQueryFlow
SizeRecommendFlow
UrgeOrderPaymentFlow
PromotionQueryFlow
LogisticsQueryFlow
ReturnFlow
ExchangeFlow
ChitchatFlow
ShippingFlow
```

LLM 不自由选择多个 Tool；Flow deterministic 编排。

---

# 33. Shipping Intent Contract

```text
什么时候发/怎么还没发 → urge_shipping informational
帮我催/快点发           → urge_shipping action_request
物流到哪/怎么还没到     → logistics_query informational
```

Order status 在 ShippingFlow 查询。

---

# 34. Urge Order Payment Contract

普通用户消息触发 Intent。

无 operator-action API。

无业务 Tool。

Flow 聚合商品/卖点/促销/用户需求/soft preferences，最终 LLM 生成个性化转化话术。

---

# 35. Size Runtime Contract

最终唯一正式算法：

```text
Range-Based Size Recommendation
```

不再要求：

```text
旧size_recommend.py输出不作为新实现的 compatibility gate
```

历史 `customer_service/tools/size_recommend.py` 只允许复用：

```text
单位normalize
参数校验
SKU helper
错误处理
有价值测试样本
```

最终计算 Service：

```python
class RangeBasedSizeRecommendationService:
    def recommend(
        self,
        measurements: dict[str, float],
        recommendation: SizeRecommendationPolicy,
    ) -> SizeRecommendationResult:
        ...
```

算法固定：

```text
required measurements完整?
→ 否：MISSING_MEASUREMENTS

按[min,max)检查每条Rule
→ 无match：NO_RANGE_MATCH
→ 有match：保留最高priority
→ 合并recommended_sizes并去重
→ 1个size：primary_size=该size
→ 多个size：primary_size=null
```

禁止：

```text
LLM算尺码
nearest-distance猜码
从成衣rows自动推导人体range
推荐码缺货后偷偷换成另一码
candidate[0]
```

服装与鞋类共用同一个 Range Matcher：

```text
服装Rule可返回 ["M"]
鞋类Rule可返回 ["39","40","41"]
```

精确 Measurements 优先级：

```text
current message
> session override
> confirmed Commerce measurements
```

长期保存：

```text
只有 explicit-confirmed 才 PATCH /api/v1/users/me/measurements
```

Range 数据属于 Commerce 商品业务数据；Agent 只做通用 deterministic evaluator。

---

# 36. RAG Runtime Contract

```text
Exact product → Commerce direct
Discovery → Adaptive Retrieval
```

```text
Stage1 Hybrid
→ insufficient Stage2 Multi-query
→ HyDE default OFF
→ Commerce truth validation
```

---

# 37. Memory Runtime Contract

```text
Commerce structured context
Redis checkpoint
Agent MySQL canonical semantic memory
Qdrant user_memory candidate index
```

Qdrant hit 必须 MySQL hydrate + user/status revalidate。

---

# 38. Dialogue Reasons：HTTP 200

```text
INTENT_UNRECOGNIZED
MULTIPLE_INTENTS
MISSING_REQUIRED_SLOT
REFERENCE_AMBIGUOUS
NEEDS_EXECUTION_CONFIRMATION
NOT_ELIGIBLE_FOR_ACTION
```

---

# 39. Runtime / HTTP Errors

```text
AUTH_INVALID_TOKEN
SESSION_NOT_FOUND
SESSION_CLOSED
TURN_IN_PROGRESS
TOOL_TIMEOUT
COMMERCE_UNAVAILABLE
IDEMPOTENCY_KEY_REUSED
REQUEST_IN_PROGRESS
BUSINESS_CONFLICT
GROUNDING_FAILED
```

---

# 40. Health

8001：

```text
GET /health/live
GET /health/ready
```

8000：同上。

Agent Critical dependencies：

```text
Agent MySQL
Redis
LLM
Commerce
```

Degradable：

```text
Qdrant
ES
TEI
Langfuse
```

---

# 41. Contract Test

开发期 CI 至少验证：

```text
关键path存在
OrderStatus enum
StockStatus enum
Order eligibility fields
SizeChart rows + recommendation.range rules schema
Range [min,max) semantics
Measurements PATCH semantics
Internal auth
Chat object schema
```

最终 E2E 通过后导出 v1.0 Snapshot。
