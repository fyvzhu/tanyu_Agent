# 探域电商售前 Agent：Developer Handoff Final 文档包

> 版本：v7.0 — Developer Handoff Final  
> 日期：2026-09-22  
> 状态：可直接交给开发者 / Codex 按文档施工；任何实现变更仍必须通过对应 Contract 与测试 Gate。

本包采用 Vertical Slice 施工方式，同时冻结跨服务 Living Contract。**每一份 `00~08` MD 都是独立、自包含的施工文档**：即使开发者只拿到其中一份，也必须能从该文件读到本项目相关边界、该 Slice 的最终目标、要修改/新增/删除的文件、Runtime/API 约束、测试以及 Completion Gate。

明确禁止在任何 MD 中使用“基于上一版修改”“沿用之前方案”“参考前一个 MD 才能实现”等依赖历史材料的方式交代核心实现。文档可以描述施工顺序和跨服务接口，但不能把关键字段、Enum、Registry、API、Fixture 或验收标准留给其他文件解释。

## 文档集

1. `00_overall_architecture_living_contract.md` —— 总体架构、服务 ownership、五节点 LangGraph、9 Intent、Range-Based Size、数据库与全局 Gate。
2. `01_slice_foundation_auth_chat_agent_runtime.md` —— Auth / Chat / LangGraph / Task / Intent / Policy Matrix / ToolRuntime / 共享 Schema。
3. `02_slice_product_promotion_conversion.md` —— 商品咨询、促销、催拍催付、Product RAG、基础闲聊。
4. `03_slice_size_recommendation_measurements.md` —— Range-Based Size Recommendation、Measurements、Size Flow 注册与保存确认。
5. `04_slice_order_logistics_shipping_aftersale.md` —— 订单、物流、催发货、退货、换货、Flow 注册、幂等写。
6. `05_slice_memory_personalization_isolation.md` —— User Context、Semantic Memory、个性化、Cross-user isolation 与旧 Memory 迁移删除。
7. `06_slice_guardrails_langfuse_sse_finalization.md` —— Guardrails、Grounding、ActionReceipt、Guarded SSE、Langfuse 与旧 Guard 迁移删除。
8. `07_api_runtime_contract.md` —— 完整 HTTP / Runtime Contract、IntentPolicy、9 Flow、8 Tool、Range Size、ActionReceipt。
9. `08_cross_service_e2e_eval.md` —— Deterministic Fixture Manifest、全 Intent E2E、Recovery、Eval、安全 Gate 与 v1.0 Freeze。

## 冻结的核心 Contract

```text
BusinessIntent = 9
Business Tool   = 8
IntentFlow      = 9
LangGraph Node  = 5
```

9 Intent：

```text
product_query
size_recommend
urge_order_payment
promotion_query
logistics_query
return
exchange
chitchat
urge_shipping
```

8 Tool：

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

`urge_order_payment` 和 `chitchat` 没有业务 Tool。

## Size Recommendation 最终定义

```text
Commerce SizeChart rows
+ products.size_recommendation_rules JSON NULL
+ RangeBasedSizeRecommendationService
+ Commerce SKU / Stock truth
```

Range 固定为 `[min,max)`。历史 `customer_service/tools/size_recommend.py` 只可迁移 normalization、validation、SKU helper、错误处理和测试样本；旧隐式算法不是正式 Contract。禁止外部 Size MCP、Size ML、LLM 算尺码、nearest-distance 猜码和 `candidate[0]`。

## Side-effect 最终定义

```text
return   → ACTION_REQUEST + final confirmation + stable Idempotency-Key
exchange → ACTION_REQUEST + final confirmation + stable Idempotency-Key
urge_shipping → ACTION_REQUEST + no second execute confirmation + stable Idempotency-Key
save_measurements → explicit SAVE_MEASUREMENTS confirmation + UserContextWriteService
```

`ActionReceipt.resource_id` 为 optional：return / exchange / urge_shipping 必填；`save_measurements` 固定为 `null`。

## Fixture 与 Final Gate

`tests.support.prepare_e2e` 必须生成 `contracts/fixtures/ecommerce_e2e_manifest.json`，其中既包含用户/订单/商品 alias，也包含 7 个固定 Size alias。测试只消费 alias，不自行发明 ID。

最终只有在 `08_cross_service_e2e_eval.md` 的全部 E2E、安全 Gate、Contract snapshot 条件通过后，才生成：

```text
contracts/openapi-commerce-v1.json
contracts/openapi-agent-v1.json
```

并进行 v1.0 Contract Freeze。

## Developer Handoff 规则

交付前必须确认：

```text
字段名无冲突
路径无平行旧实现
Enum 值唯一
IntentPolicy 唯一
IntentFlowRegistry 9/9
ToolRegistry 8/8
API method/path/header/schema 一致
Fixture alias 全部可解析
Markdown fence 全部闭合
Manifest hash/line/bytes 与实际文件一致
P0 = 0
P1 = 0
```
