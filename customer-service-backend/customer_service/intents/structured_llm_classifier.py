"""
结构化LLM分类器 - P0-2修复

根据文档第19行要求：
- 结构化分类器输出受限的目标数组
- 每个目标含 BusinessIntent、原句片段、实体
- Schema 严格校验，失败返回 CLASSIFIER_FAILURE

根据参考代码9（langchain）：
- 使用 Pydantic Schema 定义输出结构
- 模型只提出目标和实体，不决定路由
- 服务端二次校验

注意事项（文档第175-176行）：
- 不盲目使用 with_structured_output（兼容性问题）
- 不传全量聊天记录（成本和假事实）
- 超时/非法JSON返回CLASSIFIER_FAILURE
"""
from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field, ValidationError
from loguru import logger

from customer_service.tasking.models import BusinessIntent
from customer_service.intents.models import IntentClassificationResult, IntentGoal
from customer_service.infrastructure.llm import get_llm


class StructuredIntentGoal(BaseModel):
    """
    单个意图目标（LLM输出格式）
    
    根据文档第19行：每个目标的短原句片段与实体只归属于这一项
    """
    intent: BusinessIntent = Field(..., description="业务意图类型")
    text_span: str = Field(..., description="对应的原句片段（10-30字）")
    entities: dict[str, Any] = Field(default_factory=dict, description="该目标的实体")
    confidence: float = Field(default=0.8, ge=0.0, le=1.0, description="置信度")


class StructuredClassificationOutput(BaseModel):
    """
    LLM分类器的结构化输出
    
    根据文档第19行："输出受限的目标数组，每个目标含 BusinessIntent、对应的原句片段和本项实体"
    """
    goals: list[StructuredIntentGoal] = Field(
        default_factory=list,
        description="识别到的意图目标列表"
    )
    is_out_of_scope: bool = Field(
        default=False,
        description="是否明确超出业务范围"
    )
    reasoning: str | None = Field(
        None,
        description="简短的推理过程（可选，用于调试）"
    )


