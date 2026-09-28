# 最终验收：Cross-Service E2E、Recovery、Evaluation 与 v1.0 Contract Freeze

> 文档版本：v7.0 — Developer Handoff Final  
> 日期：2026-09-22  
> 实施顺序：所有 Vertical Slice 完成之后  
> 本文独立、自包含。只有本文全部 Gate 通过，Phase 1 + Phase 2 核心项目才允许标记为完成并冻结 v1.0 Contract。

---

# 1. 测试环境

真实隔离依赖：

```text
MySQL:
  ecommerce_test_db
  customer_service_test_db

Redis 8+
Qdrant
Elasticsearch
TEI / BGE-M3
ecommerce-service-backend :8001
customer-service-backend  :8000
Langfuse test project/environment
```

测试配置必须显式：

```text
TEST_ECOMMERCE_ASYNC_DATABASE_URL
TEST_AGENT_ASYNC_DATABASE_URL
PRODUCT_QDRANT_COLLECTION=product_knowledge_test
USER_MEMORY_QDRANT_COLLECTION=user_memory_test
PRODUCT_ES_INDEX=product_knowledge_test
LANGFUSE_ENVIRONMENT=test
```

禁止测试指向开发/生产业务库。

---

# 2. Deterministic E2E Fixture

Commerce 提供：

```bash
python -m tests.support.prepare_e2e
```

生成：

```text
contracts/fixtures/ecommerce_e2e_manifest.json
```

Manifest 必须至少定义这些稳定 alias：

```text
USER_A
USER_B
PRODUCT_AVAILABLE
PRODUCT_OOS
ORDER_PENDING_SHIPMENT
ORDER_AWAITING_PICKUP
ORDER_IN_TRANSIT
ORDER_RETURN_ELIGIBLE
ORDER_MULTI_ITEM
ORDER_EXCHANGE_ELIGIBLE
ORDER_ALREADY_HAS_AFTERSALE

SIZE_PRODUCT_SINGLE_RANGE
SIZE_PRODUCT_SHOES_THREE
SIZE_PRODUCT_BOUNDARY
SIZE_PRODUCT_AMBIGUOUS_RANGE
SIZE_PRODUCT_NO_MATCH
SIZE_PRODUCT_RECOMMENDED_OOS
SIZE_PRODUCT_RECOMMENDATION_UNAVAILABLE
```

Size alias 与 Case 的固定对应：

| Alias | 固定用途 |
|---|---|
| `SIZE_PRODUCT_SINGLE_RANGE` | 首次用户/历史值确认/override 的标准单尺码命中 |
| `SIZE_PRODUCT_SHOES_THREE` | 一个 Range Rule 返回 3 个具体鞋码 |
| `SIZE_PRODUCT_BOUNDARY` | 验证 `[min,max)`，例如 55kg 不命中 `[48,55)` |
| `SIZE_PRODUCT_AMBIGUOUS_RANGE` | 两个最高 priority Rule 同时命中并合并候选 |
| `SIZE_PRODUCT_NO_MATCH` | measurements 不命中任何 Rule |
| `SIZE_PRODUCT_RECOMMENDED_OOS` | 推荐尺码存在但对应 SKU 全部缺货 |
| `SIZE_PRODUCT_RECOMMENDATION_UNAVAILABLE` | SizeChart 可用但 `recommendation=null` |

Manifest 中 alias 必须解析到 seed 产生的真实 ID；测试代码只消费 alias，不自行硬编码 product/order/user ID。允许多个 alias 指向同一 product_id，但必须通过固定 seed/rule/input 明确区分 Case。

每个 write test suite 前 reset/seed，避免案例相互污染。

---

# 3. 基础链路

```text
8001 login
→ Access JWT
→ 8000 create chat session
→ send message
→ graph
→ chat history
```

断言：

```text
request_id贯穿
chat messages持久化
LangGraph checkpoint存在
Langfuse trace存在（live_langfuse suite）
```

---

# 4. 9 Intent E2E 覆盖

最终必须一一覆盖：

```text
1 product_query
2 size_recommend
3 urge_order_payment
4 promotion_query
5 logistics_query
6 return
7 exchange
8 chitchat
9 urge_shipping
```

不允许“9类支持”但 E2E 只测 7 类。

---

# 5. Product Query E2E

## Exact

```text
已知product_id问价格/SKU
→ 不调用RAG
→ Commerce direct
```

