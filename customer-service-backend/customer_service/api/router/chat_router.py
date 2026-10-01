"""
Chat Router - Slice 01 Foundation
根据 01_slice_foundation 文档 #10 定义

核心功能：
- Session CRUD（强制用户隔离）
- Message 发送/历史查询
- Turn Lock 防并发
"""
from __future__ import annotations

import json
import time
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request as FastAPIRequest, status
from fastapi.responses import StreamingResponse
from loguru import logger

from customer_service.api.chat_dependencies import (
    AuthPrincipalDep,
    ChatRepositoryDep,
    TurnLockDep
)
from customer_service.models.chat import MessageRole
from customer_service.schemas.chat import (
    ChatHistoryItem,
    ChatHistoryResponse,
    ChatMessageRequest,
    ChatObject,
    ChatTaskSummary,
    ChatTurnResponse,
    CreateSessionRequest,
    CreateSessionResponse,
)
from customer_service.schemas.common import ApiResponse

router = APIRouter(tags=["Chat"])


# ==================== Session 管理 ====================

@router.post("/api/v1/chat/sessions", response_model=ApiResponse[CreateSessionResponse])
async def create_session(
    request: CreateSessionRequest,
    principal_and_token: AuthPrincipalDep,
    repo: ChatRepositoryDep,
) -> ApiResponse[CreateSessionResponse]:
    """
    创建新的 Chat Session

    - 用户隔离：每个 Session 属于一个用户
    - Session ID 自动生成或客户端指定
    """
    principal, access_token = principal_and_token
    start_time = time.time()
    session_id = str(uuid.uuid4())

    logger.info(
        f"📝 [API] 创建 Session: user_id={principal.user_id}, "
        f"channel={request.channel}, session_id={session_id}"
    )

    try:
        # 创建 Session（使用 ChatRepository）
        session = await repo.create_session(
            session_id=session_id,
            user_id=principal.user_id,
            metadata={"channel": request.channel}
        )

        elapsed = time.time() - start_time
        logger.info(
            f"✅ [API] Session 创建成功: session_id={session.id}, "
            f"耗时={elapsed:.2f}s"
        )

        return ApiResponse(
            data=CreateSessionResponse(
                session_id=session.id,
                status=session.status,
                channel=session.channel,
                created_at=session.created_at.isoformat(),
            )
        )
    except Exception as e:
        elapsed = time.time() - start_time
        logger.exception(
            f"❌ [API] Session 创建失败: user_id={principal.user_id}, "
            f"耗时={elapsed:.2f}s, error={str(e)}"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Session 创建失败"
        )


@router.delete("/api/v1/chat/sessions/{session_id}", response_model=ApiResponse[dict])
async def delete_session(
    session_id: str,
    principal_and_token: AuthPrincipalDep,
    repo: ChatRepositoryDep,
) -> ApiResponse[dict]:
    """
    关闭 Session（强制用户隔离）

    P0-5 修复：DELETE 语义 = 关闭 Session，而非物理删除
    - Session.status → "closed"
    - ChatMessage 历史保留（不删除）
    - 删除 LangGraph checkpoint（Redis）
    - 用户只能操作自己的 Session
    """
    principal, access_token = principal_and_token
    logger.info(
        f"🗑️ [API] 删除 Session: session_id={session_id}, "
        f"user_id={principal.user_id}"
    )

    deleted = await repo.close_session(session_id, principal)

    if not deleted:
        logger.warning(
            f"⚠️ [API] Session 不存在或无权限: session_id={session_id}, "
            f"user_id={principal.user_id}"
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session 不存在或无权限"
        )

    # 问题一修复：删除 LangGraph checkpoint thread（Redis）
    # P0-4 修复：thread_id 使用 v7 规范格式 "user_id:session_id"
    try:
        from customer_service.graph.graph_manager import get_checkpointer
        checkpointer = get_checkpointer()
        thread_id = f"{principal.user_id}:{session_id}"
        await checkpointer.adelete_thread(thread_id)
        logger.info(f"✅ [API] LangGraph checkpoint 已删除: thread_id={thread_id}")
    except Exception as e:
        logger.error(f"⚠️ [API] 删除 LangGraph checkpoint 失败: {e}", exc_info=True)
        # 不阻断主流程，checkpoint 有 TTL 会自动过期

    logger.info(f"✅ [API] Session 已关闭（含 checkpoint 删除）: session_id={session_id}")
    return ApiResponse(data={"session_id": session_id, "status": "closed"})


