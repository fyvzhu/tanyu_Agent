"""
IntentPolicy 策略矩阵
根据 01_slice_foundation 文档 #22 定义

最终唯一 Policy Matrix - 全项目固定
"""
from loguru import logger

from customer_service.tasking.models import BusinessIntent
from customer_service.intents.models import IntentPolicy


# ==================== Intent Policy Matrix ====================
# 根据文档 #22 的表格定义
INTENT_POLICY_MATRIX: dict[BusinessIntent, IntentPolicy] = {
    BusinessIntent.PRODUCT_QUERY: IntentPolicy(
        intent=BusinessIntent.PRODUCT_QUERY,
        allowed_tools=("product_search_tool", "selling_point_tool"),
        can_write=False,
        requires_action_request=False,
        requires_execute_confirmation=False,
    ),
    BusinessIntent.SIZE_RECOMMEND: IntentPolicy(
        intent=BusinessIntent.SIZE_RECOMMEND,
        allowed_tools=("size_recommend_tool",),
        can_write=False,
        requires_action_request=False,
        requires_execute_confirmation=False,
    ),
    BusinessIntent.URGE_ORDER_PAYMENT: IntentPolicy(
        intent=BusinessIntent.URGE_ORDER_PAYMENT,
        allowed_tools=(),  # 无业务 Tool
        can_write=False,
        requires_action_request=False,
        requires_execute_confirmation=False,
    ),
    BusinessIntent.PROMOTION_QUERY: IntentPolicy(
        intent=BusinessIntent.PROMOTION_QUERY,
        allowed_tools=("promotion_query_tool",),
        can_write=False,
        requires_action_request=False,
        requires_execute_confirmation=False,
    ),
    BusinessIntent.LOGISTICS_QUERY: IntentPolicy(
        intent=BusinessIntent.LOGISTICS_QUERY,
        allowed_tools=("logistics_query_tool",),
        can_write=False,
        requires_action_request=False,
        requires_execute_confirmation=False,
    ),
    BusinessIntent.RETURN: IntentPolicy(
        intent=BusinessIntent.RETURN,
        allowed_tools=("return_request_tool",),
        can_write=True,
        requires_action_request=True,
        requires_execute_confirmation=True,
    ),
    BusinessIntent.EXCHANGE: IntentPolicy(
        intent=BusinessIntent.EXCHANGE,
        allowed_tools=("exchange_request_tool",),
        can_write=True,
        requires_action_request=True,
        requires_execute_confirmation=True,
    ),
    BusinessIntent.CHITCHAT: IntentPolicy(
        intent=BusinessIntent.CHITCHAT,
        allowed_tools=(),  # 无业务 Tool
        can_write=False,
        requires_action_request=False,
        requires_execute_confirmation=False,
    ),
    BusinessIntent.URGE_SHIPPING: IntentPolicy(
        intent=BusinessIntent.URGE_SHIPPING,
        allowed_tools=("urge_shipping_tool",),
        can_write=True,
        requires_action_request=True,
        requires_execute_confirmation=False,  # 不需要第二次确认
    ),
}


def get_intent_policy(intent: BusinessIntent) -> IntentPolicy:
    """获取 Intent 策略"""
    policy = INTENT_POLICY_MATRIX.get(intent)
    if not policy:
        logger.error(f"❌ Intent Policy 未定义: {intent}")
        raise ValueError(f"Intent Policy 未定义: {intent}")
    return policy


def validate_tool_for_intent(intent: BusinessIntent, tool_name: str) -> bool:
    """验证 Tool 是否允许在该 Intent 下使用"""
    policy = get_intent_policy(intent)
    allowed = tool_name in policy.allowed_tools
    if not allowed:
        logger.warning(f"⚠️ Tool {tool_name} 不允许用于 Intent {intent}")
    return allowed


# ==================== 初始化验证 ====================
def validate_policy_matrix():
    """验证 Policy Matrix 完整性"""
    all_intents = set(BusinessIntent)
    defined_intents = set(INTENT_POLICY_MATRIX.keys())
    
    if all_intents != defined_intents:
        missing = all_intents - defined_intents
        extra = defined_intents - all_intents
        logger.error(f"❌ Intent Policy Matrix 不完整！缺失: {missing}, 多余: {extra}")
        raise RuntimeError("Intent Policy Matrix 必须覆盖所有 9 个 BusinessIntent")
    
    logger.info(f"✅ Intent Policy Matrix 验证通过 (9/9 覆盖)")


# 模块加载时验证
validate_policy_matrix()
