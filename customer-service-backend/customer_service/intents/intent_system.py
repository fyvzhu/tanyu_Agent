"""
Intent 分类器和策略系统
"""
from __future__ import annotations

import logging
from typing import Any

from customer_service.tasking.models import BusinessIntent
from customer_service.intents.models import IntentDecision
from customer_service.infrastructure.llm import get_llm

logger = logging.getLogger(__name__)


class IntentClassifier:
    """
    意图分类器
    - 使用 LLM 识别用户输入的业务意图
    - 支持 9 种 BusinessIntent
    """

    INTENT_PROMPT = """你是一个电商客服意图识别专家。根据用户的输入，判断用户的意图类型，并提取关键实体。

可选的意图类型及需要提取的实体：
1. chitchat - 闲聊（打招呼、天气、情感表达等）
   实体：无

2. product_query - 商品查询（查找商品、询问价格、品牌、材质、卖点等）
   实体：search_query（商品关键词、商品ID、商品描述）

3. size_recommend - 尺码推荐（询问尺码、身材推荐等）
   实体：body_measurements（身高、体重、尺寸等身体数据）

4. order_query - 订单查询（查询订单状态、订单详情等）
   实体：order_id（订单号）

5. logistics_query - 物流查询（查询快递、配送进度等）
   实体：order_id（订单号）

6. return_request - 退货申请（要求退货、退款等）
   实体：order_id（订单号）、return_reason（退货原因）

7. exchange_request - 换货申请（要求换货、换尺码等）
   实体：order_id（订单号）、exchange_reason（换货原因）

8. urge_shipping - 催发货（订单已支付，催促商家发货、加快配送等）
   实体：order_id（订单号）

9. urge_order_payment - 催付款/催拍（客户犹豫不决、询问是否值得购买、促成交易等）
   实体：无

10. promotion_query - 促销查询（询问优惠、折扣、活动等）
   实体：无

用户输入: {user_input}

请以 JSON 格式返回：
{{
  "intent": "intent_name",
  "confidence": 0.95,
  "reason": "识别理由",
  "entities": {{"key": "value"}}
}}

注意：
- 对于 product_query，search_query 应该包含用户提到的所有商品相关信息（商品ID、品类、颜色、用途等）
- 如果用户提到具体商品ID（如 PROD001），请将其作为 search_query
- 如果用户描述商品特征（如"夏天穿的连衣裙"），请将完整描述作为 search_query
- 如果实体不存在，entities 应为空对象 {{}}"""

    def __init__(self):
        self.llm = get_llm()

    async def classify(self, user_input: str, context: dict[str, Any] | None = None) -> IntentDecision:
        """
        识别用户输入的意图
        
        Args:
            user_input: 用户输入
            context: 上下文信息（可选）
            
        Returns:
            IntentDecision 对象
        """
        try:
            prompt = self.INTENT_PROMPT.format(user_input=user_input)
            
            # 调用 LLM
            response = await self.llm.ainvoke(prompt)
            content = response.content if hasattr(response, 'content') else str(response)
            
            # 解析 JSON
            import json
            result = json.loads(content)
            
            intent = BusinessIntent(result["intent"])
            confidence = float(result.get("confidence", 0.8))
            reason = result.get("reason", "")
            entities = result.get("entities", {})
            
            return IntentDecision(
                intent=intent,
                confidence=confidence,
                reason=reason,
                extracted_entities=entities
            )
            
        except Exception as e:
            logger.error(f"Intent 分类失败: {e}", exc_info=True)
            # 降级：默认为 chitchat
            return IntentDecision(
                intent=BusinessIntent.CHITCHAT,
                confidence=0.5,
                reason=f"分类失败，降级为闲聊: {str(e)}",
                extracted_entities={}
            )


class IntentPolicy:
    """
    意图策略
    - 定义每种 Intent 需要的必填槽位
    - 验证槽位完整性
    """

    # 每种 Intent 的必填槽位定义
    REQUIRED_SLOTS: dict[BusinessIntent, list[str]] = {
        BusinessIntent.CHITCHAT: [],
        BusinessIntent.PRODUCT_QUERY: ["search_query"],
        BusinessIntent.SIZE_RECOMMEND: ["body_measurements"],
        BusinessIntent.ORDER_QUERY: ["order_id"],
        BusinessIntent.LOGISTICS_QUERY: ["order_id"],
        BusinessIntent.RETURN_REQUEST: ["order_id", "return_reason"],
        BusinessIntent.EXCHANGE_REQUEST: ["order_id", "exchange_reason"],
        BusinessIntent.URGE_SHIPPING: ["order_id"],
        BusinessIntent.URGE_ORDER_PAYMENT: [],  # 催付款不需要槽位，基于对话上下文
        BusinessIntent.PROMOTION_QUERY: [],
    }

    @classmethod
    def get_required_slots(cls, intent: BusinessIntent) -> list[str]:
        """获取指定意图的必填槽位"""
        return cls.REQUIRED_SLOTS.get(intent, [])

    @classmethod
    def check_slots_complete(cls, intent: BusinessIntent, slots: dict[str, Any]) -> tuple[bool, list[str]]:
        """
        检查槽位是否完整
        
        Returns:
            (是否完整, 缺失的槽位列表)
        """
        required = cls.get_required_slots(intent)
        missing = [slot for slot in required if slot not in slots or not slots[slot]]
        return len(missing) == 0, missing

    @classmethod
    def should_ask_slots(cls, intent: BusinessIntent, slots: dict[str, Any]) -> bool:
        """判断是否需要询问槽位"""
        is_complete, _ = cls.check_slots_complete(intent, slots)
        return not is_complete


class PendingIntentSelector:
    """
    待处理意图选择器
    - 当出现意图切换时，决定是暂停当前任务还是取消
    """

    @staticmethod
    def should_interrupt(
        current_intent: BusinessIntent | None,
        new_intent: BusinessIntent
    ) -> bool:
        """
        判断新意图是否应该打断当前任务
        
        规则：
        - 闲聊不打断任何任务
        - 高优先级任务（退换货、催发货）打断其他任务
        - 同类任务不打断
        """
        if current_intent is None:
            return False

        if new_intent == BusinessIntent.CHITCHAT:
            return False

        # 高优先级任务
        high_priority = {
            BusinessIntent.RETURN_REQUEST,
            BusinessIntent.EXCHANGE_REQUEST,
            BusinessIntent.URGE_SHIPPING
        }

        if new_intent in high_priority:
            return True

        # 同类任务不打断
        if new_intent == current_intent:
            return False

        return True
