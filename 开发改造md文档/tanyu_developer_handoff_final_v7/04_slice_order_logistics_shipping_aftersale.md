# Vertical Slice 04：订单、物流、催发货、退货、换货与副作用幂等

> 文档版本：v7.0 — Developer Handoff Final  
> 日期：2026-09-22  
> 实施顺序：Size Slice 之后  
> 涉及工程：`ecommerce-service-backend:8001` + `customer-service-backend:8000`  
> 本文独立、自包含。完成后必须跑通 `logistics_query`、`urge_shipping`、`return`、`exchange`，并验证副作用 exactly-once。

---

# 1. 业务原则

```text
订单/物流/售后状态真值 → Commerce
用户意图/多轮槽位/任务切换 → Agent
真正副作用执行          → Commerce
副作用授权               → Agent ActionGuard + Commerce最终规则
```

Agent 不能复制：

```text
哪些订单可退
哪些可换
refund_amount
是否可催发货
```

Commerce 通过 Order Detail/Write API 给出最终事实。

---

# 2. OrderStatus 稳定 enum

API：

```text
pending_payment
pending_shipment
awaiting_pickup
in_transit
awaiting_receipt
completed
canceled
```

如果 DB 用中文：Commerce Service 层映射。

Response 可同时：

```text
status
status_label
```

Agent 只按 enum 判断。

---

# 2.1 Action / Confirmation Runtime Contract

```python
class ActionMode(str, Enum):
    INFORMATIONAL = "informational"
    ACTION_REQUEST = "action_request"

class ConfirmationKind(str, Enum):
    EXECUTE_RETURN = "execute_return"
    EXECUTE_EXCHANGE = "execute_exchange"
    CONFIRM_STORED_MEASUREMENTS = "confirm_stored_measurements"
    SAVE_MEASUREMENTS = "save_measurements"
```

本 Slice 的副作用语义：

```text
return   → ACTION_REQUEST + EXECUTE_RETURN final confirmation
exchange → ACTION_REQUEST + EXECUTE_EXCHANGE final confirmation
urge_shipping → ACTION_REQUEST，但不要求第二次 execute confirmation
INFORMATIONAL → write tool count 必须为 0
```

---

# 3. Orders API

```text
GET /api/v1/orders
GET /api/v1/orders/{order_id}
GET /api/v1/orders/{order_id}/logistics
```

所有 repository 查询必须带当前 user_id。

Non-owner/不存在统一 404。

---

# 4. Order Detail：Eligibility 由 Commerce 计算

Item：

```json
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
```

`active_after_sale`：

```json
{
  "type": "return",
  "request_id": "R1",
  "status": "submitted"
}
```

Eligibility 映射只存在 Commerce Service 中，不进入 Agent。

---

# 5. Logistics Contract

```json
{
  "order_id": "O2",
  "order_status": "in_transit",
  "latest_trace": {
    "status": "in_transit",
    "description": "快件到达转运中心",
    "time": "..."
  },
  "traces": []
}
```

`awaiting_pickup` 表示已经进入物流履约阶段，但可能尚未产生丰富轨迹；Agent 仍不得创建 shipping urge。

---

# 6. 催发货与物流 Intent 语义

固定：

| 表达 | Intent | ActionMode |
|---|---|---|
| 什么时候发货？ | urge_shipping | INFORMATIONAL |
| 今天能发吗？ | urge_shipping | INFORMATIONAL |
| 怎么还没发？ | urge_shipping | INFORMATIONAL |
| 帮我催一下 | urge_shipping | ACTION_REQUEST |
| 快点发货 | urge_shipping | ACTION_REQUEST |
| 物流到哪了？ | logistics_query | INFORMATIONAL |
| 怎么还没到？ | logistics_query | INFORMATIONAL |
| 物流怎么没更新？ | logistics_query | INFORMATIONAL |

真实订单状态不在 `intent_parse` 发 HTTP 查询。

