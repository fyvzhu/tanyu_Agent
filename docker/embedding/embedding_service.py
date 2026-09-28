"""
BGE-M3 Embedding服务
提供向量化API供Phase 2使用
"""
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from sentence_transformers import SentenceTransformer
import logging

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="BGE-M3 Embedding Service")

# 加载本地模型
logger.info("正在加载BGE-M3模型...")
try:
    model = SentenceTransformer('/models/bge-m3')
    logger.info("✅ BGE-M3模型加载成功")
except Exception as e:
    logger.error(f"❌ 模型加载失败: {e}")
    model = None


class EmbeddingRequest(BaseModel):
    text: str | list[str]
    model: str = "bge-m3"


class EmbeddingResponse(BaseModel):
    embeddings: list[list[float]]
    model: str
    dimension: int


@app.post("/embeddings", response_model=EmbeddingResponse)
async def get_embeddings(req: EmbeddingRequest):
    """生成文本向量"""
    if model is None:
        raise HTTPException(500, "模型未加载")
    
    try:
        texts = [req.text] if isinstance(req.text, str) else req.text
        embeddings = model.encode(texts, normalize_embeddings=True)
        
        return {
            "embeddings": embeddings.tolist(),
            "model": req.model,
            "dimension": embeddings.shape[1]
        }
    except Exception as e:
        logger.error(f"向量化失败: {e}")
        raise HTTPException(500, f"向量化失败: {str(e)}")


@app.get("/health")
async def health():
    """健康检查"""
    return {
        "status": "healthy" if model is not None else "unhealthy",
        "model": "bge-m3",
        "model_loaded": model is not None
    }


@app.get("/")
async def root():
    """根路径"""
    return {
        "service": "BGE-M3 Embedding Service",
        "version": "1.0.0",
        "model": "BAAI/bge-m3",
        "endpoints": {
            "embeddings": "POST /embeddings",
            "health": "GET /health"
        }
    }
