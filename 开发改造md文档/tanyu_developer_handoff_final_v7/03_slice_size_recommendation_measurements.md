# Vertical Slice 03：Range-Based Size Recommendation 与 Measurements

> 文档版本：v7.0 — Developer Handoff Final  
> 日期：2026-09-22  
> 实施顺序：Product Slice 之后  
> 涉及工程：`ecommerce-service-backend:8001` + `customer-service-backend:8000`  
> 本文独立、自包含。完成后必须实现基于“用户适配范围”的确定性尺码推荐，以及 Measurements 的确认、Session Override 和显式长期保存。

---

# 1. 本 Slice 的最终决策

本项目的 Size Recommendation 统一采用：

```text
Range-Based Size Recommendation
```

明确不做：

```text
不接 Faslet / True Fit / Cabina 等外部 Size MCP
不训练新的 Size ML 模型
不让 LLM 计算尺码
不继承未正式定义的历史 size_recommend.py 算法 Contract
不让开发者自行发明新的隐式公式
```

当前历史文件：

```text
customer_service/tools/size_recommend.py
```

只允许用于识别可复用的：

```text
单位换算
Pydantic / 参数校验
错误处理
SKU筛选辅助逻辑
已有测试数据
```

历史算法行为**不是**新版本算法真值，也不再要求 characterization test 与旧输出完全一致。

新版本算法真值只有：

```text
Commerce 商品推荐范围数据
+
RangeBasedSizeRecommendationService 的确定性范围匹配规则
```

---

# 2. 为什么把“商品尺码表”和“用户适配范围”分开

现有商品尺码表中的：

```text
M：胸围92 / 腰围76 / 肩宽39
```

描述的是商品或尺码规格，不等价于：

```text
人体胸围92cm → 必然应该选M
```

尺码推荐还会受到：

```text
商品版型
松量
面料弹性
品牌尺码策略
商品自身推荐规则
```

影响。

因此最终必须分成两类 Commerce 数据：

```text
A. SizeChart rows
→ 商品尺码事实
→ 展示给用户

B. recommendation rules
→ 用户身体数据适配范围
→ 给 RangeBasedSizeRecommendationService 做确定性推荐
```

Agent 不从 SizeChart 的成衣具体数值“猜”用户应该穿什么码。

---

# 3. 最终职责

```text
Commerce :8001
→ Product SizeChart 真值
→ Product Recommendation Range 真值
→ SKU / Price / Stock 真值
→ user_measurements 持久化真值

Agent :8000
→ Measurements 当前上下文
→ RangeBasedSizeRecommendationService
→ 范围匹配
→ SKU / Stock 再验证
→ 多轮询问 / 确认 / 解释

LLM
→ 只负责语言理解与自然语言表达
→ 不参与尺码数学计算
```

---

# 4. Commerce Measurements Contract

```http
GET   /api/v1/users/me/measurements
PATCH /api/v1/users/me/measurements
```

用户身份只能来自 Access JWT `sub`。

PATCH 示例：

```json
{
  "weight_kg": 57
}
```

语义固定：

```text
请求中缺失字段 → 保持原值
显式 null → HTTP 422
值 <= 0 → HTTP 422
```

当前至少支持：

```text
height_cm
weight_kg
bust_cm
waist_cm
hip_cm
shoulder_cm
```

如果后续 Range Rules 真正需要新的**用户身体字段**，必须作为 coordinated contract change 同步：

```text
8001 Schema
8001 DB
07 API Contract
8000 Normalizer / Models
本 Slice Tests
08 E2E
```

商品的：

```text
pants_length_cm
skirt_length_cm
garment_bust_cm
```

不是用户身体 Measurements，不应混入 `user_measurements`。

---

# 5. Commerce SizeChart + Recommendation Contract

```http
GET /api/v1/catalog/products/{product_id}/size-chart
```

商品不存在：

```text
404 PRODUCT_NOT_FOUND
```

`available` 只表示“商品尺码表 rows 是否可用”，不表示推荐 Range 是否可用。

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

商品有尺码表但没有配置推荐 Range：

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

此时可以展示尺码表，但 Agent 不做自动尺码推荐。