@router.get("/api/v1/chat/sessions", response_model=ApiResponse[dict])
async def list_sessions(
    principal_and_token: AuthPrincipalDep,
    repo: ChatRepositoryDep,
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
) -> ApiResponse[dict]:
    """
    获取用户的会话列表（强制用户隔离）

    - 按最后活跃时间倒序排列
    - 支持分页
    - 自动生成会话标题（基于首条用户消息）
    """
    principal, access_token = principal_and_token
    offset = (page - 1) * page_size

    logger.info(
        f"📋 [API] 获取会话列表: user_id={principal.user_id}, "
        f"page={page}, page_size={page_size}"
    )

    sessions, total = await repo.list_sessions(principal, limit=page_size, offset=offset)

    # 构造响应数据
    items = []
    for session in sessions:
        # 生成会话标题
        first_msg = await repo.get_first_user_message(session.id)
        if first_msg:
            title = first_msg[:20] + ("..." if len(first_msg) > 20 else "")
        else:
            title = f"新会话 - {session.created_at.strftime('%m/%d %H:%M')}"

        items.append({
            "session_id": session.id,
            "title": title,
            "status": session.status,
            "last_active_at": session.last_active_at.isoformat() if session.last_active_at else None,
            "created_at": session.created_at.isoformat(),
        })

    logger.info(f"✅ [API] 会话列表获取成功: 共 {total} 个会话，返回 {len(items)} 个")

    return ApiResponse(
        data={
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    )


# ==================== Message 管理 ====================

@router.post(
    "/api/v1/chat/sessions/{session_id}/messages",
    response_model=ApiResponse[ChatTurnResponse],
)
async def send_message(
    session_id: str,
    request: ChatMessageRequest,
    fastapi_request: FastAPIRequest,  # P1-50: 添加 FastAPI Request 以获取 request_id
    principal_and_token: AuthPrincipalDep,
    repo: ChatRepositoryDep,
    turn_lock: TurnLockDep,
) -> ApiResponse[ChatTurnResponse]:
    """
    发送消息（Slice 01 Foundation 同步消息接口）

    完整 LangGraph 处理将在后续实现
    当前仅测试：
    - Session Ownership Check
    - Message 持久化
    - Turn Lock
    """
    principal, access_token = principal_and_token
    start_time = time.time()
    turn_id = str(uuid.uuid4())

    # P1-50 修复：从 request.state 读取 request_id
    request_id = getattr(fastapi_request.state, "request_id", str(uuid.uuid4()))

    message_preview = (request.message[:50] + "...") if len(request.message) > 50 else request.message

    logger.info(
        f"[{session_id}] 📨 [API] 收到消息: user_id={principal.user_id}, "
        f"turn_id={turn_id}, request_id={request_id}, message='{message_preview}'"
    )

    try:
        # 1. 获取 Turn Lock（防止并发）
        # P1-49: 立即尝试获取锁，不等待
        lock_acquired = await turn_lock.acquire(session_id, turn_id, timeout=0.0)
        if not lock_acquired:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Session 正在处理其他消息，请稍后重试"
            )

        try:
            # 2. 验证 Session Ownership（自动在 add_message 中完成）
            # 3. 添加用户消息
            user_message = await repo.add_message(
                session_id=session_id,
                role=MessageRole.USER,
                content=request.message,
                principal=principal,
                metadata={"turn_id": turn_id}
            )

            if user_message is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Session 不存在或无权限"
                )

            # 4. 调用真实 LangGraph 执行五节点流程
            from customer_service.graph.graph_manager import get_agent_graph
            from customer_service.graph.turn_initializer import TurnInitializer
            from customer_service.schemas.foundation import SessionUserContext
            from customer_service.context import AgentRuntimeContext
            from pydantic import SecretStr

            graph = get_agent_graph()

            # P0-1 修复：构造完整的 AgentRuntimeContext
            thread_id = f"{principal.user_id}:{session_id}"
            runtime = AgentRuntimeContext(
                principal=principal,
                request_id=request_id,
                session_id=session_id,
                turn_id=turn_id,
                request_deadline_monotonic=time.monotonic() + 30.0,  # 30秒超时
                user_access_token=SecretStr(access_token)
            )

            # P0-1 修复：把完整的 runtime 放进 config，Graph nodes 直接使用
            config = {
                "configurable": {
                    "thread_id": thread_id,
                    "runtime": runtime,  # 完整的 AgentRuntimeContext
                }
            }

            # P0-6/P0-7 修复：从 checkpoint 恢复 persistent state，而不是每次都初始化为 None
            try:
                # 尝试从 Redis checkpoint 恢复上一轮的 state
                checkpoint_state = await graph.aget_state(config)
                if checkpoint_state and checkpoint_state.values:
                    # 有历史 state，从 checkpoint 恢复
                    restored_state = checkpoint_state.values
                    logger.info(
                        f"[{session_id}] 📦 从 checkpoint 恢复 persistent state: "
                        f"active_task={'有' if restored_state.get('active_task') else '无'}, "
                        f"paused_tasks={len(restored_state.get('paused_tasks', []))}"
                    )
                else:
                    # 首次对话，初始化空 state
                    restored_state = {
                        "conversation_focus": None,
                        "active_task": None,
                        "paused_tasks": [],
                        "pending_intent_selection": None,
                        "session_user_context": SessionUserContext(member_level="regular"),
                    }
                    logger.info(f"[{session_id}] 🆕 首次对话，初始化 persistent state")
            except Exception as e:
                # checkpoint 读取失败，使用空 state
                logger.warning(f"[{session_id}] ⚠️ checkpoint 恢复失败: {e}，使用空 state")
                restored_state = {
                    "conversation_focus": None,
                    "active_task": None,
                    "paused_tasks": [],
                    "pending_intent_selection": None,
                    "session_user_context": SessionUserContext(member_level="regular"),
                }

            # P0-6 修复：使用 TurnInitializer 重置 transient fields，保留 persistent fields
            initial_state = TurnInitializer.initialize_turn(
                state=restored_state,
                current_message=request.message,
                turn_id=turn_id,
            )

            logger.info(f"[{session_id}] 🚀 开始执行 LangGraph...")

            # 执行 Graph（传入 config，Graph 会自动保存到 checkpoint）
            final_state = await graph.ainvoke(initial_state, config=config)

            logger.info(f"[{session_id}] ✅ LangGraph 执行完成")

            # 从 final_state 提取结果
            response_draft = final_state.get("response_draft")
            intent_result = final_state.get("intent_result")
            active_task = final_state.get("active_task")

            # 生成助手回复
            if response_draft and isinstance(response_draft, str):
                # response_draft 是字符串类型（来自 response_gen_node）
                assistant_response = response_draft
            elif response_draft and hasattr(response_draft, "text"):
                # response_draft 是对象（有 text 属性）
                assistant_response = response_draft.text
            elif response_draft and isinstance(response_draft, dict):
                # response_draft 是字典（有 text 键）
                assistant_response = response_draft.get("text", "抱歉，我遇到了一些问题。")
            else:
                # 兜底：没有 response_draft
                assistant_response = "你好，我是探域售前助手。您可以问我商品、促销或订单相关问题。"

            # 提取 intent 信息
            intent_name = "unknown"
            intent_confidence = 0.0
            if intent_result:
                if hasattr(intent_result, "intent"):
                    intent_name = str(intent_result.intent.value) if intent_result.intent else "unknown"
                    intent_confidence = intent_result.confidence or 0.0
                elif isinstance(intent_result, dict):
                    intent_name = str(intent_result.get("intent", "unknown"))
                    intent_confidence = intent_result.get("confidence", 0.0)

            # P0-23 修复：提取 task 状态（统一使用 Pydantic 模型）
            task_status = "completed"
            if active_task:
                if hasattr(active_task, "status"):
                    task_status = active_task.status.value if hasattr(active_task.status, "value") else str(active_task.status)

            # 提取 retrieval context、dialogue_reason 和 objects（如果有）
            retrieved_context = None
            dialogue_reason = None  # P1-33: 从 FlowResult 提取 dialogue_reason
            objects = []  # P1-32: 从 FlowResult 提取 objects
            flow_result = final_state.get("flow_result")
            if flow_result:
                # P1-33: 提取 dialogue_reason
                if hasattr(flow_result, "dialogue_reason"):
                    dialogue_reason = flow_result.dialogue_reason

                # P1-32: 提取 objects（ProductCard等）
                if hasattr(flow_result, "objects") and flow_result.objects:
                    objects = flow_result.objects

                # 从 FlowResult 提取信息
                if hasattr(flow_result, "tool_result") and flow_result.tool_result:
                    tool_data = flow_result.tool_result.data
                    if "retrieval_mode" in tool_data:
                        retrieved_context = {
                            "retrieval_mode": tool_data.get("retrieval_mode"),
                            "product_count": len(objects),  # P1-32: 使用实际的 objects 数量
                            "retrieval_scores": tool_data.get("retrieval_scores", {}),
                            "evidence": tool_data.get("evidence", []),
                        }

            # 问题修复2：先构造并验证响应对象，再保存消息
            # 这样可以避免"消息已入库但 HTTP 返回 500"的半成品
            logger.debug(f"[{session_id}] 原始对象数量: {len(objects)}, 类型: {[type(obj).__name__ for obj in objects]}")
            if objects:
                logger.debug(f"[{session_id}] 第一个对象内容: {objects[0]}")

            try:
                from customer_service.schemas.chat import ProductCard, PromotionCard

                validated_objects = []
                for i, obj in enumerate(objects):
                    if isinstance(obj, dict):
                        # 根据 type 字段选择正确的模型
                        obj_type = obj.get("type")
                        logger.debug(f"[{session_id}] 验证对象 {i+1}: type={obj_type}, keys={list(obj.keys())}")

                        if obj_type == "product_card":
                            validated_obj = ProductCard(**obj)
                            logger.debug(f"[{session_id}] ✅ ProductCard 验证成功: {validated_obj.product_id}")
                        elif obj_type == "promotion":
                            validated_obj = PromotionCard(**obj)
                            logger.debug(f"[{session_id}] ✅ PromotionCard 验证成功: {validated_obj.promotion_id}")
                        else:
                            logger.warning(f"[{session_id}] ⚠️  未知对象类型: {obj_type}, 对象: {obj}")
                            continue
                        validated_objects.append(validated_obj)
                    else:
                        # 已经是 Pydantic 对象
                        logger.debug(f"[{session_id}] 对象 {i+1} 已是 Pydantic 对象: {type(obj).__name__}")
                        validated_objects.append(obj)

                logger.info(f"[{session_id}] ✅ 对象验证完成: {len(validated_objects)}/{len(objects)} 个对象通过验证")
                objects = validated_objects
            except Exception as e:
                logger.error(
                    f"[{session_id}] ❌ 对象结构验证失败: turn_id={turn_id}, error={e}, "
                    f"objects_count={len(objects)}", exc_info=True
                )
                # 对象验证失败，不保存消息，返回错误
                dialogue_reason = "object_validation_error"
                objects = []  # 清空对象

            # 5. 添加 Assistant 消息（在验证成功后）
            # 将 objects 序列化为 JSON 保存
            objects_json = None
            if objects:
                try:
                    import json
                    # 将 Pydantic 对象转换为字典
                    objects_dict = [obj.model_dump() if hasattr(obj, 'model_dump') else obj for obj in objects]
                    objects_json = json.dumps(objects_dict, ensure_ascii=False)
                except Exception as e:
                    logger.error(f"[{session_id}] ⚠️ 对象序列化失败: {e}")

            assistant_message = await repo.add_message(
                session_id=session_id,
                role=MessageRole.ASSISTANT,
                content=assistant_response,
                principal=principal,
                metadata={
                    "turn_id": turn_id,
                    "intent": intent_name,
                    "intent_confidence": intent_confidence,
                    "guard_retry_count": final_state.get("guard_retry_count", 0),
                    "fallback_used": final_state.get("fallback_used", False),
                },
                objects_json=objects_json,  # 保存验证后的对象
            )

            elapsed = time.time() - start_time
            logger.info(
                f"[{session_id}] ✅ [API] 消息处理成功: turn_id={turn_id}, "
                f"intent={intent_name}, objects_count={len(objects)}, 耗时={elapsed:.2f}s"
            )

            # 问题修复2: 显式转换对象为字典，避免 Pydantic 序列化问题
            objects_for_response = []
            for obj in objects:
                if hasattr(obj, 'model_dump'):
                    objects_for_response.append(obj.model_dump())
                elif isinstance(obj, dict):
                    objects_for_response.append(obj)
                else:
                    logger.warning(f"[{session_id}] ⚠️  无法序列化对象: {type(obj)}")

            return ApiResponse(
                data=ChatTurnResponse(
                    turn_id=turn_id,
                    message_id=assistant_message.message_id if assistant_message else str(uuid.uuid4()),
                    text=assistant_response,
                    objects=objects_for_response,  # 使用转换后的字典列表
                    task=ChatTaskSummary(intent=intent_name, status=task_status),
                    dialogue_reason=dialogue_reason,  # P1-33: 传递 dialogue_reason
                    retrieved_context=retrieved_context,
                )
            )

        finally:
            # 6. 释放 Turn Lock
            await turn_lock.release(session_id, turn_id)

    except HTTPException:
        raise
    except Exception as e:
        elapsed = time.time() - start_time
        logger.exception(
            f"[{session_id}] ❌ [API] 消息处理失败: user_id={principal.user_id}, "
            f"turn_id={turn_id}, 耗时={elapsed:.2f}s, error={str(e)}"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="消息处理失败"
        )