---

# 7. LogisticsQueryFlow

```text
order_id
↓
logistics_query_tool
↓
Commerce get_logistics(user bearer)
↓
Evidence
↓
response
```

无 order_id：WAITING_SLOT。

---

# 8. ShippingStatusResolver

不是 Business Tool，是 `ShippingFlow` 内部普通 Service：

```python
class ShippingStatusResolver:
    async def resolve(order_id, ctx):
        order = await ecommerce.get_order(...)
        ...
```

分支：

```text
pending_shipment
→ PENDING_SHIPMENT

awaiting_pickup / in_transit / awaiting_receipt
→ ALREADY_IN_LOGISTICS
→ 需要时get_logistics

pending_payment / completed / canceled
→ NOT_ELIGIBLE
```

---

# 9. ShippingFlow

## INFORMATIONAL

```text
“什么时候发货？”
→ get_order
```

`pending_shipment`：

```text
只回答仍待发货
可提示“如果需要我可以帮您催一下”
create_shipping_urge = 0
```

已进入物流：

```text
get_logistics
→ 返回物流Evidence
create_shipping_urge = 0
```

## ACTION_REQUEST

```text
“我后天急用，帮我催一下”
```

`pending_shipment`：

```text
reason_detail整合urgency_context / expected_ship_time
→ urge_shipping_tool
```

已进入物流：

```text
不创建urge
→ logistics evidence
```

---

# 10. Shipping Urge Commerce API

```http
POST /api/v1/orders/{order_id}/shipping-urge-requests
Authorization: Bearer <USER_ACCESS_TOKEN>
Idempotency-Key: <stable-key>
```

Input：

```json
{
  "reason_code": "NORMAL_URGE",
  "reason_detail": "用户后天急用，希望尽快发出"
}
```

只允许：

```text
order.status=pending_shipment
```

不新增 `requested_deadline`。

---

# 11. Return Flow

## INFORMATIONAL

```text
“退货怎么办？”
“如果不合适能退吗？”
```

不要求：

```text
order_id/product_id/sku_id/reason
```

不调用 write Tool。

直接解释当前项目简化规则，必要时提示用户要真正办理时提供订单。

## ACTION_REQUEST

目标槽位：

```text
order_id
product_id
sku_id
reason
```

但优先 Commerce 反查：

```text
order_id
→ get_order
→ return_eligible items
```

1 个 eligible item：自动补 product/sku。

多个：输出 `order_item_choice` objects，让用户选择。

禁止 `items[0]`。

槽位完整：

```text
WAITING_CONFIRMATION(EXECUTE_RETURN)
```

用户确认：`return_request_tool`。

---

# 12. Return Commerce API

```http
POST /api/v1/orders/{order_id}/return-requests
Authorization: Bearer <USER_ACCESS_TOKEN>
Idempotency-Key: <stable-key>
```

Input：

```json
{
  "product_id": "15970",
  "sku_id": "SKU15970_02",
  "reason": "尺码太小"
}
```

Whole order-item semantics：

```text
不接 quantity
refund_amount = order_item.amount = price * quantity
```

Agent 不传、不计算 refund_amount。

---

# 13. Exchange Flow

INFORMATIONAL：

```text
“能换颜色吗？”
```

只说明流程，不启动写操作。

ACTION_REQUEST：

```text
“帮我换成黑色M”
```

目标：

```text
order_id
product_id
original_sku_id
target_color/target_size
exchange_sku_id
reason
```

流程：

```text
get_order
→ resolve original eligible item
→ Commerce get/filter product SKUs
→ target_color/size唯一匹配
→ exchange_sku_id
→ WAITING_CONFIRMATION(EXECUTE_EXCHANGE)
→ exchange_request_tool
```

多个 target SKU：澄清，不 `candidate[0]`。

---

# 14. Exchange Commerce API

