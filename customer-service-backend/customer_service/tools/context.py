from __future__ import annotations

from pydantic import BaseModel, Field

from customer_service.context.runtime import AgentRuntimeContext
from customer_service.tasking.models import ActionMode, BusinessIntent


class ToolExecutionContext(BaseModel):
    runtime: AgentRuntimeContext = Field(exclude=True)
    intent: BusinessIntent
    task_id: str | None = None
    action_mode: ActionMode | None = None