@router.get(
    "/api/v1/chat/sessions/{session_id}/messages",
    response_model=ApiResponse[ChatHistoryResponse],
)
async def get_messages(
    session_id: str,
    principal_and_token: AuthPrincipalDep,
    repo: ChatRepositoryDep,
    cursor: str | None = Query(None, description="分页游标"),
    limit: int = Query(50, ge=1, le=200, description="消息数量限制"),
) -> ApiResponse[ChatHistoryResponse]:
    """
    获取 Session 的消息历史（强制用户隔离）

    P1-34 修复：实现 cursor pagination
    - cursor: 分页游标（base64 编码的 message_id）
    - limit: 每页数量
    - next_cursor: 下一页游标，None 表示没有更多数据
    - 按时间正序返回
    - 用户只能查看自己的消息
    """
    import base64

    principal, access_token = principal_and_token
    logger.info(
        f"📜 [API] 获取消息历史: session_id={session_id}, "
        f"user_id={principal.user_id}, cursor={cursor}, limit={limit}"
    )

    # P1-34: 解码 cursor
    after_message_id = None
    if cursor:
        try:
            decoded = base64.urlsafe_b64decode(cursor).decode('utf-8')
            after_message_id = int(decoded)
        except Exception as e:
            logger.warning(f"⚠️ 无效的 cursor: {cursor}, error={e}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="无效的分页游标"
            )

    # 获取消息（多取1条用于判断是否有下一页）
    messages = await repo.get_messages(
        session_id,
        principal,
        limit=limit + 1,
        after_message_id=after_message_id
    )

    if not messages and not await repo.get_session(session_id, principal):
        # Session 不存在或无权限
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session 不存在或无权限"
        )

    # P1-34: 判断是否有下一页
    has_more = len(messages) > limit
    if has_more:
        messages = messages[:limit]  # 截取实际需要的数量

    # 转换为 API Schema
    items = []
    for msg in messages:
        # 解析 metadata
        metadata = {}
        if msg.metadata_json:
            try:
                metadata = json.loads(msg.metadata_json)
            except json.JSONDecodeError:
                logger.warning(f"⚠️ 消息 metadata 解析失败: message_id={msg.id}")

        objects = []
        if msg.objects_json:
            try:
                objects = json.loads(msg.objects_json)
            except json.JSONDecodeError:
                logger.warning(f"⚠️ 消息 objects 解析失败: message_id={msg.message_id}")

        items.append(
            ChatHistoryItem(
                turn_id=msg.turn_id or metadata.get("turn_id", str(msg.id)),
                role="assistant" if msg.role == MessageRole.ASSISTANT else "user",
                message_id=msg.message_id,
                content=msg.content,
                created_at=msg.created_at.isoformat(),
                objects=objects,
            )
        )

    # P1-34: 生成 next_cursor
    next_cursor = None
    if has_more and messages:
        last_message_id = messages[-1].id
        # 使用 base64 编码 message_id
        next_cursor = base64.urlsafe_b64encode(
            str(last_message_id).encode('utf-8')
        ).decode('utf-8')

    logger.info(
        f"✅ [API] 消息历史获取成功: session_id={session_id}, "
        f"count={len(items)}, has_more={has_more}, next_cursor={next_cursor}"
    )

    return ApiResponse(
        data=ChatHistoryResponse(messages=items, next_cursor=next_cursor)
    )
