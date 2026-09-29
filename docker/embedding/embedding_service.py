"""
BGE-M3 Embedding Service
使用 sentence-transformers 提供 embedding 服务
"""
import os
from typing import List, Union
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from sentence_transformers import SentenceTransformer
import logging

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 创建 FastAPI 应用
app = FastAPI(title="BGE-M3 Embedding Service")

# 全局模型变量
model = None
MODEL_PATH = "/models/bge-m3"


class EmbeddingRequest(BaseModel):
    """嵌入请求模型"""
    inputs: Union[str, List[str]]


class EmbeddingResponse(BaseModel):
    """嵌入响应模型"""
    embeddings: List[List[float]]


@app.on_event("startup")
async def load_model():
    """启动时加载模型"""
    global model
    try:
        logger.info(f"Loading BGE-M3 model from {MODEL_PATH}...")
        model = SentenceTransformer(MODEL_PATH)
        logger.info("Model loaded successfully!")
    except Exception as e:
        logger.error(f"Failed to load model: {e}")
        raise


@app.get("/health")
async def health_check():
    """健康检查端点"""
    if model is None:
        raise HTTPException(status_code=503, detail="Model not loaded")
    return {"status": "healthy", "model": "BAAI/bge-m3"}


@app.post("/embed", response_model=EmbeddingResponse)
async def embed(request: EmbeddingRequest):
    """生成文本嵌入"""
    if model is None:
        raise HTTPException(status_code=503, detail="Model not loaded")
    
    try:
        # 处理单个文本或文本列表
        if isinstance(request.inputs, str):
            texts = [request.inputs]
        else:
            texts = request.inputs
        
        # 生成嵌入
        embeddings = model.encode(
            texts,
            normalize_embeddings=True,
            show_progress_bar=False
        )
        
        # 转换为列表格式
        embeddings_list = embeddings.tolist()
        
        return EmbeddingResponse(embeddings=embeddings_list)
    
    except Exception as e:
        logger.error(f"Error generating embeddings: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/")
async def root():
    """根端点"""
    return {
        "service": "BGE-M3 Embedding Service",
        "model": "BAAI/bge-m3",
        "endpoints": {
            "/health": "Health check",
            "/embed": "Generate embeddings (POST)"
        }
    }
