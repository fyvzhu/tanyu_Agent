"""
S02-F02 测试：ProductQueryFlow 通过 ToolRuntime 调用统一 RAG

验证 P0-02/P0-03 修复：
- ProductQueryFlow 不再自建 ProductRetrievalService
- Discovery 路径通过 ToolRuntime 调用 product_search_tool
- Exact 路径不调用 RAG（RAG 调用数 = 0）
- Discovery 路径调用 product_search_tool 一次
- 硬约束不静默放宽（P1-05）
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from customer_service.flows.product import ProductQueryFlow
from customer_service.graph.state import AgentState
from customer_service.tools.models import ToolResult, ToolError
from customer_service.tools.base import EvidenceItem


@pytest.fixture
def mock_commerce_client():
    """Mock EcommerceClient"""
    client = AsyncMock()
    client.get_product = AsyncMock(return_value={
        "product_id": "15970",
        "product_display_name": "测试商品",
        "brand": "测试品牌",
        "price": 299.00,
    })
    client.get_skus = AsyncMock(return_value=[
        {"sku_id": "SKU001", "color": "黑色", "size": "M", "stock_quantity": 10}
    ])
    client.batch_get_products = AsyncMock(return_value=[])
    return client


@pytest.fixture
def mock_tool_runtime():
    """Mock ToolRuntime"""
    runtime = AsyncMock()
    return runtime


@pytest.mark.asyncio
async def test_exact_query_no_rag_call(mock_commerce_client, mock_tool_runtime):
    """
    Exact 场景：商品15970多少钱？
    验证：RAG 调用数 = 0，只调用 Commerce Direct
    """
    with patch('customer_service.flows.product.get_ecommerce_client', return_value=mock_commerce_client), \
         patch('customer_service.flows.product.get_global_tool_runtime', return_value=mock_tool_runtime):
        
        flow = ProductQueryFlow()
        
        state: AgentState = {
            "session_id": "test-session",
            "current_message": "商品15970多少钱？",
            "focused_object": None,
            "short_memory": {},
        }
        
        result = await flow.execute(state)
        
        # 断言：Direct 模式
        assert result["retrieval_mode"] == "direct"
        assert result["focused_product_id"] == "15970"
        
        # 核心断言：ToolRuntime 未被调用（RAG 调用数 = 0）
        mock_tool_runtime.execute.assert_not_called()
        
        # Commerce API 被调用
        mock_commerce_client.get_product.assert_called_once_with("15970")
        mock_commerce_client.get_skus.assert_called_once_with("15970")


@pytest.mark.asyncio
async def test_discovery_via_tool_runtime(mock_commerce_client, mock_tool_runtime):
    """
    Discovery 场景：想找舒适透气的 T 恤
    验证：通过 ToolRuntime 调用 product_search_tool 一次
    """
    # Mock 返回的 ToolResult
    mock_tool_result = ToolResult(
        tool_name="product_search_tool",
        ok=True,
        data={
            "retrieval_mode": "qdrant+es",
            "candidates": [
                {
                    "product_id": "101",
                    "brand": "品牌A",
                    "product_display_name": "舒适T恤",
                    "material": "纯棉",
                    "selling_points": ["透气", "柔软"],
                    "selected_sku": {"sku_id": "SKU101", "price": 89.00},
                    "score": 0.92,
                    "matched_reasons": ["透气", "舒适"],
                }
            ]
        },
        evidence=[
            EvidenceItem(
                source_type="rag",
                source_name="qdrant",
                reference_id="101",
                facts={"score": 0.92},
            )
        ],
    )

    # Mock tool spec with handler
    from customer_service.tools.runtime import ToolSpec
    from customer_service.tools.product_search import ProductSearchInput
    from customer_service.intents.models import BusinessIntent

    mock_handler = AsyncMock(return_value=mock_tool_result)
    mock_tool_spec = ToolSpec(
        name="product_search_tool",
        allowed_intents=(BusinessIntent.PRODUCT_QUERY,),
        side_effect=False,
        timeout_seconds=30.0,
        args_model=ProductSearchInput,
        handler=mock_handler,
    )

    # Mock registry
    mock_registry = MagicMock()
    mock_registry.get.return_value = mock_tool_spec

    with patch('customer_service.flows.product.get_ecommerce_client', return_value=mock_commerce_client), \
         patch('customer_service.flows.product.get_global_tool_runtime', return_value=mock_tool_runtime), \
         patch('customer_service.flows.product.get_global_tool_registry', return_value=mock_registry):

        flow = ProductQueryFlow()

        state: AgentState = {
            "session_id": "test-session",
            "current_message": "想找舒适透气的 T 恤",
            "focused_object": None,
            "short_memory": {},
        }

        result = await flow.execute(state)

        # 断言：RAG 模式
        assert result["retrieval_mode"] == "qdrant+es"
        assert len(result["products"]) == 1
        assert result["products"][0]["product_id"] == "101"

        # 验证：tool handler 被调用一次
        mock_handler.assert_called_once()


@pytest.mark.asyncio
async def test_strict_filter_no_relax(mock_commerce_client, mock_tool_runtime):
    """
    P1-05 验证：严格约束（400元以内黑色）无结果时不静默放宽
    """
    # Mock 返回的 ToolResult（严格匹配失败）
    mock_tool_result = ToolResult(
        tool_name="product_search_tool",
        ok=True,
        data={
            "retrieval_mode": "qdrant+es",
            "candidates": [],
            "strict_match_failed": True,
            "applied_filters": {
                "color": "黑色",
                "max_price": "400",
            }
        },
        evidence=[],
    )

    # Mock tool spec with handler
    from customer_service.tools.runtime import ToolSpec
    from customer_service.tools.product_search import ProductSearchInput
    from customer_service.intents.models import BusinessIntent

    mock_handler = AsyncMock(return_value=mock_tool_result)
    mock_tool_spec = ToolSpec(
        name="product_search_tool",
        allowed_intents=(BusinessIntent.PRODUCT_QUERY,),
        side_effect=False,
        timeout_seconds=30.0,
        args_model=ProductSearchInput,
        handler=mock_handler,
    )

    # Mock registry
    mock_registry = MagicMock()
    mock_registry.get.return_value = mock_tool_spec

    with patch('customer_service.flows.product.get_ecommerce_client', return_value=mock_commerce_client), \
         patch('customer_service.flows.product.get_global_tool_runtime', return_value=mock_tool_runtime), \
         patch('customer_service.flows.product.get_global_tool_registry', return_value=mock_registry):

        flow = ProductQueryFlow()

        state: AgentState = {
            "session_id": "test-session",
            "current_message": "有没有400元以内的黑色通勤裙？",
            "focused_object": None,
            "short_memory": {},
        }

        result = await flow.execute(state)

        # 断言：返回空列表，但标记了严格匹配失败
        assert len(result["products"]) == 0
        # 注意：strict_match_failed 在 Tool 的 data 中，Flow 需要传递

        # 验证：tool handler 被调用一次
        mock_handler.assert_called_once()
