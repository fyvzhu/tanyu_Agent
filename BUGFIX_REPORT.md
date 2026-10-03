# 紧急Bug修复报告

## 问题描述

**错误类型**: `UnboundLocalError`  
**错误位置**: `intent_parse.py` 第656行  
**错误信息**: `cannot access local variable 'get_intent_policy' where it is not associated with a value`

## 根本原因

在P0-1修复中添加的短路逻辑（第313行）中，我错误地添加了局部导入：

```python
# 错误代码（第313行）
from customer_service.intents.policies import get_intent_policy  # ❌ 局部导入
policy = get_intent_policy(context_resolution.inherited_intent)
```

这导致Python认为`get_intent_policy`是一个局部变量，但在函数后面（第656行）使用时，这个"局部变量"还未被赋值，从而触发`UnboundLocalError`。

## 修复方案

删除第313行的重复导入，使用文件顶部（第52行）已经导入的全局`get_intent_policy`：

```python
# 修复后（第313行）
# 获取IntentPolicy（使用已导入的函数）
policy = get_intent_policy(context_resolution.inherited_intent)  # ✅ 使用全局导入
```

## 修复验证

```bash
# Python语法检查
python -m py_compile intent_parse.py
结果: ✅ 通过（无错误）

# IDE诊断
diagnostics intent_parse.py
结果: ✅ No diagnostics found
```

## 文件变更

- **修改文件**: `customer-service-backend/customer_service/graph/nodes/intent_parse.py`
- **修改位置**: 第313行
- **变更类型**: 删除重复的`from ... import`语句

## 影响范围

- **影响功能**: 省略式追问的短路逻辑（P0-1修复）
- **影响用户**: 所有使用意图继承功能的用户
- **严重程度**: 🔴 严重（导致500错误）

## 后续操作

✅ **已完成**:
1. 删除重复导入
2. Python语法验证通过
3. IDE诊断无错误

⚠️ **需要操作**:
1. **重启后端服务**以应用修复
2. 测试省略式追问场景（"那29570呢？"）
3. 检查新的错误日志确认问题解决

## 测试建议

```bash
# 测试用例
用户: 查询15970的优惠
Agent: [创建promotion_query任务]
用户: 那29570呢？
期望: [短路逻辑生效，直接继承意图] ✅
```

---

**修复时间**: 2026-10-03 15:00  
**修复人员**: Kiro  
**验证状态**: ✅ 语法验证通过，待服务重启测试