## Discovery

```text
“想要黑色通勤连衣裙，预算400”
→ Hybrid RAG
→ Commerce truth
→ product_card
```

断言：动态 price/stock 与 MySQL 一致。

---

# 6. Promotion E2E

不同用户等级：

```text
promotion result不同
```

无活动：正常空结果。

---

# 7. Urge Order Payment E2E

用户：

```text
“这件有点贵，我再考虑一下”
```

前置唯一 focused product。

断言：

```text
intent=urge_order_payment
无operator action API
无urge_order_payment_tool
聚合卖点/促销/需求/soft personalization
生成个性化话术
无Commerce write
```

记录端到端 latency p50/p95。

---

# 8. Chitchat E2E

无 active task：普通闲聊。

有 return WAITING_SLOT 时：

```text
“哈哈谢谢”
→ 不创建长期chitchat task
→ return仍存在
```

---

# 9. Size E2E：首次用户

固定测试商品：

```text
SIZE_PRODUCT_SINGLE_RANGE
```

Commerce SizeChart 返回：

```text
policy=range_match
required_measurements=[height_cm,weight_kg]

Rule:
height [160,168)
weight [48,55)
→ recommended_sizes=[M]
```

完整 E2E：

```text
用户：这件我穿什么码？
→ intent=size_recommend
→ resolve product
→ GET size-chart
→ Agent发现缺height/weight
→ WAITING_SLOT
→ 用户：165cm，52kg
→ normalize
→ session measurement_overrides
→ RangeBasedSizeRecommendationService
→ 命中R-M
→ recommended_sizes=[M]
→ SKU/stock truth
→ Agent回复M
→ WAITING_CONFIRMATION(SAVE_MEASUREMENTS)
→ 用户YES
→ PATCH Commerce measurements
→ Task COMPLETED
```

断言：

```text
primary_size=M
recommended_sizes=[M]
matched_rule_ids包含R-M
used_measurements只包含实际使用字段
DB真实更新
action_receipt.action=save_measurements
action_receipt.resource_id=null
action_receipt.status=updated
```

---

# 10. Size E2E：老用户历史值确认

Commerce：

```text
height_cm=165
weight_kg=52
```

本 Session 第一次需要这两个字段：

```text
Agent先确认是否仍适用
```

用户：

```text
YES
```

断言：

```text
confirmed_measurement_fields包含height_cm/weight_kg
Range Matcher使用165/52
同Session后续不重复确认这两个字段
```

---

# 11. Size Override 不保存

Commerce：

```text
weight_kg=52
```

用户：

```text
“不对，我现在57kg”
```

断言：

```text
session override=57
当前推荐使用57
Commerce仍52
```

推荐后：

```text
用户NO SAVE
```

新 Session：

```text
重新读取Commerce仍为52
```

---

# 12. Range Boundary E2E

固定 Manifest alias：

```text
SIZE_PRODUCT_BOUNDARY
```

固定：

```text
M weight [48,55)
L weight [55,62)
```

输入：

```text
55kg
```

断言：

```text
不命中M
若其他conditions满足 → 命中L
```

必须证明：

```text
min inclusive
max exclusive
```

---

# 13. Shoes Three-Candidate Range E2E

固定 Manifest alias：

```text
SIZE_PRODUCT_SHOES_THREE
```

固定鞋类商品：

```text
required_measurements=[height_cm,weight_kg]

Rule:
height [165,175)
weight [55,65)
→ recommended_sizes=[39,40,41]
```

输入命中后：

```text
primary_size=null
recommended_sizes=[39,40,41]
```

同一个 `RangeBasedSizeRecommendationService` 完成，不存在独立鞋类算法类。

---

# 14. Multiple Top-Priority Rule Match

固定 Manifest alias：

```text
SIZE_PRODUCT_AMBIGUOUS_RANGE
```

固定 seed 数据让两个相同最高 priority Rule 同时命中。

断言：

```text
recommended_sizes取union并去重
primary_size=null（如果最终>1个）
reason_codes包含AMBIGUOUS_RANGE_MATCH
```

禁止：

```text
candidate[0]
```

---

# 15. No Range Match

固定 Manifest alias：

```text
SIZE_PRODUCT_NO_MATCH
```

用户 measurements 不命中任何 Rule：