完整示例：

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
          "height_cm": {
            "min": 150,
            "max": 160
          },
          "weight_kg": {
            "min": 40,
            "max": 48
          }
        },
        "recommended_sizes": ["S"]
      },
      {
        "rule_id": "R-M",
        "priority": 100,
        "conditions": {
          "height_cm": {
            "min": 160,
            "max": 168
          },
          "weight_kg": {
            "min": 48,
            "max": 55
          }
        },
        "recommended_sizes": ["M"]
      }
    ]
  },
  "size_chart_url": "/static/size-images/15970.jpg"
}
```

核心：

```text
rows
→ 商品尺码事实

recommendation.required_measurements
→ Agent需要哪些用户Measurements

recommendation.rules
→ 用户Measurements到推荐尺码的正式业务数据
```

---

# 6. Range Condition 的固定数学语义

每个字段 Range：

```json
{
  "min": 48,
  "max": 55
}
```

统一解释为：

```text
[min, max)
```

即：

```text
min inclusive
max exclusive
```

所以：

```text
48kg → 命中
54.999kg → 命中
55kg → 不命中
```

如果：

```text
min = null
```

表示无下界。

如果：

```text
max = null
```

表示无上界。

这样不需要：

```text
min_inclusive
max_inclusive
```

等额外字段。

一个 Rule 中多个 `conditions` 使用：

```text
AND
```

例如：

```text
height命中
AND
weight命中
```

才算该 Rule 匹配。

---

# 7. Range Rule 数据校验

Commerce 在 import / startup data validation / API serialization 前必须验证：

```text
policy == range_match
required_measurements 非空
rules 非空
rule_id 在 product 内唯一
priority 为整数
recommended_sizes 非空
conditions 的字段必须属于允许的 measurement field
conditions 中至少有一个字段
min/max 至少一个非 null
同时非 null 时 min < max
recommended_sizes 必须存在于该商品 SizeChart / SKU size_code 集合中
```

非法数据：

```text
导入/测试阶段 fail-fast
```

不能等用户问尺码时才发现。

---

# 8. RangeBasedSizeRecommendationService

最终只保留一个通用算法 Service：

```python
class RangeBasedSizeRecommendationService:
    def recommend(
        self,
        measurements: dict[str, float],
        recommendation: SizeRecommendationPolicy,
    ) -> SizeRecommendationResult:
        ...
```

不再创建：

```text
HeightWeightSingleSizeRule
BodyMeasurementSingleSizeRule
HeightWeightThreeCandidatesRule
```

等平行算法类。

不同商品差异放在：

```text
recommendation.rules
```

中，不放在 Agent 的品类 if/else 中。

---

# 9. 算法步骤

固定：

```text
1. 验证 policy=range_match

2. 读取 required_measurements

3. 检查用户是否缺字段
   ├─ 缺 → missing_measurements
   └─ 不缺 → 继续

4. 遍历 rules
   → 每个condition按 [min,max) 判断
   → 所有condition均满足才匹配

5. 得到 matched_rules

6. 无匹配
   → NO_RANGE_MATCH
   → 不强行推荐

7. 有匹配
   → 找最高 priority
   → 只保留最高 priority rules

8. 合并这些 rules 的 recommended_sizes
   → 去重
   → 保持规则声明顺序

9. 若最终只有1个size
   → primary_size=该size

10. 若最终>1个size
    → primary_size=null
    → recommended_sizes保留全部候选

11. 返回确定性结果

12. Tool 再调用 Commerce SKU/Stock Truth
```

注意：

```text
不能 candidates[0]
不能用最近距离猜一个size
不能因为某推荐尺码缺货就改推荐另一码
```

---

# 10. Priority 的用途

正常数据尽量设计成：

```text
范围互不冲突
```

`priority` 只用于少数业务覆盖规则。

例如：

```text
普通规则 priority=100
特殊商品修正规则 priority=200
```

如果多个最高 priority Rule 同时匹配：

```text
合并 recommended_sizes
primary_size=null（除非合并后只有一个唯一size）
reason_code=AMBIGUOUS_RANGE_MATCH
```

Agent 必须如实告诉用户存在多个候选，不强行选一个。

---

# 11. SizeRecommendationResult

```python
class SizeRecommendationResult(BaseModel):
    primary_size: str | None
    recommended_sizes: list[str]

    used_measurements: dict[str, float]
    missing_measurements: list[str]

    matched_rule_ids: list[str]
    reason_codes: list[str]

    matching_skus: list[SkuCandidate]
    size_chart_url: str | None