```http
POST /api/v1/orders/{order_id}/exchange-requests
Authorization: Bearer <USER_ACCESS_TOKEN>
Idempotency-Key: <stable-key>
Content-Type: application/json
```

Request：

```json
{
  "product_id": "15970",
  "original_sku_id": "SKU15970_02",
  "exchange_sku_id": "SKU15970_03",
  "reason": "换大一码"
}
```

Success `200/201` data：

```json
{
  "exchange_request_id": "E1",
  "status": "submitted",
  "refund_amount": "0.00"
}
```

Commerce 最终验证：

```text
JWT.sub 拥有该 order
same product
target exists
target in_stock
exchange_eligible=true
no active conflict
refund_amount=0.00
```

错误语义：

```text
401 AUTH_INVALID_TOKEN
404 ORDER_NOT_FOUND
409 BUSINESS_CONFLICT
409 IDEMPOTENCY_KEY_REUSED
409 REQUEST_IN_PROGRESS
422 VALIDATION_ERROR
```

`404 ORDER_NOT_FOUND` 同时覆盖“不存在”和“非当前 JWT.sub 所有”；不得泄露订单是否属于其他用户。Write transport outcome uncertain 时，只允许使用**同一个** stable `Idempotency-Key` 最多重试 1 次。

---

# 14.1 IntentFlowRegistry 注册

以下 4 个 Flow 必须注册到全项目唯一的 `customer_service/flows/registry.py`；禁止建立第二个 Registry：

```python
FLOW_REGISTRY.update({
    BusinessIntent.LOGISTICS_QUERY: LogisticsQueryFlow(...),
    BusinessIntent.RETURN: ReturnFlow(...),
    BusinessIntent.EXCHANGE: ExchangeFlow(...),
    BusinessIntent.URGE_SHIPPING: ShippingFlow(...),
})
```

最终这些 Intent 均通过同一个 `IntentFlowRegistry.get()` 解析。订单业务 Tool 注册在 `customer_service/tools/registry.py`，Flow Registry 与 Tool Registry 职责必须分开。

---

# 15. Tool Runtime 与 4 个订单 Tool

本 Slice 使用：

```text
logistics_query_tool
urge_shipping_tool
return_request_tool
exchange_request_tool
```

统一通过 ToolRuntime：

```text
registry
→ intent allowlist
→ args schema
→ action guard
→ deadline
→ semaphore
→ timeout
→ execute
→ retry policy
→ result schema
→ Tool Output Guard
→ Evidence
→ trace
```

---

# 16. Retry 规则

Read：

```text
connect/read timeout
502/503/504
→ 最多1次
```

业务 4xx：不 retry。

Write：

```text
只有transport outcome uncertain
+ 相同stable Idempotency-Key
→ 最多1次
```

不能换 key 重试。

---

# 17. Stable Idempotency-Key

Agent 生成：

```text
payload_hash = SHA256(canonical business payload)

UUIDv5(
  namespace,
  user_id + task_id + action_type + payload_hash
)
```

不包含：

```text
turn_id
request_id
timestamp
随机数
```

同一 Task 跨 Turn 重试仍相同 key。

---

# 18. Commerce Idempotency Transaction

推荐：

```text
BEGIN
  INSERT idempotency PROCESSING
  validate business
  create business resource
  UPDATE idempotency COMPLETED + response
COMMIT
```

异常：ROLLBACK。

并发相同 key：

```text
T2等待unique/lock
→ T1成功commit
→ T2读取COMPLETED
→ replay
```

锁等待超时可映射 `REQUEST_IN_PROGRESS`。

不需要长期 FAILED 状态和僵尸记录清理系统。

---

# 19. ActionReceipt 持久化

副作用成功后，**先持久化结果，再向客户端发送最终成功文本**：

```text
Tool write success
→ Task COMPLETED
→ assistant chat_message.content
→ objects_json.action_receipt
→ commit Agent DB
→ response / SSE final
```

