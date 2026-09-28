"""
检索结果融合算法 - RRF (Reciprocal Rank Fusion)
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def reciprocal_rank_fusion(
    results_list: list[list[tuple[str, float]]],
    k: int = 60
) -> list[tuple[str, float]]:
    """
    RRF (Reciprocal Rank Fusion) 算法融合多个检索结果

    P1-44 修复：先将每个来源的 chunk 聚合到商品级，再进行 RRF 融合
    避免拥有更多 chunk 的商品获得不公平的优势

    公式: score(d) = sum(1 / (k + rank(d))) for all occurrences

    Args:
        results_list: 多个检索结果列表，每个元素为 [(chunk_id, score), ...]
        k: 平滑参数，通常取 60

    Returns:
        融合后的结果列表 [(product_id, fused_score), ...]，按分数降序排列

    Example:
        >>> qdrant_results = [("p1:overview:0", 0.9), ("p2:material:0", 0.8)]
        >>> es_results = [("p2:selling_points:0", 0.95), ("p3:overview:0", 0.7)]
        >>> fused = reciprocal_rank_fusion([qdrant_results, es_results])
        >>> # p2 会获得更高分数，因为在两个列表中都出现
    """
    scores: dict[str, float] = {}

    for results in results_list:
        # P1-44: 先聚合到商品级（每个来源单独聚合）
        product_scores = aggregate_chunks_to_products(results)

        # 对聚合后的商品结果按分数排序
        sorted_products = sorted(product_scores.items(), key=lambda x: x[1], reverse=True)

        # 对商品级结果进行 RRF 加分
        for rank, (product_id, _) in enumerate(sorted_products, start=1):
            rrf_score = 1.0 / (k + rank)
            scores[product_id] = scores.get(product_id, 0.0) + rrf_score

    # 按分数降序排序
    sorted_results = sorted(scores.items(), key=lambda x: x[1], reverse=True)

    logger.debug(
        f"RRF fusion (P1-44 fixed): {len(results_list)} sources -> {len(sorted_results)} products"
    )

    return sorted_results


def aggregate_chunks_to_products(
    chunk_results: list[tuple[str, float]]
) -> dict[str, float]:
    """
    将 chunk 级别的结果聚合到 product 级别
    
    chunk_id 格式: {product_id}:{chunk_type}:{ordinal}
    例如: "12345:overview:0", "12345:selling_points:0"
    
    聚合策略：使用最大分数（max pooling）
    
    Args:
        chunk_results: chunk 级别的检索结果 [(chunk_id, score), ...]
        
    Returns:
        product 级别的分数字典 {product_id: max_score}
        
    Example:
        >>> chunks = [
        ...     ("12345:overview:0", 0.9),
        ...     ("12345:selling_points:0", 0.85),
        ...     ("67890:material:0", 0.8)
        ... ]
        >>> products = aggregate_chunks_to_products(chunks)
        >>> # {"12345": 0.9, "67890": 0.8}
    """
    product_scores: dict[str, float] = {}
    
    for chunk_id, score in chunk_results:
        try:
            # 解析 chunk_id: {product_id}:{chunk_type}:{ordinal}
            parts = chunk_id.split(":")
            if len(parts) < 1:
                logger.warning(f"Invalid chunk_id format: {chunk_id}")
                continue
            
            product_id = parts[0]
            
            # 使用最大分数（也可以用平均、加权等策略）
            current_score = product_scores.get(product_id, 0.0)
            product_scores[product_id] = max(current_score, score)
            
        except Exception as e:
            logger.warning(f"Failed to parse chunk_id {chunk_id}: {e}")
            continue
    
    logger.debug(
        f"Aggregated {len(chunk_results)} chunks -> {len(product_scores)} products"
    )
    
    return product_scores


def merge_scores_with_reasons(
    scores: dict[str, float],
    reasons_lists: list[dict[str, list[str]]]
) -> dict[str, list[str]]:
    """
    合并多个来源的匹配原因
    
    Args:
        scores: 融合后的商品分数 {product_id: score}
        reasons_lists: 多个来源的匹配原因列表
        
    Returns:
        合并后的匹配原因 {product_id: [reason1, reason2, ...]}
    """
    merged_reasons: dict[str, list[str]] = {}
    
    for product_id in scores.keys():
        reasons_set = set()
        
        for reasons_dict in reasons_lists:
            if product_id in reasons_dict:
                for reason in reasons_dict[product_id]:
                    reasons_set.add(str(reason))
        
        merged_reasons[product_id] = list(reasons_set)
    
    return merged_reasons


def apply_boost_factors(
    scores: dict[str, float],
    boost_config: dict[str, float]
) -> dict[str, float]:
    """
    应用加权因子（例如优先展示某些品牌或类别）
    
    Args:
        scores: 原始分数 {product_id: score}
        boost_config: 加权配置 {product_id: boost_factor}
        
    Returns:
        加权后的分数
    """
    boosted_scores = scores.copy()
    
    for product_id, boost in boost_config.items():
        if product_id in boosted_scores:
            boosted_scores[product_id] *= boost
            logger.debug(f"Applied boost {boost} to product {product_id}")
    
    return boosted_scores
