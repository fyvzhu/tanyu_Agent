FROM python:3.11-slim

WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 安装Python依赖（使用与你环境相同的版本）
RUN pip install --no-cache-dir \
    fastapi==0.141.1 \
    uvicorn[standard]==0.52.1 \
    sentence-transformers==6.0.1 \
    torch==2.14.0

# 复制服务脚本
COPY embedding_service.py /app/

# 模型通过volume挂载，不复制到镜像
# 挂载路径: /models/bge-m3

EXPOSE 8000

CMD ["uvicorn", "embedding_service:app", "--host", "0.0.0.0", "--port", "8000"]
