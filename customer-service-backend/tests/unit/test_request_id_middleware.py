"""
测试 Request-ID 中间件
P1-50: 验证 Request-ID HTTP 契约实现
"""
import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from customer_service.api.middleware.request_id import RequestIDMiddleware


@pytest.fixture
def app():
    """创建测试应用"""
    from fastapi import Request

    app = FastAPI()
    app.add_middleware(RequestIDMiddleware)

    @app.get("/test")
    async def test_endpoint(request: Request):
        return {"request_id": request.state.request_id}

    return app


@pytest.fixture
def client(app):
    """创建测试客户端"""
    return TestClient(app)


def test_request_id_from_header(client):
    """测试从请求头读取 Request-ID"""
    request_id = str(uuid.uuid4())
    response = client.get("/test", headers={"X-Request-ID": request_id})
    
    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == request_id
    assert response.json()["request_id"] == request_id


def test_request_id_case_insensitive(client):
    """测试 Request-ID 大小写不敏感"""
    request_id = str(uuid.uuid4())
    response = client.get("/test", headers={"x-request-id": request_id})
    
    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == request_id
    assert response.json()["request_id"] == request_id


def test_request_id_generated_when_missing(client):
    """测试当请求头中没有 Request-ID 时自动生成"""
    response = client.get("/test")
    
    assert response.status_code == 200
    assert "X-Request-ID" in response.headers
    
    # 验证生成的是有效的 UUID
    generated_id = response.headers["X-Request-ID"]
    try:
        uuid.UUID(generated_id)
    except ValueError:
        pytest.fail(f"Generated request_id '{generated_id}' is not a valid UUID")
    
    assert response.json()["request_id"] == generated_id


def test_request_id_in_response_header(client):
    """测试响应头中包含 Request-ID"""
    request_id = str(uuid.uuid4())
    response = client.get("/test", headers={"X-Request-ID": request_id})
    
    assert "X-Request-ID" in response.headers
    assert response.headers["X-Request-ID"] == request_id