```

关键 Reason Code：

```text
MATCHED
MISSING_MEASUREMENTS
NO_RANGE_MATCH
AMBIGUOUS_RANGE_MATCH
RECOMMENDED_SIZE_OUT_OF_STOCK
SIZE_RECOMMENDATION_UNAVAILABLE
```

---

# 12. 服装与鞋类使用同一算法

## 服装

Rule：

```json
{
  "conditions": {
    "height_cm": {"min": 160, "max": 168},
    "weight_kg": {"min": 48, "max": 55}
  },
  "recommended_sizes": ["M"]
}
```

结果：

```text
primary_size=M
recommended_sizes=[M]
```

## 鞋类

如果项目当前业务要求：

```text
身高 + 体重
→ 3个具体候选尺码
```

只需要 Rule：

```json
{
  "conditions": {
    "height_cm": {"min": 165, "max": 175},
    "weight_kg": {"min": 55, "max": 65}
  },
  "recommended_sizes": ["39", "40", "41"]
}
```

结果：

```text
primary_size=null
recommended_sizes=[39,40,41]
```

不需要新的鞋类算法类。

---

# 13. Body Measurements 同样走 Range Rules

如果某商品确实需要：

```text
bust_cm
shoulder_cm
```

Commerce 返回：

```json
{
  "required_measurements": [
    "bust_cm",
    "shoulder_cm"
  ],
  "rules": [
    {
      "rule_id": "R-M",
      "priority": 100,
      "conditions": {
        "bust_cm": {"min": 84, "max": 90},
        "shoulder_cm": {"min": 36, "max": 39}
      },
      "recommended_sizes": ["M"]
    }
  ]
}
```

Agent 无需：

```python
if category == "shirt":
    ...
```

只按 `required_measurements` 收集和匹配。

---

# 14. Recommendation Rules 的 Commerce 持久化

为了保持简单，不新建 Size Rule 平台。

在 `products` 增加一个可空 MySQL `JSON` 字段：

```text
size_recommendation_rules JSON NULL
```

内容只存：

```text
policy
required_measurements
rules
```

例如：

```json
{
  "policy": "range_match",
  "required_measurements": ["height_cm", "weight_kg"],
  "rules": [...]
}
```

数据库类型固定为 MySQL `JSON`；不要在开发者之间出现 JSON/TEXT 两种实现分支。

`rows` 继续由现有商品 size 数据生成，不重复存两份 SizeChart。

当前版本：

```text
不建通用Rule Engine
不建Rule Version系统
不建Admin配置后台
```

---

# 15. 推荐范围数据来源

推荐范围是**业务数据**，不是 Agent 自动生成的数据。

开发数据准备时：

```text
为所有需要 size_recommend 的 demo 商品明确配置 range rules
```

不得：

```text
从成衣胸围/腰围自动猜人体适配范围
用LLM自动生成ranges并直接入库
运行时根据SizeChart rows即时推导ranges
```

如果商品：

```text
没有 range rules
```

则：

```text
recommendation=null
```

Agent 返回：

```text
SIZE_RECOMMENDATION_UNAVAILABLE
```

可以展示尺码表，但不声称已经可靠推荐尺码。

---

# 16. `size_recommend_tool` 的职责

仍保留业务 Tool：

```text
size_recommend_tool
```

因为它组合真实外部 I/O 与业务计算。

流程：

```text
get_size_chart(product_id)
↓
读取 recommendation
↓
组装 CurrentMeasurementContext
↓
RangeBasedSizeRecommendationService
↓
get/filter SKUs
↓
Stock Truth
↓
Evidence
```

Tool 不接：

```text
user_id
access_token
```

这些由 RuntimeContext / EcommerceClient 注入。

---

# 17. SKU 匹配

如果：

```text
recommended_sizes=[M]
```

商品有：

```text
黑色M
白色M
藏青M
```

返回：

```text
matching_skus = 3条
```

不要：

```text
selected_sku=candidates[0]
```

只有用户当前条件已经使 SKU 唯一，例如：

```text
color=黑色
size=M
```

才允许附：

```text
selected_sku_id
```

---

# 18. 缺货语义

算法推荐：

```text
M
```

但所有 M SKU：

```text
out_of_stock
```

推荐结果仍然是：

```text
M
```

不能自动改成：

```text
L
```

并说 L 也适合。

返回：

```text
reason_codes += RECOMMENDED_SIZE_OUT_OF_STOCK
```

Agent 可以：

```text
展示相邻可售SKU
```

但必须明确：

> 这些是库存候选，不是 Range Matcher 验证后的等价推荐尺码。

---

# 19. 用户 Measurements 单位规范化

确定性：

```text
165cm → 165cm
1.65m → 165cm
52kg → 52kg
104斤 → 52kg
```

固定：

```text
1斤 = 0.5kg
```

LLM 不承担主数值换算。

Normalization 可以保留：

```text
original_text
normalized_value
```

供调试 / Langfuse 脱敏 metadata 使用。

---

# 19.1 Confirmation Runtime Contract

本 Slice 使用项目统一的 `ConfirmationKind`；完整 enum 固定为：

```python
class ConfirmationKind(str, Enum):
    EXECUTE_RETURN = "execute_return"
    EXECUTE_EXCHANGE = "execute_exchange"
    CONFIRM_STORED_MEASUREMENTS = "confirm_stored_measurements"
    SAVE_MEASUREMENTS = "save_measurements"
