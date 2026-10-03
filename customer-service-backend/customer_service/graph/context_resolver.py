"""
Context Resolver - 上下文解析器

P2修复（参考修改建议2第十、十一节）：
规则优先的上下文解析，处理省略式追问、指代消解、意图继承等多轮对话场景。

核心思想：
1. 规则处理高频确定场景（90%+）
2. LLM处理复杂边缘场景（兜底）
3. 不依赖具体业务意图，通用化设计

参考：ecommerce-customer-service 的 Context Resolution
"""
from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, Field
from loguru import logger

from customer_service.tasking.models import BusinessIntent, TaskFrame
from customer_service.graph.dialogue_frame import DialogueFrame
from customer_service.intents.entity_extractor import extract_entities


class ContextResolution(BaseModel):
    """
    上下文解析结果
    
    mode说明：
    - none: 无需上下文处理，按正常流程
    - continue_active_task: 继续当前活跃任务（补槽）
    - repeat_last_intent: 重复上一轮意图（"那29570呢？"）
    - new_explicit_goal: 显式新目标（"我要查订单"）
    """
    mode: Literal[
        "none",
        "continue_active_task",
        "repeat_last_intent",
        "new_explicit_goal",
    ] = Field(..., description="上下文解析模式")
    
    inherited_intent: BusinessIntent | None = Field(
        None,
        description="继承的意图（mode=repeat_last_intent时有效）"
    )
    
    entity_updates: dict[str, Any] = Field(
        default_factory=dict,
        description="实体更新（如product_id、color等）"
    )
    
    confidence: float = Field(
        default=1.0,
        description="解析置信度（规则=1.0，LLM<1.0）"
    )
    
    reasoning: str | None = Field(
        None,
        description="解析推理过程（调试用）"
    )


class ContextResolver:
    """
    上下文解析器 - 规则优先
    
    职责：
    1. 检测省略式追问（"那29570呢？"）
    2. 检测指代表达（"这个"、"那个"）
    3. 检测补槽场景（active_task缺槽位）
    4. 提取实体更新
    5. LLM兜底（复杂场景）
    
    不职责：
    - 意图分类（交给IntentClassifier）
    - 槽位验证（交给SlotCheck）
    - 商品名解析（交给ProductReferenceResolver）
    """
    
    def __init__(self, use_llm_fallback: bool = False):
        """
        Args:
            use_llm_fallback: 是否启用LLM兜底（暂未实现）
        """
        self.use_llm_fallback = use_llm_fallback
    
    def resolve(
        self,
        current_message: str,
        dialogue_frame: DialogueFrame | None,
        active_task: TaskFrame | None,
        turn_id: str,
    ) -> ContextResolution:
        """
        解析上下文
        
        Args:
            current_message: 当前用户消息
            dialogue_frame: 对话语义帧
            active_task: 当前活跃任务
            turn_id: 轮次ID
        
        Returns:
            ContextResolution
        """
        text = current_message.strip()
        
        # ===== 规则1：检测补槽场景 =====
        # 如果有active_task且缺少关键槽位，优先判定为补槽
        if active_task and active_task.slots.get("missing_slots"):
            missing = active_task.slots["missing_slots"]
            logger.info(f"[{turn_id}] Context规则1: 补槽场景, missing={missing}")

            # 提取实体，看是否包含缺失槽位
            entities = extract_entities(text)
            filled_slots = {k: v for k, v in entities.items() if k in missing}

            if filled_slots:
                return ContextResolution(
                    mode="continue_active_task",
                    entity_updates=filled_slots,
                    confidence=1.0,
                    reasoning=f"补槽: {list(filled_slots.keys())}"
                )
            # 如果没有提取到槽位，也可能是用户输入的就是槽位值（纯文本）
            # 例如用户回复"29570"补product_id
            elif len(missing) == 1 and text.strip().isdigit() and len(text.strip()) in [4, 5, 6]:
                # 纯数字且长度合理，当作product_id
                slot_name = missing[0]
                if slot_name == "product_id":
                    return ContextResolution(
                        mode="continue_active_task",
                        entity_updates={"product_id": text.strip()},
                        confidence=1.0,
                        reasoning=f"补槽: 纯数字输入视为{slot_name}"
                    )

        # ===== 规则2：检测指代表达（优先于省略式追问）=====
        # "这个怎么样？"、"那个有货吗？"
        if self._has_referential_expression(text):
            logger.info(f"[{turn_id}] Context规则2: 指代表达")

            # 需要结合dialogue_frame.last_focus解析
            if dialogue_frame and dialogue_frame.last_focus:
                # 将指代词解析为具体实体
                entity_type = dialogue_frame.last_focus.entity_type
                entity_id = dialogue_frame.last_focus.entity_id

                # 根据实体类型设置对应的ID字段
                if entity_type == "product":
                    entity_updates = {"product_id": entity_id}
                elif entity_type == "order":
                    entity_updates = {"order_id": entity_id}
                else:
                    entity_updates = {f"{entity_type}_id": entity_id}

                # 如果有上一轮意图，也继承
                inherited_intent = dialogue_frame.last_business_intent

                return ContextResolution(
                    mode="repeat_last_intent" if inherited_intent else "none",
                    inherited_intent=inherited_intent,
                    entity_updates=entity_updates,
                    confidence=0.9,  # 指代消解置信度略低
                    reasoning=f"指代消解: {dialogue_frame.last_focus}"
                )

        # ===== 规则3：检测省略式追问（重复上一轮意图）=====
        # "那29570呢？"、"这个呢？"、"那黑色呢？"
        if self._is_elliptical_followup(text):
            logger.info(f"[{turn_id}] Context规则3: 省略式追问")

            # 尝试从dialogue_frame获取上一轮意图
            inherited_intent = None
            if dialogue_frame and dialogue_frame.last_business_intent:
                inherited_intent = dialogue_frame.last_business_intent
            elif active_task:
                inherited_intent = active_task.intent

            if inherited_intent:
                # 提取实体更新
                entities = extract_entities(text)

                return ContextResolution(
                    mode="repeat_last_intent",
                    inherited_intent=inherited_intent,
                    entity_updates=entities,
                    confidence=1.0,
                    reasoning=f"省略式追问，继承意图: {inherited_intent.value}"
                )

        # ===== 规则4：无需上下文处理 =====
        # 显式完整的目标："我要查订单"、"推荐男士衬衫"
        logger.info(f"[{turn_id}] Context规则4: 无需上下文，显式目标")
        return ContextResolution(
            mode="new_explicit_goal",
            confidence=1.0,
            reasoning="显式完整目标，无需上下文继承"
        )
    
    def _is_elliptical_followup(self, text: str) -> bool:
        """
        检测省略式追问
        
        复用intents/classifier.py中的_is_elliptical_followup逻辑
        """
        from customer_service.intents.classifier import _is_elliptical_followup
        return _is_elliptical_followup(text)
    
    def _has_referential_expression(self, text: str) -> bool:
        """
        检测指代表达
        
        Examples:
            - "这个怎么样？"
            - "那个有货吗？"
            - "它能退吗？"
        
        注意：要排除"这款"、"那款"等完整表达
        """
        # 指代词
        referential_markers = ["这个", "那个", "它", "他"]
        has_marker = any(marker in text for marker in referential_markers)
        
        # 排除完整表达
        if "款" in text or "种" in text or "类" in text:
            return False
        
        return has_marker and len(text) < 20  # 指代通常很短
