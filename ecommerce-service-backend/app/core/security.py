"""
安全模块：JWT认证和密码加密
"""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings, absolute_project_path

# ==================== RS256 密钥加载 ====================
def load_rsa_keys():
    """
    加载 RS256 私钥和公钥

    失败时立即中止启动，不回退到备用密钥
    """
    try:
        # 使用 absolute_project_path 转换为绝对路径
        private_key_path = absolute_project_path(settings.jwt_private_key_path)
        public_key_path = absolute_project_path(settings.jwt_public_key_path)

        # 验证文件存在
        if not private_key_path.exists():
            raise FileNotFoundError(
                f"JWT_KEY_CONFIG_ERROR: 私钥文件不存在: {private_key_path}\n"
                f"请检查 JWT_PRIVATE_KEY_PATH 环境变量配置"
            )

        if not public_key_path.exists():
            raise FileNotFoundError(
                f"JWT_KEY_CONFIG_ERROR: 公钥文件不存在: {public_key_path}\n"
                f"请检查 JWT_PUBLIC_KEY_PATH 环境变量配置"
            )

        # 读取密钥
        with open(private_key_path, 'r') as f:
            private_key = f.read()

        with open(public_key_path, 'r') as f:
            public_key = f.read()

        # 基本验证
        if not private_key.strip() or not public_key.strip():
            raise ValueError("JWT_KEY_CONFIG_ERROR: 密钥文件为空")

        if "BEGIN RSA PRIVATE KEY" not in private_key and "BEGIN PRIVATE KEY" not in private_key:
            raise ValueError("JWT_KEY_CONFIG_ERROR: 私钥格式不正确")

        if "BEGIN PUBLIC KEY" not in public_key:
            raise ValueError("JWT_KEY_CONFIG_ERROR: 公钥格式不正确")

        # 成功日志（不输出密钥内容）
        print(f"✅ [Commerce] JWT 密钥加载成功")
        print(f"   私钥路径: {private_key_path}")
        print(f"   公钥路径: {public_key_path}")

        return private_key, public_key

    except Exception as e:
        # 配置错误必须立即失败，不能继续启动
        raise RuntimeError(f"❌ [Commerce] JWT 密钥加载失败，服务无法启动: {e}")

# 加载密钥
JWT_PRIVATE_KEY, JWT_PUBLIC_KEY = load_rsa_keys()

# ==================== 密码加密 ====================
# Argon2 (推荐)
argon2_hasher = PasswordHasher()

# Bcrypt (备用)
bcrypt_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    """加密密码（使用Argon2id）"""
    if settings.password_hash_algorithm == "argon2":
        return argon2_hasher.hash(password)
    else:
        return bcrypt_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """验证密码"""
    if settings.password_hash_algorithm == "argon2":
        try:
            argon2_hasher.verify(hashed_password, plain_password)
            # 检查是否需要rehash
            if argon2_hasher.check_needs_rehash(hashed_password):
                # TODO: 更新数据库中的hash
                pass
            return True
        except VerifyMismatchError:
            return False
    else:
        # 修正：passlib bcrypt.verify(password, hash) 参数顺序
        # 第一个参数是明文密码，第二个参数是哈希值
        return bcrypt_context.verify(plain_password, hashed_password)


# ==================== JWT Token (RS256) ====================
def create_access_token(data: dict[str, Any], expires_delta: timedelta | None = None) -> str:
    """
    创建访问令牌 (RS256)

    P1-17 修复：添加 iat (issued at) 字段
    """
    to_encode = data.copy()
    now = datetime.utcnow()

    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=settings.jwt_access_token_expire_minutes)

    # 添加标准 JWT claims（P1-17：包含 iat）
    to_encode.update({
        "exp": expire,
        "iat": now,  # P1-17: issued at 时间戳
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "sub": data.get("user_id"),
        "type": "access"
    })

    encoded_jwt = jwt.encode(
        to_encode,
        JWT_PRIVATE_KEY,
        algorithm=settings.jwt_algorithm
    )

    return encoded_jwt


def create_refresh_token() -> str:
    """创建不透明的刷新令牌 (opaque token)"""
    # 生成 32 字节的随机令牌
    return secrets.token_urlsafe(32)


def hash_refresh_token(token: str) -> str:
    """对刷新令牌进行 SHA-256 哈希"""
    return hashlib.sha256(token.encode()).hexdigest()


def decode_token(token: str) -> dict[str, Any] | None:
    """解码JWT Token (使用 RS256 公钥)"""
    try:
        payload = jwt.decode(
            token,
            JWT_PUBLIC_KEY,
            algorithms=[settings.jwt_algorithm],
            audience=settings.jwt_audience,
            issuer=settings.jwt_issuer
        )
        return payload
    except JWTError:
        return None


def verify_internal_service_token(token: str) -> bool:
    """验证Internal API的Service Token"""
    return token == settings.internal_service_token