```

本文实际使用 `CONFIRM_STORED_MEASUREMENTS` 与 `SAVE_MEASUREMENTS`。`PendingConfirmation` 只允许存在于 `TaskFrame.pending_confirmation`，不得在 AgentState 顶层保存第二份。

---

# 20. SessionUserContext

```python
class SessionUserContext(BaseModel):
    measurement_overrides: dict[str, float]
    confirmed_measurement_fields: set[str]
```

不使用：

```text
stored_measurements_confirmed: bool
```

因为：

```text
确认 height/weight
≠
确认 bust/waist/hip
```

---

# 21. Measurements 使用优先级

精确数值固定：

```text
当前用户消息明确值
>
Session measurement_overrides
>
Commerce user_measurements 中“本Session已确认”的字段
```

Agent semantic memory：

```text
不作为精确尺码计算真值
```

---

# 22. 场景一：首次用户

用户：

```text
“这件衬衫我穿什么码？”
```

流程：

```text
intent=size_recommend
↓
resolve product
↓
get size chart
↓
recommendation.required_measurements
↓
Commerce measurements缺失
↓
WAITING_SLOT
```

Agent 只问实际缺的字段。

例如：

> “这款需要身高和体重才能推荐尺码，请告诉我您的身高和体重。”

用户：

```text
“165cm，52kg”
```

流程：

```text
normalize
↓
measurement_overrides
↓
RangeBasedSizeRecommendationService
↓
命中规则
↓
SKU truth
↓
推荐
↓
WAITING_CONFIRMATION(SAVE_MEASUREMENTS)
```

用户：

```text
“可以”
```

→ PATCH Commerce。

用户：

```text
“不用”
```

→ Commerce 不变，当前 Session override 保留。

首次提供 Measurements **不等价于长期保存授权**。

---

# 23. 场景二：老用户确认历史 Measurements

Commerce：

```text
height_cm=165
weight_kg=52
```

本 Session 第一次需要：

```text
height_cm
weight_kg
```

Agent：

> “我这边记录的身高/体重是165cm/52kg，这两个数据现在还适用吗？”

用户：

```text
“对”
```

结果：

```text
confirmed_measurement_fields +=
{height_cm, weight_kg}
```

然后继续 Range Matcher。

同 Session 再需要：

```text
height/weight
```

不重复确认。

若另一商品需要：

```text
waist/hip
```

只处理还没确认的字段。

---

# 24. 场景三：历史值变化

Commerce：

```text
height=165
weight=52
```

用户：

```text
“不对，我现在57kg”
```

结果：

```text
measurement_overrides.weight_kg=57
confirmed_measurement_fields.add("weight_kg")
```

当前推荐：

```text
使用57kg
```

Commerce：

```text
仍然52kg
```

推荐完成后：

> “需要我把资料里的体重更新为57kg吗？”

确认才 PATCH。

---

# 25. 用户直接明确长期修改

用户：

```text
“把体重改成57kg，以后按这个推荐”
```

这是 explicit persistence intent：

```text
不再重复二次确认
→ UserContextWriteService.patch_measurements()
```

成功后：

```text
measurement_overrides.weight_kg=57
confirmed_measurement_fields包含weight_kg
```

---

# 26. Task 生命周期

尺码已推荐，但还在问是否保存：

```text
Task.status=WAITING_CONFIRMATION
Task.pending_confirmation.kind=SAVE_MEASUREMENTS
```

不能先 `COMPLETED`。

用户：

```text
YES
→ PATCH
→ COMPLETED