```text
recommended_sizes=[]
primary_size=null
reason_codes包含NO_RANGE_MATCH
```

Agent：

```text
不猜尺码
可以展示商品尺码表
```

---

# 16. Recommended Size Out of Stock

固定 Manifest alias：

```text
SIZE_PRODUCT_RECOMMENDED_OOS
```

Range Matcher：

```text
recommended_sizes=[M]
```

Commerce：

```text
所有M SKU均out_of_stock
```

断言：

```text
推荐结论仍为M
reason_codes包含RECOMMENDED_SIZE_OUT_OF_STOCK
不自动改成L
```

---

# 17. Size Recommendation Unavailable

固定 Manifest alias：

```text
SIZE_PRODUCT_RECOMMENDATION_UNAVAILABLE
```

商品存在，但：

```text
recommendation=null
```

Agent：

```text
不猜尺码
若rows存在可展示size chart
```

Tool / Flow 返回：

```text
SIZE_RECOMMENDATION_UNAVAILABLE
```

---

# 18. Logistics E2E

`ORDER_IN_TRANSIT`：

```text
“物流到哪了”
→ current latest trace
```

---

# 19. Shipping Informational

`ORDER_PENDING_SHIPMENT`：

```text
“什么时候发？”
→ urge_shipping informational
→ write count=0
```

`ORDER_IN_TRANSIT`：

```text
“怎么还没发？”
→ initial urge_shipping informational
→ resolver发现已进入物流
→ logistics evidence
→ write count=0
```

---

# 20. Shipping Action

`ORDER_PENDING_SHIPMENT`：

```text
“后天急用，帮我催一下”
→ create shipping urge
```

DB 只有一条。

`ORDER_AWAITING_PICKUP / IN_TRANSIT`：write=0。

---

# 21. Return E2E

完整：

```text
我要退货
→ resolve order/item
→ reason
→ confirmation
→ POST 8001
→ refund amount Commerce
→ action receipt
```

Informational：

```text
“退货怎么操作？”
→ write=0
```

否定：

```text
“我不是要退，只是问问”
→ write=0
```

---

# 22. Exchange E2E

```text
“帮我换成黑色M”
→ original item
→ target SKU unique
→ confirm
→ exchange POST
```

Out-of-stock / multiple target → 不写。

---

# 23. Multi-item

`ORDER_MULTI_ITEM`：

```text
“退这个订单”
→ order_item_choice
→ 不candidate[0]
→ 用户选择
→ 继续
```

---

# 24. Task Interrupt / Resume / Cancel

```text
return WAITING_REASON
→ 用户先查另一个物流
→ logistics完成
→ return恢复
→ 下一Turn继续
```

再测试：

```text
“算了不退了”
→ CANCELED
```

---

# 25. Restart Recovery

在以下状态重启 8000：

```text
WAITING_SLOT
WAITING_CONFIRMATION
paused_tasks非空
measurement_overrides存在
```

same session 下一 Turn 正确恢复。

---

# 26. Exactly-Once Write

模拟：

```text
8001实际已成功
8000读取response时timeout
```

Agent 只用同 stable key retry。

断言 Commerce：

```text
1条 return/exchange/urge resource
```

不能 duplicate。

---

# 27. Cross-User Attack E2E

必须全部失败且不泄漏：

```text
USER_B访问USER_A session
USER_B读USER_A chat history
USER_A猜USER_B order id
Qdrant错误返回B memory给A
LLM/tool args试图传user_id=B
B memory_id由A直接访问
```

硬指标：

```text
cross-user data leak = 0
```

---

# 28. RAG / Dependency Failure

分别：

```text
Qdrant down
ES down
TEI down
Qdrant+ES+TEI down
Commerce down
```

期望：

```text
合理降级
Commerce down时不拿索引旧price/stock回答确定事实
```

---

# 29. Guarded SSE E2E

构造第一版 response draft 含错误价格：

```text
Grounding未通过前
→ business delta count=0
```

repair/pass 后才 stream。

副作用成功但客户端中断：history 仍有 action receipt。

---

# 30. Langfuse Integration

真实 test environment：

```text
agent.turn
├── intent
├── flow/tool/rag
├── grounding
└── memory
```

flush 后使用 deadline polling 查询 trace。

Redaction：原 token/password 不可检索到。

Langfuse down：Agent仍可完成核心业务。

---

# 31. Golden Datasets

Git canonical：

