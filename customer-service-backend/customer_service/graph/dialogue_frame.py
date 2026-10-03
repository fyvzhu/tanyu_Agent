"""
DialogueFrame - 对话语义上下文帧

P2修复（参考修改建议2第八节）：
保存上一轮业务意图、焦点对象、槽位等语义信息，
用于支持省略式追问、意图继承、指代消解等多轮对话能力。

区别于：
- 对话历史 Memory（MySQL chat_messages）：原始消息文本
- 工作流 Memory（Redis Checkpoint）：active_task、paused_tasks
- 语义上下文 Memory（DialogueFrame）：上一业务意图、当前关注对象

参考：ecommerce-customer-service 的 DialogueState
"""
from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field

from customer_service.tasking.models import BusinessIntent


class FocusRef(BaseModel):
    """焦点对象引用"""
    entity_type: str = Field(..., description="对象类型: product/order/sku")
    entity_id: str = Field(..., description="对象ID")
    entity_name: str | None = Field(None, description="对象名称（可选）")
    
    def __str__(self):
        if self.entity_name:
            return f"{self.entity_type}:{self.entity_id}({self.entity_name})"
        return f"{self.entity_type}:{self.entity_id}"


class DialogueFrame(BaseModel):
    """
    对话语义上下文帧
    
    保存最近一次业务操作的语义信息，用于：
    1. 意图继承："那29570呢？" 继承上一轮的promotion_query意图
    2. 指代消解："这个呢？" 需要知道"这个"指的是哪个商品
    3. 槽位继承：切换商品ID后，其他槽位可能保持不变
    4. 任务恢复：知道最近完成的任务是什么
    """
    
    last_business_intent: BusinessIntent | None = Field(
        None,
        description="最近一次业务意图（promotion_query、product_query等）"
    )
    
    last_focus: FocusRef | None = Field(
        None,
        description="最近关注的对象（商品、订单等）"
    )
    
    last_slots: dict[str, Any] = Field(
        default_factory=dict,
        description="最近一次业务任务的槽位快照"
    )
    
    last_completed_task_id: str | None = Field(
        None,
        description="最近完成的任务ID"
    )
    
    last_updated_turn_id: str | None = Field(
        None,
        description="最后更新DialogueFrame的轮次ID"
    )
    
    def update_from_task(self, task, turn_id: str):
        """
        从Task更新DialogueFrame
        
        Args:
            task: TaskContext对象
            turn_id: 当前轮次ID
        """
        if task:
            self.last_business_intent = task.intent
            self.last_slots = task.slots.copy()
            
            # 如果slots中有商品ID，设置焦点
            if "product_id" in task.slots:
                self.last_focus = FocusRef(
                    entity_type="product",
                    entity_id=task.slots["product_id"],
                    entity_name=task.slots.get("product_name")
                )
            elif "order_id" in task.slots:
                self.last_focus = FocusRef(
                    entity_type="order",
                    entity_id=task.slots["order_id"]
                )
            
            self.last_updated_turn_id = turn_id
    
    def clear(self):
        """清空DialogueFrame"""
        self.last_business_intent = None
        self.last_focus = None
        self.last_slots = {}
        self.last_completed_task_id = None
        self.last_updated_turn_id = None
    
    def get_context_summary(self) -> str:
        """
        获取上下文摘要（用于日志和调试）
        
        Returns:
            上下文摘要字符串
        """
        if not self.last_business_intent:
            return "无上下文"
        
        parts = [f"意图={self.last_business_intent.value}"]
        
        if self.last_focus:
            parts.append(f"焦点={self.last_focus}")
        
        if self.last_slots:
            key_slots = {k: v for k, v in self.last_slots.items() if k in ["product_id", "order_id", "category"]}
            if key_slots:
                parts.append(f"槽位={key_slots}")
        
        return ", ".join(parts)
    
    def to_dict(self) -> dict[str, Any]:
        """转换为字典（用于持久化）"""
        return {
            "last_business_intent": self.last_business_intent.value if self.last_business_intent else None,
            "last_focus": self.last_focus.model_dump() if self.last_focus else None,
            "last_slots": self.last_slots,
            "last_completed_task_id": self.last_completed_task_id,
            "last_updated_turn_id": self.last_updated_turn_id,
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DialogueFrame:
        """从字典恢复（用于反序列化）"""
        return cls(
            last_business_intent=BusinessIntent(data["last_business_intent"]) if data.get("last_business_intent") else None,
            last_focus=FocusRef(**data["last_focus"]) if data.get("last_focus") else None,
            last_slots=data.get("last_slots", {}),
            last_completed_task_id=data.get("last_completed_task_id"),
            last_updated_turn_id=data.get("last_updated_turn_id"),
        )