这样即使 SSE 断开：

```text
GET chat history
```

仍可看到已完成操作。

`action_receipt`：

```json
{
  "type": "action_receipt",
  "action": "return",
  "resource_id": "R1",
  "status": "submitted",
  "order_id": "O1",
  "refund_amount": "299.90"
}
```

只有 return 包含 Commerce 返回的 refund_amount。

---

# 20. Task 中断/恢复经典场景

```text
T1 我要退货
→ WAITING_SLOT order

T2 O1001
→ eligible item自动解析
→ WAITING_SLOT reason

T3 先帮我查O2002到哪了
→ pause return
→ logistics task
→ 完成
→ resume return WAITING_SLOT
→ 仅提示“刚才退货还差原因”

T4 尺码太小
→ continue return
→ WAITING_CONFIRMATION

T5 确认
→ return write
```

测试必须完整覆盖。

---

# 21. 用户隔离

Tool args 不含 user_id。

EcommerceClient 使用当前 Access JWT。

即使用户输入别人的 order_id：

```text
8001 WHERE order_id=? AND user_id=JWT.sub
→ 404
```

双层保护：Agent scope + Commerce ownership。

---

# 22. 具体文件

## Commerce

```text
app/api/public/orders.py
app/api/public/after_sale.py
app/repositories/order.py
app/repositories/after_sale.py
app/repositories/idempotency.py
app/services/order.py
app/services/after_sale.py
app/schemas/orders.py
app/schemas/after_sale.py
app/models/idempotency.py
```

## Agent

```text
customer_service/flows/logistics.py
customer_service/flows/shipping.py
customer_service/flows/return_flow.py
customer_service/flows/exchange.py
customer_service/service/shipping_status_resolver.py

customer_service/tools/logistics_query.py
customer_service/tools/urge_shipping.py
customer_service/tools/return_request.py
customer_service/tools/exchange_request.py
customer_service/tools/runtime.py
customer_service/tools/idempotency.py
customer_service/tasking/manager.py
customer_service/tasking/confirmation.py
customer_service/chat/service.py
```

---

# 23. Dialogue Reason vs HTTP Error

以下是正常 200 对话：

```text
MISSING_REQUIRED_SLOT
REFERENCE_AMBIGUOUS
MULTIPLE_INTENTS
NEEDS_EXECUTION_CONFIRMATION
NOT_ELIGIBLE_FOR_ACTION
```

不是 HTTP error。

真正 runtime error：

```text
AUTH_INVALID_TOKEN
SESSION_NOT_FOUND
SESSION_CLOSED
TOOL_TIMEOUT
COMMERCE_UNAVAILABLE
BUSINESS_CONFLICT
```

---

# 24. Slice 测试

## Commerce Integration

```text
OrderStatus mapping
ownership
eligibility fields
logistics latest trace
return refund formula
exchange same product/stock
shipping only pending_shipment
idempotency concurrent replay
```

## Agent Unit/Component

```text
ShippingStatusResolver
INFORMATIONAL副作用=0
Return/Exchange SlotPolicy
multi-item no candidate[0]
Task confirmation
stable idempotency key
```

## Slice E2E

必须：

```text
logistics_query
urge_shipping informational pending
urge_shipping informational already shipped
urge_shipping action pending
urge_shipping action already in logistics
return informational
return action single item
return action multi item
exchange action
return→logistics→return interruption
副作用timeout+same-key retry exactly once
cross-user order attack
```

---

# 25. Completion Gate

```text
OrderStatus稳定enum
eligibility由Commerce返回
logistics完整
urge_shipping语义正确
awaiting_pickup不会误催发货
return/exchange informational不追问执行槽位
ACTION_REQUEST需要正确确认
multi-item不自动选第一条
refund只由Commerce计算
write stable idempotency exactly-once
副作用成功先持久化action receipt
跨用户订单访问=0 leak
```