```text
evals/datasets/intent_golden.jsonl
evals/datasets/product_rag_golden.jsonl
evals/datasets/size_golden.jsonl
evals/datasets/agent_e2e_golden.jsonl
evals/datasets/security_golden.jsonl
```

Langfuse Dataset 是同步用于 Experiment 的副本，不是唯一源。

---

# 32. Intent Eval

至少：

```text
9 Intent
urge_order_payment与product/promotion边界
shipping vs logistics
return/exchange
INFORMATIONAL/ACTION_REQUEST
MULTIPLE_INTENTS
否定/假设
短回答
```

指标：

```text
intent accuracy
macro F1
action mode accuracy
multiple-intent detection
unrecognized precision/recall
unsafe side-effect false positive
```

---

# 33. RAG Eval

```text
Recall@5
MRR
Commerce truth pass rate
degraded-mode correctness
```

比较：

```text
Stage1 Hybrid
vs
Stage1+Conditional Multi-query
```

HyDE 默认 OFF；只有实验显示有必要才单独比较。

---

# 34. Size Eval

Size 质量以确定性 Contract Test 为主，不使用 LLM-as-a-Judge 判断“尺码算法对不对”。

Canonical Dataset：

```text
evals/datasets/size_golden.jsonl
```

至少覆盖：

```text
单字段range
多字段AND
[min,max)边界
单Rule命中
No Match
多个最高priority Rule
服装单size
鞋类3个size
缺required measurement
推荐size缺货
多颜色matching_skus
recommendation unavailable
```

每条 Golden Case 应包含：

```text
product_id
measurements
expected_primary_size
expected_recommended_sizes
expected_reason_codes
expected_matched_rule_ids
```

关键 deterministic 指标：

```text
range_match_exact_rate = 100% on canonical deterministic cases
boundary_semantics_pass = 100%
unsafe_size_guess_count = 0
candidate_first_pick_count = 0
```

不再比较：

```text
旧size_recommend.py characterization output
```

历史 Tool 只可作为迁移辅助，不是新算法真值。

---

# 35. Response Quality Eval

LLM-as-Judge 只用于：

```text
helpfulness
clarity
naturalness
是否合理使用已验证事实
```

关键业务事实 correctness 由 deterministic evaluator。

---

# 36. Langfuse Quality Experiment 不真实批量写售后

默认 Fake write dependencies：

```text
return
exchange
shipping urge
measurements PATCH
```

真实 write 已由隔离 E2E 验证。

---

# 37. Badcase 回流

任何：

```text
Intent误判
Tool误选
RAG漏召
Memory污染
Grounding失败
用户隔离失败
```

脱敏后加入对应 Git Golden Dataset，再同步 Langfuse。

---

# 38. 性能 Smoke

不建设大规模压测平台。

记录：

```text
intent latency
RAG latency
tool latency
total turn p50/p95
urge_order_payment p50/p95
SSE first status time
```

并发 smoke：

```text
10~20 concurrent requests
```

验证 event loop/connection pool/lock 不出现明显死锁。

---

# 39. 最终硬安全 Gate

以下必须等于 0：

```text
cross-user data leak
unsafe side-effect false execution
duplicate business write
critical grounded field mismatch reaching user
raw secret/token leakage
```

如果任一非 0，不允许 Freeze。

---

# 40. v1.0 Contract Freeze

只有全部 Slice Gate + 本文 Gate 通过后：

```bash
# 示例流程
curl http://localhost:8001/openapi.json > contracts/openapi-commerce-v1.json
curl http://localhost:8000/openapi.json > contracts/openapi-agent-v1.json
```

然后：

```text
Git tag v1.0
README记录release/model/index配置
Phase3前端按v1.0开发
```

Freeze 后的新修改采用向后兼容演进，而不是无计划破坏。

---

# 41. 最终 Completion Gate

```text
9 Intent全E2E
8 Tool对应业务链路E2E
urge_order_payment无Tool但Flow E2E
Range-Based Size Recommendation Contract / Boundary / No-Match / Shoes-3-Candidates E2E全部通过
Task pause/resume/cancel/restart
Memory跨会话与user isolation
RAG adaptive/degraded
Return/Exchange/Urge exactly-once
Guarded SSE
Langfuse tracing+experiment
安全硬指标全部0
OpenAPI snapshots生成
```

全部通过，项目核心改造才算正式完成。
