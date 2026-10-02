"""
商品文本逻辑切分器

按照文档第 14 节要求，将商品知识卡片切分为语义逻辑块（不机械按字符切分）。

问题 #9 修复：使用稳定的 UUID5 作为 chunk ID，确保同一 chunk 的 ID 始终相同。
"""

import uuid
from typing import Literal
from pydantic import BaseModel, Field
from loguru import logger

ChunkType = Literal["overview", "selling_points", "material", "size"]

# UUID5 命名空间（用于生成确定性 chunk ID）
CHUNK_NAMESPACE = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")  # DNS namespace


class ProductChunk(BaseModel):
    """商品文本块"""

    chunk_id: str = Field(..., description="稳定的 UUID5 chunk ID")
    logical_id: str = Field(..., description="逻辑 ID: {product_id}:{chunk_type}:{ordinal}")
    product_id: str = Field(..., description="商品 ID")
    chunk_type: ChunkType = Field(..., description="Chunk 类型")
    text: str = Field(..., description="Chunk 文本内容")
    ordinal: int = Field(..., description="同类型 chunk 的序号")
    metadata: dict = Field(default_factory=dict, description="附加元数据")


class ProductChunker:
    """
    商品知识卡片逻辑切分器

    切分策略（不机械按字符切分）：
    1. overview chunk: brand + product_display_name + category
    2. selling_points chunks: 每个卖点一个 chunk（如果列表过长则合并）
    3. material chunk: 材质信息
    4. size chunk: 尺码摘要信息

    问题 #9 修复：
    - 使用 UUID5(logical_id) 生成稳定的 chunk_id
    - logical_id 格式: {product_id}:{chunk_type}:{ordinal}
    - 同一商品的同一 chunk 永远生成相同的 UUID
    """

    CHUNKER_VERSION = "v1"
    MAX_SELLING_POINTS = 10  # 最多保留的卖点数量

    @staticmethod
    def generate_chunk_id(logical_id: str) -> str:
        """
        生成稳定的 UUID5 chunk ID

        Args:
            logical_id: 逻辑 ID，格式 {product_id}:{chunk_type}:{ordinal}

        Returns:
            确定性的 UUID5 字符串
        """
        return str(uuid.uuid5(CHUNK_NAMESPACE, logical_id))
    
    def chunk_product(self, product_id: str, knowledge_card: dict) -> list[ProductChunk]:
        """
        将商品知识卡片切分为逻辑 chunks
        
        Args:
            product_id: 商品 ID
            knowledge_card: 商品知识卡片字典
            
        Returns:
            ProductChunk 列表
        """
        chunks = []
        
        logger.debug(f"开始切分商品 {product_id} 的知识卡片")
        
        # Chunk 1: Overview
        overview_chunk = self._build_overview_chunk(product_id, knowledge_card)
        if overview_chunk:
            chunks.append(overview_chunk)
        
        # Chunk 2-N: Selling Points
        selling_point_chunks = self._build_selling_point_chunks(product_id, knowledge_card)
        chunks.extend(selling_point_chunks)
        
        # Chunk N+1: Material
        material_chunk = self._build_material_chunk(product_id, knowledge_card)
        if material_chunk:
            chunks.append(material_chunk)
        
        # Chunk N+2: Size
        size_chunk = self._build_size_chunk(product_id, knowledge_card)
        if size_chunk:
            chunks.append(size_chunk)
        
        logger.info(f"商品 {product_id} 切分完成，生成 {len(chunks)} 个 chunks")
        return chunks
    
    def _build_overview_chunk(self, product_id: str, knowledge_card: dict) -> ProductChunk | None:
        """构建概览 chunk"""
        parts = []

        if brand := knowledge_card.get("brand"):
            parts.append(f"品牌: {brand}")
        if name := knowledge_card.get("product_display_name"):
            parts.append(f"商品: {name}")
        if category := knowledge_card.get("category"):
            parts.append(f"类别: {category}")

        if not parts:
            return None

        overview_text = " | ".join(parts)
        logical_id = f"{product_id}:overview:0"

        return ProductChunk(
            chunk_id=self.generate_chunk_id(logical_id),
            logical_id=logical_id,
            product_id=product_id,
            chunk_type="overview",
            text=overview_text,
            ordinal=0,
            metadata={
                "brand": knowledge_card.get("brand"),
                "category": knowledge_card.get("category"),
            }
        )
    
    def _build_selling_point_chunks(self, product_id: str, knowledge_card: dict) -> list[ProductChunk]:
        """构建卖点 chunks"""
        chunks = []

        # 尝试从 selling_points 或 features 字段获取
        selling_points = knowledge_card.get("selling_points") or knowledge_card.get("features") or []

        if not selling_points:
            return chunks

        # 限制卖点数量，避免生成过多 chunks
        selling_points = selling_points[:self.MAX_SELLING_POINTS]

        for i, point in enumerate(selling_points):
            if not point or not point.strip():
                continue

            logical_id = f"{product_id}:selling_points:{i}"
            chunks.append(ProductChunk(
                chunk_id=self.generate_chunk_id(logical_id),
                logical_id=logical_id,
                product_id=product_id,
                chunk_type="selling_points",
                text=point.strip(),
                ordinal=i,
                metadata={}
            ))

        return chunks
    
    def _build_material_chunk(self, product_id: str, knowledge_card: dict) -> ProductChunk | None:
        """构建材质 chunk"""
        material = knowledge_card.get("material")

        if not material or not material.strip():
            return None

        logical_id = f"{product_id}:material:0"
        return ProductChunk(
            chunk_id=self.generate_chunk_id(logical_id),
            logical_id=logical_id,
            product_id=product_id,
            chunk_type="material",
            text=f"材质: {material.strip()}",
            ordinal=0,
            metadata={}
        )

    def _build_size_chunk(self, product_id: str, knowledge_card: dict) -> ProductChunk | None:
        """构建尺码 chunk"""
        size_summary = knowledge_card.get("size_summary")

        if not size_summary or not size_summary.strip():
            return None

        logical_id = f"{product_id}:size:0"
        return ProductChunk(
            chunk_id=self.generate_chunk_id(logical_id),
            logical_id=logical_id,
            product_id=product_id,
            chunk_type="size",
            text=size_summary.strip(),
            ordinal=0,
            metadata={}
        )
