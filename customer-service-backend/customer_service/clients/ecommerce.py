"""
EcommerceClient - Commerce Backend HTTP 适配器
Agent 访问 Commerce API 的唯一入口
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

from customer_service.config.config import settings
from customer_service.tools.errors import ToolError, ToolExecutionError

logger = logging.getLogger(__name__)


class EcommerceClient:
    """
    Commerce Backend HTTP 适配器
    - 支持 Service-to-Service 认证（内部 API）
    - 支持用户委托认证（公开 API）
    - 统一的错误处理和重试机制
    """

    def __init__(self, base_url: str | None = None, service_token: str | None = None):
        self.base_url = (base_url or settings.commerce_api_base_url).rstrip("/")
        self.service_token = service_token or settings.commerce_service_token
        # 创建独立的 httpx 客户端
        self.http = httpx.AsyncClient(timeout=30.0)  # 提高超时到 30s
        logger.info(f"EcommerceClient 初始化: {self.base_url}")

    def _service_headers(self) -> dict[str, str]:
        """Service-to-Service 认证头"""
        return {
            "Authorization": f"Bearer {self.service_token}",
            "X-Service-Name": "customer-service-agent"
        }

    @staticmethod
    def _user_headers(user_access_token: str | None) -> dict[str, str]:
        """用户委托认证头"""
        if not user_access_token:
            raise ToolExecutionError(
                ToolError(
                    code="AUTH_REQUIRED",
                    message="missing delegated user token",
                    safe_message="请先登录后再操作。",
                )
            )
        return {"Authorization": f"Bearer {user_access_token}"}

    async def _request(
        self,
        method: str,
        path: str,
        *,
        user_token: str | None = None,
        internal: bool = False,
        request_id: str | None = None,  # P1-50: 添加 request_id 参数
        **kwargs
    ) -> Any:
        """
        统一的 HTTP 请求方法

        Args:
            method: HTTP 方法
            path: API 路径
            user_token: 用户 Access Token（委托认证）
            internal: 是否为内部 API（Service-to-Service）
            request_id: Request-ID（用于链路追踪）
            **kwargs: 传递给 httpx.request 的其他参数

        Returns:
            响应数据（data 字段）

        Raises:
            ToolExecutionError: 请求失败时抛出
        """
        headers = kwargs.pop("headers", {})

        # 设置认证头
        if internal:
            headers.update(self._service_headers())
        elif user_token is not None:
            headers.update(self._user_headers(user_token))

        # P1-50 修复：传播 Request-ID
        if request_id:
            headers["X-Request-ID"] = request_id

        url = f"{self.base_url}{path}"
        logger.debug(f"HTTP {method} {url} (internal={internal})")

        try:
            response = await self.http.request(method, url, headers=headers, **kwargs)
        except httpx.TimeoutException as exc:
            logger.error(f"请求超时: {url} - {exc}")
            raise ToolExecutionError(
                ToolError(
                    code="UPSTREAM_TIMEOUT",
                    message=str(exc),
                    safe_message="业务服务暂时繁忙，请稍后再试。",
                    retryable=True,
                )
            )
        except httpx.HTTPError as exc:
            logger.error(f"HTTP 错误: {url} - {exc}")
            raise ToolExecutionError(
                ToolError(
                    code="UPSTREAM_UNAVAILABLE",
                    message=str(exc),
                    safe_message="业务服务暂时不可用，请稍后再试。",
                    retryable=True,
                )
            )

        # 解析响应
        try:
            payload = response.json()
        except Exception as e:
            logger.error(f"JSON 解析失败: {response.text[:200]}")
            raise ToolExecutionError(
                ToolError(
                    code="INVALID_RESPONSE",
                    message=f"Invalid JSON: {str(e)}",
                    safe_message="服务响应格式错误。",
                    retryable=False,
                )
            )

        # 检查业务错误
        if response.status_code >= 400 or payload.get("success") is False:
            error = payload.get("error") or {}
            logger.warning(f"业务错误: {error.get('code')} - {error.get('message')}")
            raise ToolExecutionError(
                ToolError(
                    code=error.get("code") or f"HTTP_{response.status_code}",
                    message=error.get("message") or response.text,
                    safe_message=error.get("safe_message") or "业务处理失败。",
                    retryable=response.status_code >= 500,
                    details=error.get("details") or {},
                )
            )

        return payload.get("data")

    async def search_products(self, params: dict[str, Any]) -> dict[str, Any]:
        return await self._request("GET", "/api/v1/catalog/products", params=params)

    async def get_product(self, product_id: str, request_id: str | None = None) -> dict[str, Any]:
        return await self._request("GET", f"/api/v1/catalog/products/{product_id}", request_id=request_id)

    async def get_skus(self, product_id: str, request_id: str | None = None) -> list[dict[str, Any]]:
        data = await self._request("GET", f"/api/v1/catalog/products/{product_id}/skus", request_id=request_id)
        return data.get("items", [])

    async def get_size_chart(self, product_id: str, request_id: str | None = None) -> dict[str, Any]:
        return await self._request("GET", f"/api/v1/catalog/products/{product_id}/size-chart", request_id=request_id)

    async def knowledge_card(self, product_id: str, request_id: str | None = None) -> dict[str, Any]:
        return await self._request("GET", f"/internal/v1/products/{product_id}/knowledge-card", internal=True, request_id=request_id)

    async def batch_get_products(self, product_ids: list[str], request_id: str | None = None) -> list[dict[str, Any]]:
        if not product_ids:
            return []
        data = await self._request(
            "POST",
            "/internal/v1/products/batch-get",
            json={"product_ids": product_ids},
            internal=True,
            request_id=request_id,
        )
        return data if isinstance(data, list) else []

    async def product_assets(self, product_id: str, asset_type: str, request_id: str | None = None) -> dict[str, Any]:
        return await self._request(
            "GET",
            f"/internal/v1/products/{product_id}/assets",
            params={"asset_type": asset_type},
            internal=True,
            request_id=request_id,
        )

    async def active_promotions(
        self,
        product_id: str,
        user_access_token: str | None = None,
        request_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        获取特定商品的有效促销（P1-04 修复）

        使用用户 Access JWT 调用 Commerce 公开 API
        Commerce 从 JWT sub 查询真实用户 → 查真实 level → 根据 level + 时间 + product_id 过滤

        Args:
            product_id: 商品ID
            user_access_token: 用户 Access JWT（必需，用于获取真实用户等级）
            request_id: Request-ID（用于链路追踪）
        """
        # P1-04 修复：调用公开 API，使用用户委托认证
        data = await self._request(
            "GET",
            f"/api/v1/catalog/products/{product_id}/promotions",
            user_token=user_access_token,  # 传递用户 token
            request_id=request_id,
        )
        return data.get("items", [])

    async def list_active_promotions(
        self,
        user_access_token: str | None = None,
        request_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        获取所有有效促销（全局促销列表，P1-04 修复）

        使用用户 Access JWT 调用 Commerce API
        Commerce 从 JWT sub 自动过滤适用于该用户等级的促销

        Args:
            user_access_token: 用户 Access JWT（必需，用于获取真实用户等级）
            request_id: Request-ID（用于链路追踪）
        """
        data = await self._request(
            "GET",
            "/internal/v1/promotions/active",
            params={},  # P1-04 修复：不再传递 member_level 参数
            internal=False,  # 使用用户委托认证
            user_access_token=user_access_token,
            request_id=request_id,
        )
        return data.get("items", [])

    async def filter_skus(self, payload: dict[str, Any], request_id: str | None = None) -> list[dict[str, Any]]:
        data = await self._request("POST", "/internal/v1/skus/filter", json=payload, internal=True, request_id=request_id)
        return data.get("items", [])

    async def logistics(self, order_id: str, user_token: str, request_id: str | None = None) -> dict[str, Any]:
        return await self._request("GET", f"/api/v1/orders/{order_id}/logistics", user_token=user_token, request_id=request_id)

    async def create_return(
        self,
        order_id: str,
        payload: dict[str, Any],
        user_token: str,
        idempotency_key: str | None = None,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        headers = {"Idempotency-Key": idempotency_key} if idempotency_key else {}
        return await self._request(
            "POST",
            f"/api/v1/orders/{order_id}/return-requests",
            json=payload,
            user_token=user_token,
            headers=headers,
            request_id=request_id,
        )

    async def create_exchange(
        self,
        order_id: str,
        payload: dict[str, Any],
        user_token: str,
        idempotency_key: str | None = None,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        headers = {"Idempotency-Key": idempotency_key} if idempotency_key else {}
        return await self._request(
            "POST",
            f"/api/v1/orders/{order_id}/exchange-requests",
            json=payload,
            user_token=user_token,
            headers=headers,
            request_id=request_id,
        )

    async def create_shipping_urge(
        self,
        order_id: str,
        payload: dict[str, Any],
        user_token: str,
        idempotency_key: str | None = None,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        headers = {"Idempotency-Key": idempotency_key} if idempotency_key else {}
        return await self._request(
            "POST",
            f"/api/v1/orders/{order_id}/shipping-urge-requests",
            json=payload,
            user_token=user_token,
            headers=headers,
            request_id=request_id,
        )

    async def get_product_knowledge_card(self, product_id: str, request_id: str | None = None) -> dict[str, Any] | None:
        """
        获取商品知识卡片（供 RAG 索引使用）

        Args:
            product_id: 商品ID
            request_id: Request-ID（用于链路追踪）

        Returns:
            知识卡片数据，如果商品不存在返回 None
        """
        try:
            return await self._request(
                "GET",
                f"/internal/v1/products/{product_id}/knowledge-card",
                internal=True,
                request_id=request_id,
            )
        except ToolExecutionError as e:
            if e.error.code == "RESOURCE_NOT_FOUND":
                return None
            raise

    async def close(self) -> None:
        """关闭 HTTP 客户端"""
        await self.http.aclose()
        logger.info("EcommerceClient 已关闭")


# 全局单例实例
_ecommerce_client: EcommerceClient | None = None


def get_ecommerce_client() -> EcommerceClient:
    """获取全局 EcommerceClient 单例"""
    global _ecommerce_client
    if _ecommerce_client is None:
        _ecommerce_client = EcommerceClient()
    return _ecommerce_client


async def close_ecommerce_client() -> None:
    """关闭全局 EcommerceClient"""
    global _ecommerce_client
    if _ecommerce_client:
        await _ecommerce_client.close()
        _ecommerce_client = None
