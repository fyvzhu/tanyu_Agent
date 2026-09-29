FROM python:3.11-slim

WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 复制服务文件
COPY embedding_service.py .

# 安装 Python 依赖
RUN pip install --no-cache-dir \
    fastapi==0.115.4 \
    uvicorn[standard]==0.32.0 \
    sentence-transformers==3.3.1 \
    torch==2.6.0 \
    numpy==2.1.3

# 暴露端口
EXPOSE 80

# 启动服务
CMD ["uvicorn", "embedding_service:app", "--host", "0.0.0.0", "--port", "80"]