NO
→ 不PATCH
→ COMPLETED
```

确认期间用户切换其他任务：

```text
pause size task
→ 执行新task
→ 完成
→ resume size WAITING_CONFIRMATION
```

同一个 Turn 恢复后只提示下一步，不继续自动执行第二个业务动作。

---

# 26.1 IntentFlowRegistry 注册

`SizeRecommendFlow` 必须注册到全项目唯一的：

```text
customer_service/flows/registry.py
```

不得创建第二个 Size Registry 或局部 Registry。注册结果：

```python
FLOW_REGISTRY.update({
    BusinessIntent.SIZE_RECOMMEND: SizeRecommendFlow(...),
})
```

最终 `IntentFlowRegistry.get(BusinessIntent.SIZE_RECOMMEND)` 必须返回这一正式 Flow；`size_recommend_tool` 仍由 ToolRegistry 注册，两类 Registry 不得混用。

---

# 27. SizeRecommendFlow

```text
resolve product
↓
get size chart
↓
recommendation?
├─ NO
│  → SIZE_RECOMMENDATION_UNAVAILABLE
│  → 不猜尺码
│  → available=true时仍可展示SizeChart
└─ YES
    ↓
required_measurements
    ↓
CurrentMeasurementContext
    ├─ 缺字段
    │  → WAITING_SLOT
    │
    ├─ Commerce字段未确认
    │  → WAITING_CONFIRMATION(CONFIRM_STORED_MEASUREMENTS)
    │
    └─ 当前值完整
         ↓
      size_recommend_tool
         ↓
      RangeBasedSizeRecommendationService
         ↓
      matching SKUs / stock
         ↓
      response
         ↓
      若出现新Measurements且未明确长期保存
         → WAITING_CONFIRMATION(SAVE_MEASUREMENTS)
```

---

# 28. ChatObject

```json
{
  "type": "size_recommendation",
  "product_id": "15970",
  "primary_size": "M",
  "recommended_sizes": ["M"],
  "matching_skus": [
    {
      "sku_id": "SKU15970-BLK-M",
      "color": "黑色",
      "size_code": "M",
      "stock_status": "in_stock"
    }
  ],
  "used_measurements": {
    "height_cm": 165,
    "weight_kg": 52
  },
  "matched_rule_ids": ["R-M"],
  "reason_codes": ["MATCHED"],
  "size_chart_url": "/static/size-images/15970.jpg"
}
```

对用户返回的 Measurements 只包含本次推荐实际使用字段。

---

# 29. UserContextWriteService

它不是 LLM Tool。

```text
用户明确确认保存
↓
UserContextWriteService
↓
EcommerceClient.patch_measurements()
```

统一路径：

```text
customer_service/service/user_context_write_service.py
```

不创建：

```text
customer_service/services/
```

平行目录。

Measurements PATCH 成功后统一持久化 `action_receipt`：

```json
{
  "type": "action_receipt",
  "action": "save_measurements",
  "resource_id": null,
  "status": "updated",
  "order_id": null,
  "refund_amount": null
}
```

`resource_id` 对 `save_measurements` 必须为 `null`，因为 PATCH 只是更新用户 Measurements，不创建新的业务 resource。

---

# 30. Commerce 实现修改

涉及：

```text
app/models/product.py
app/repositories/product.py
app/services/catalog.py
app/schemas/catalog.py
app/api/public/catalog.py

app/repositories/user.py
app/services/user.py
app/schemas/users.py
app/api/public/user.py