class StructuredLLMClassifier:
    """
    结构化LLM分类器
    
    P0-2修复：添加LLM分类器作为关键词分类器的增强
    
    根据文档第174行：
    - 提示词只携带当前消息、已验证的会话焦点摘要、正在等待的槽位
    - 不传全量聊天记录或JWT
    - Schema校验通过后，由DecisionEngine计算最终TurnAction
    """
    
    def __init__(self, enabled: bool = False):
        """
        Args:
            enabled: 是否启用LLM分类器（默认False，使用关键词分类器）
        """
        self.enabled = enabled
        self.llm = get_llm() if enabled else None
    
    async def classify(
        self,
        message: str,
        context: dict[str, Any] | None = None,
        timeout: float = 5.0
    ) -> IntentClassificationResult:
        """
        使用LLM进行结构化意图分类
        
        Args:
            message: 用户消息
            context: 上下文（会话焦点、等待槽位等）
            timeout: 超时时间（秒）
        
        Returns:
            IntentClassificationResult
        """
        if not self.enabled or not self.llm:
            # 未启用LLM分类器，返回空结果（由关键词分类器处理）
            return IntentClassificationResult(
                goals=[],
                is_confident=False,
                is_out_of_scope=False,
                classifier_error="LLM classifier not enabled"
            )
        
        try:
            # 构造提示词（精简版，不传全量历史）
            prompt = self._build_prompt(message, context)
            
            # 调用LLM（需要在infrastructure/llm.py中实现结构化输出支持）
            # 注意：这里需要根据实际LLM服务的能力选择实现方式
            # 1. 如果支持 with_structured_output，直接使用
            # 2. 如果只支持 JSON 模式，手动解析和校验
            
            # 目前先使用简单的JSON模式模拟
            response_text = await self._call_llm_with_timeout(prompt, timeout)
            
            # 解析和校验
            output = self._parse_and_validate(response_text)
            
            # 转换为 IntentClassificationResult
            return self._convert_to_classification_result(output)
        
        except TimeoutError as e:
            logger.error(f"LLM分类器超时: {e}")
            return IntentClassificationResult(
                goals=[],
                is_confident=False,
                is_out_of_scope=False,
                classifier_error="timeout"
            )
        
        except ValidationError as e:
            logger.error(f"LLM输出Schema校验失败: {e}")
            return IntentClassificationResult(
                goals=[],
                is_confident=False,
                is_out_of_scope=False,
                classifier_error="schema_validation_failed"
            )
        
        except Exception as e:
            logger.error(f"LLM分类器异常: {e}")
            return IntentClassificationResult(
                goals=[],
                is_confident=False,
                is_out_of_scope=False,
                classifier_error=str(e)
            )
    
    def _build_prompt(self, message: str, context: dict[str, Any] | None) -> str:
        """
        构造LLM提示词
        
        根据文档第174行：只携带必要上下文，不传全量聊天记录
        """
        # 业务意图列表（固定9类）
        intent_list = "\n".join([
            f"- {intent.value}: {self._get_intent_description(intent)}"
            for intent in BusinessIntent
        ])
        
        # 上下文信息（精简）
        context_info = ""
        if context:
            if context.get("conversation_focus"):
                context_info += f"\n当前焦点: {context['conversation_focus']}"
            if context.get("waiting_slot"):
                context_info += f"\n等待槽位: {context['waiting_slot']}"
        
        prompt = f"""你是一个电商客服意图分类助手。请分析用户消息并识别意图。

支持的业务意图类型：
{intent_list}

用户消息: "{message}"{context_info}

请以JSON格式返回分类结果：
{{
  "goals": [
    {{
      "intent": "BusinessIntent枚举值",
      "text_span": "对应的原句片段",
      "entities": {{"entity_key": "entity_value"}},
      "confidence": 0.0-1.0
    }}
  ],
  "is_out_of_scope": false,
  "reasoning": "可选的推理过程"
}}

注意：
1. intent 必须是上述业务意图之一
2. 如果识别到多个独立目标，在goals数组中列出
3. 如果不确定或超出范围，设置 is_out_of_scope=true
4. 不要编造信息，只提取用户明确表达的内容
"""
        return prompt
    
    def _get_intent_description(self, intent: BusinessIntent) -> str:
        """获取意图描述"""
        descriptions = {
            BusinessIntent.PRODUCT_QUERY: "商品查询、推荐",
            BusinessIntent.SIZE_RECOMMEND: "尺码推荐",
            BusinessIntent.URGE_ORDER_PAYMENT: "催拍催付",
            BusinessIntent.PROMOTION_QUERY: "优惠查询",
            BusinessIntent.LOGISTICS_QUERY: "物流查询",
            BusinessIntent.RETURN: "退货",
            BusinessIntent.EXCHANGE: "换货",
            BusinessIntent.CHITCHAT: "闲聊",
            BusinessIntent.URGE_SHIPPING: "催发货",
        }
        return descriptions.get(intent, "")
    
    async def _call_llm_with_timeout(self, prompt: str, timeout: float) -> str:
        """
        调用LLM（带超时）

        根据文档第175-176行警告：
        - 记录原始响应类型
        - 处理解析错误和超时
        - 如果只能受控JSON输出，服务端二次校验

        当前实现：返回模拟输出（需要替换为真实LLM调用）
        """
        import asyncio

        # TODO: 实际实现需要调用 self.llm
        # 当前返回模拟输出用于测试框架
        await asyncio.sleep(0.1)  # 模拟网络延迟

        # 模拟输出（实际使用时需要删除）
        return '''
        {
          "goals": [],
          "is_out_of_scope": false,
          "reasoning": "LLM classifier not fully implemented yet"
        }
        '''
    
    def _parse_and_validate(self, response_text: str) -> StructuredClassificationOutput:
        """
        解析并校验LLM输出
        
        根据文档第174行：Schema校验通过后才使用
        """
        import json
        
        # 解析JSON
        try:
            data = json.loads(response_text)
        except json.JSONDecodeError as e:
            raise ValidationError(f"Invalid JSON: {e}")
        
        # Pydantic校验
        output = StructuredClassificationOutput(**data)
        
        return output
    
    def _convert_to_classification_result(
        self,
        output: StructuredClassificationOutput
    ) -> IntentClassificationResult:
        """
        转换为 IntentClassificationResult
        """
        goals = [
            IntentGoal(
                intent=g.intent,
                entities=g.entities,
                text_span=g.text_span,
                confidence=g.confidence
            )
            for g in output.goals
        ]
        
        return IntentClassificationResult(
            goals=goals,
            is_confident=len(goals) > 0 and all(g.confidence >= 0.7 for g in output.goals),
            is_out_of_scope=output.is_out_of_scope,
            classifier_error=None
        )
