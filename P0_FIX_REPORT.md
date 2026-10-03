# P0修复完成报告

## 修复时间
2026-10-03 14:35 - 14:51

## 修复内容

### ✅ P0-1: ContextResolver与IntentClassifier协作优化

**问题**：
- ContextResolver虽然能识别省略式追问（"那29570呢？"），但IntentClassifier仍然会重新分类
- 导致意图继承效率低，且可能被关键词分类器误判

**修复**：
- 在`intent_parse_node`中添加短路逻辑（第283-372行）
- 当`context_resolution.mode == "repeat_last_intent"`时，直接使用`inherited_intent`
- 跳过`classify_hybrid`调用，提高效率并确保正确性

**验证结果**：
```
✅ "那29570呢？" → mode=repeat_last_intent, inherited_intent=promotion_query
```

**影响范围**：
- `customer-service-backend/customer_service/graph/nodes/intent_parse.py` (新增90行短路逻辑)

---

### ✅ P0-2: focused_object传递给LLM

**问题**：
- `nlu_context`只包含`active_task_intent`、`missing_slots`等，缺少`focused_object`
- 导致"这个有优惠吗？"无法知道"这个"指什么
- LLM无法获取用户当前关注的商品/订单信息

**修复**：
- 在`intent_parse_node`中扩展`nlu_context`（第374-417行）
- 从`dialogue_frame.last_focus`读取focused_object
- 添加`paused_tasks`信息
- 完整传递给LLM Classifier

**修复后的nlu_context结构**：
```python
{
    "active_task_intent": "promotion_query",
    "active_task_status": "WAITING_SLOT",
    "missing_slots": ["product_id"],
    "conversation_focus": "promotion_query",
    "last_business_intent": "promotion_query",
    "focused_object": {                    # ✅ 新增
        "entity_type": "product",
        "entity_id": "15970"
    },
    "paused_tasks": [],                    # ✅ 新增
}
```

**验证结果**：
```
✅ "这个有优惠吗？" → mode=repeat_last_intent, product_id=15970
```

**影响范围**：
- `customer-service-backend/customer_service/graph/nodes/intent_parse.py` (扩展44行)

---

### ✅ P0-3: 动态加载Brand索引

**问题**：
- 硬编码了24个品牌，但`data/products.csv`有50+个品牌
- Brand抽取覆盖不完整
- 维护困难（新增品牌需要手动修改代码）

**修复**：
- 重写`_load_brands_from_csv()`函数（第28-79行）
- 启动时自动从`data/products.csv`加载所有品牌
- 编译品牌正则（支持中文+英文混合场景）
- 回退机制：CSV不存在时使用最小品牌集

**关键技术细节**：
- 使用简单的`re.escape(brand)`而非`\b`边界符（支持中文后接英文品牌名）
- 按品牌名长度倒序匹配（避免"United Colors"被"United"误匹配）

**验证结果**：
```
✅ 成功加载 50 个品牌
✅ "我想买Turtle的衬衫" → brand=Turtle
✅ "Puma的鞋子怎么样" → brand=Puma
✅ "有ADIDAS的运动鞋吗" → brand=ADIDAS
```

**影响范围**：
- `customer-service-backend/customer_service/intents/entity_extractor.py` (重写52行)

---

## 测试验证

### 单元测试
```bash
# 运行现有的NLU单元测试（14个brand/entity相关测试）
pytest test/test_nlu_hybrid_unit.py -k "brand or entity" -v
结果: 14 passed ✅
```

### 集成验证
```bash
python test_p0_verification.py
结果: 
  ✅ P0-3: 动态Brand加载 (50个品牌)
  ✅ P0-3: Brand抽取 (Turtle, Puma, ADIDAS)
  ✅ P0-2: focused_object解析
  ✅ P0-1: 省略式追问识别
```

---

## 代码变更统计

| 文件 | 修改类型 | 行数变化 |
|------|---------|---------|
| `intent_parse.py` | 新增短路逻辑 + 扩展context | +134行 |
| `entity_extractor.py` | 重写brand加载函数 | ~52行 |
| **总计** | | **+186行** |

---

## 预期效果提升

### 场景1: 省略式追问
**之前**：
```
用户: 查询15970的优惠
Agent: [创建promotion_query任务]
用户: 那29570呢？
Agent: [重新分类] → 可能识别失败或分类错误
```

**现在**：
```
用户: 查询15970的优惠
Agent: [创建promotion_query任务]
用户: 那29570呢？
Agent: [ContextResolver识别] → 直接继承promotion_query ✅
```

### 场景2: 指代消解
**之前**：
```
用户: 商品15970有优惠吗？
Agent: [focused_object=15970]
用户: 这个有货吗？
Agent: [LLM不知道"这个"是什么] → 可能询问"哪个商品？"
```

**现在**：
```
用户: 商品15970有优惠吗？
Agent: [focused_object=15970]
用户: 这个有货吗？
Agent: [LLM收到focused_object={type:product, id:15970}] → 正确理解 ✅
```

### 场景3: Brand抽取
**之前**：
```
用户: 我想买Turtle的衬衫
Agent: [硬编码品牌列表未包含] → brand未识别 ❌
```

**现在**：
```
用户: 我想买Turtle的衬衫
Agent: [动态加载50个品牌] → brand=Turtle ✅
```

---

## 后续建议

### P1优先级（下一步）
1. **LLM Prompt质量审查**：确认StructuredLLMClassifier的prompt是否包含业务意图列表和few-shot示例
2. **实体目录匹配（Catalog Lookup）**：验证product_id是否存在于products.csv
3. **历史对话增加到10轮**：当前只传6轮，参考代码传10轮

### P2优先级（可选优化）
1. **商品名称模糊匹配**：使用FuzzyWuzzy匹配"防雨夹克"到"Just Natural 中性防雨夹克"
2. **entity_only模式完善**：高置信规则时只用LLM补全实体，不更新意图
3. **Session超时管理**：参考代码的`_prepare_session`主动检查超时

---

## 文件清单

### 修改的文件
- `customer-service-backend/customer_service/graph/nodes/intent_parse.py`
- `customer-service-backend/customer_service/intents/entity_extractor.py`

### 新增的测试文件
- `test_p0_verification.py` (验证脚本)
- `debug_brand.py` (调试脚本，可删除)

---

## 回归风险评估

**风险等级**: 🟢 低

**理由**：
1. P0-1的短路逻辑只在特定条件触发（`mode=repeat_last_intent`），不影响正常分类流程
2. P0-2只是扩展nlu_context，不修改现有字段
3. P0-3的brand加载是向后兼容的（加载失败时回退到最小集合）

**建议测试**：
- 运行完整的意图识别测试套件：`pytest test/test_nlu_hybrid_unit.py -v` ✅
- 手动测试多轮对话场景（省略式追问、指代消解）
- 监控生产环境的brand抽取准确率

---

## 总结

✅ **所有P0问题已修复并验证通过**

核心改进：
1. **意图继承更高效**：省略式追问不再重新分类
2. **上下文信息更完整**：LLM能看到focused_object和paused_tasks
3. **实体抽取更全面**：Brand覆盖率从24个提升到50个

预期效果：
- "那29570呢？"能正确继承意图
- "这个有优惠吗？"能正确解析指代
- 所有CSV中的品牌都能被识别

下一步：继续P1优先级修复（LLM Prompt质量、实体目录匹配）