scripts/import_data.py
```

协调 Contract 变更：

```text
products 增加 nullable:
size_recommendation_rules JSON
```

CSV / 导入源如果采用 JSON 字符串字段：

```text
size_recommendation_rules
```

必须在 import 阶段校验，不允许无效 JSON 静默入库。

---

# 31. Agent 实现修改

修改：

```text
customer_service/tools/size_recommend.py
customer_service/flows/size.py
customer_service/slots/size_policy.py
customer_service/service/user_context_write_service.py
customer_service/tasking/confirmation.py
customer_service/graph/state.py
```

新增/整理：

```text
customer_service/size/models.py
customer_service/size/normalization.py
customer_service/size/service.py
```

`service.py` 中只有：

```text
RangeBasedSizeRecommendationService
```

不建立通用 Rule Engine / Provider Plugin Framework。

---

# 32. 旧 `size_recommend.py` 如何处理

开发开始时先阅读历史文件：

```text
customer_service/tools/size_recommend.py
```

只做：

```text
识别可复用normalization
识别已有SKU helper
识别错误处理
识别有价值的测试样本
```

不要求：

```text
新实现输出与旧算法逐条一致
```

最终旧 Tool 必须变薄：

```text
Commerce I/O
→ RangeBasedSizeRecommendationService
→ SKU Truth
→ Evidence
```

旧的隐式算法分支应删除，避免同一个项目存在两套尺码真值。

---

# 33. Size Recommendation Contract Tests

不再写：

```text
characterization test = 最终算法真值
```

改成：

```text
Range-Based Size Recommendation Contract Tests
```

建议：

```text
tests/unit/size/test_range_matcher.py
tests/component/size/test_size_flow.py
tests/integration/size/test_size_commerce_contract.py
```

必须覆盖：

```text
单字段range
多字段AND
min inclusive
max exclusive
无下界
无上界
单Rule命中
无Rule命中
多个最高priority Rule命中
recommended_sizes去重
服装单size
鞋类3个size
缺required measurement
非法rule数据
推荐尺码缺货
多颜色matching_skus
```

---

# 34. Commerce Slice Tests

必须：

```text
GET size-chart 返回 recommendation object
rules schema validation
recommended_sizes必须属于商品合法size
无recommendation时 recommendation=null
Measurements PATCH partial update
Measurements explicit null → 422
商品不存在 → 404
SKU truth
```

---

# 35. Measurements E2E

必须覆盖：

```text
首次用户
→ 提供值
→ Range Matcher
→ 推荐
→ 保存YES

首次用户
→ 推荐
→ 保存NO

老用户
→ 历史字段首次确认
→ 推荐

老用户
→ 某字段变化
→ session override
→ 推荐
→ 不保存

用户明确“以后按57kg”
→ 直接PATCH
```

---

# 36. Range Matcher E2E

至少固定测试商品：

## Clothing Single Size

```text
rule:
height [160,168)
weight [48,55)
→ M

input:
165 / 52

expected:
recommended_sizes=[M]
primary_size=M
```

## Boundary

```text
M weight [48,55)
L weight [55,62)

55kg
→ 不命中M
→ 可命中L（若其他conditions满足）
```

## Shoes Three Candidates

```text
rule
→ [39,40,41]

expected:
primary_size=null
recommended_sizes=[39,40,41]
```

## No Match

```text
recommended_sizes=[]
primary_size=null
reason=NO_RANGE_MATCH
```

Agent 不猜。

---

# 37. Langfuse

稳定 observation：

```text
flow.size_recommend
tool.size_recommend
size.range_match
size.commerce_sku_validation
measurements.confirmation
measurements.writeback
```

推荐记录：

```text
required_measurement_fields
matched_rule_count
matched_rule_ids
recommended_size_count
reason_codes
duration
```

默认不上传完整长期 Measurements。

---

# 38. 不允许扩展范围

本 Slice 不做：

```text
第三方Size MCP
Size ML训练
基于LLM的尺码计算
自动从成衣尺寸推导人体范围
nearest-distance尺码算法
复杂打分/权重系统
通用Rule Engine
Rule管理后台
Rule版本平台
```

---

# 39. Completion Gate

只有全部满足才完成：

```text
Range-Based Size Recommendation 成为唯一正式算法Contract

Commerce明确返回：
rows
recommendation.required_measurements
recommendation.rules

Range数学语义固定为[min,max)

RangeBasedSizeRecommendationService为唯一计算Service

旧size_recommend.py中的隐式算法不再作为第二套真值

服装单size范围匹配通过

鞋类同一Range Matcher输出3个具体候选size

无match不强行推荐

重叠最高priority规则不candidate[0]

matching_skus不candidate[0]

推荐尺码缺货不改写推荐结论

Measurements字段级确认成立

Session Override成立

只有显式授权才PATCH长期Measurements

Range Contract Tests通过

Slice E2E通过
```
