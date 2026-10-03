"""
Product Reference Resolver - 商品引用解析器

P2修复（参考修改建议2第十二节）：
将商品名称、品牌等文本引用解析为product_id。

核心思想：
1. 数字ID直接验证存在性
2. 商品名称通过EcommerceClient搜索
3. 品牌+类别组合查询
4. 返回唯一ID或候选列表

参考：ecommerce-customer-service 的 ProductResolver
"""
from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field
from loguru import logger

from customer_service.clients.ecommerce import get_ecommerce_client


class ProductResolution(BaseModel):
    """
    商品解析结果
    """
    resolved: bool = Field(..., description="是否成功解析")
    
    product_id: str | None = Field(None, description="解析到的商品ID（唯一时）")
    
    candidates: list[dict[str, Any]] = Field(
        default_factory=list,
        description="候选商品列表（多个匹配时）"
    )
    
    confidence: float = Field(
        default=1.0,
        description="解析置信度"
    )
    
    reasoning: str | None = Field(
        None,
        description="解析推理过程"
    )


class ProductReferenceResolver:
    """
    商品引用解析器
    
    职责：
    1. 数字ID直接返回
    2. 商品名称查询数据库
    3. 品牌+类别组合查询
    4. 处理多候选情况
    
    不职责：
    - 意图分类
    - 上下文推理（交给Context Resolver）
    """
    
    async def resolve(
        self,
        reference: str,
        context_hints: dict[str, Any] | None = None,
    ) -> ProductResolution:
        """
        解析商品引用

        Args:
            reference: 商品引用（可能是ID、名称、品牌等）
            context_hints: 上下文提示（category、brand等）

        Returns:
            ProductResolution
        """
        reference = reference.strip()
        context_hints = context_hints or {}

        client = get_ecommerce_client()

        # ===== 策略1：纯数字ID =====
        if reference.isdigit() and len(reference) in [4, 5, 6]:
            logger.info(f"[ProductResolver] 策略1: 纯数字ID={reference}")

            # 验证ID是否存在
            try:
                product = await client.get_product(reference)
                if product:
                    return ProductResolution(
                        resolved=True,
                        product_id=reference,
                        confidence=1.0,
                        reasoning="数字ID直接匹配"
                    )
            except Exception as e:
                logger.warning(f"[ProductResolver] 商品ID {reference} 不存在: {e}")
                return ProductResolution(
                    resolved=False,
                    reasoning=f"商品ID {reference} 不存在"
                )

        # ===== 策略2：商品名称搜索 =====
        logger.info(f"[ProductResolver] 策略2: 商品名称搜索 '{reference}'")

        try:
            # 使用EcommerceClient搜索
            search_params = {"q": reference}

            # 添加上下文提示
            if context_hints.get("brand"):
                search_params["brand"] = context_hints["brand"]
            if context_hints.get("category"):
                search_params["category"] = context_hints["category"]

            result = await client.search_products(search_params)
            products = result.get("items", [])

            if len(products) == 1:
                product = products[0]
                return ProductResolution(
                    resolved=True,
                    product_id=str(product["product_id"]),
                    confidence=0.9,
                    reasoning=f"商品搜索匹配: {product.get('product_display_name', '')}"
                )
            elif len(products) > 1:
                # 多个匹配
                candidates = [
                    {
                        "product_id": str(p["product_id"]),
                        "name": p.get("product_display_name", ""),
                        "brand": p.get("brand", ""),
                        "category": p.get("category", ""),
                    }
                    for p in products[:10]  # 最多返回10个候选
                ]
                return ProductResolution(
                    resolved=False,
                    candidates=candidates,
                    confidence=0.7,
                    reasoning=f"搜索匹配到{len(products)}个候选"
                )
            else:
                # 无匹配
                logger.warning(f"[ProductResolver] 搜索无结果: '{reference}'")
                return ProductResolution(
                    resolved=False,
                    reasoning=f"未找到匹配的商品: {reference}"
                )

        except Exception as e:
            logger.error(f"[ProductResolver] 搜索失败: {e}")
            return ProductResolution(
                resolved=False,
                reasoning=f"商品搜索失败: {str(e)}"
            )
