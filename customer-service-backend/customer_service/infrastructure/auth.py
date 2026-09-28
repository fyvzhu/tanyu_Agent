"""
JWT 认证工具 - RS256 本地验签
Agent 后端只验证 Commerce 后端签发的 JWT，不签发 Token
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from jose import JWTError, jwt
from fastapi import HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from loguru import logger

from customer_service.config.config import settings, absolute_project_path


class JWTVerifier:
    """RS256 JWT 验证器（唯一验签入口）"""

    def __init__(self):
        self._public_key: str | None = None
        self._key_path: Path | None = None

    def _load_public_key(self) -> str:
        """
        加载 RS256 公钥

        使用 absolute_project_path 确保路径解析一致性
        失败时立即中止，不回退备用路径
        """
        if self._public_key is None:
            try:
                # 使用统一的路径解析函数
                self._key_path = absolute_project_path(settings.jwt_public_key_path)

                if not self._key_path.exists():
                    raise FileNotFoundError(
                        f"JWT_KEY_CONFIG_ERROR: 公钥文件不存在: {self._key_path}\n"
                        f"请检查 JWT_PUBLIC_KEY_PATH 环境变量配置"
                    )

                self._public_key = self._key_path.read_text(encoding="utf-8")

                # 基本验证
                if not self._public_key.strip():
                    raise ValueError("JWT_KEY_CONFIG_ERROR: 公钥文件为空")

                if "BEGIN PUBLIC KEY" not in self._public_key:
                    raise ValueError("JWT_KEY_CONFIG_ERROR: 公钥格式不正确")

                # 成功日志（不输出密钥内容）
                logger.info(f"✅ [Agent] JWT 公钥加载成功: {self._key_path}")

            except Exception as e:
                raise RuntimeError(f"❌ [Agent] JWT 公钥加载失败，服务无法启动: {e}")

        return self._public_key

    def verify_token(self, token: str) -> dict[str, Any]:
        """
        验证 JWT Token（严格契约验证）

        验证项：
        1. RS256 签名
        2. issuer = tanyu-ecommerce-service
        3. audience = tanyu-services
        4. exp 未过期
        5. type = access（不接受 refresh）
        6. sub 非空

        Args:
            token: JWT Token 字符串

        Returns:
            解码后的 payload

        Raises:
            HTTPException: Token 无效或过期
        """
        try:
            public_key = self._load_public_key()

            # 验证签名、issuer、audience、exp
            payload = jwt.decode(
                token,
                public_key,
                algorithms=[settings.jwt_algorithm],
                audience=settings.jwt_audience,
                issuer=settings.jwt_issuer,
            )

            # 验证 type = access
            token_type = payload.get("type")
            if token_type != "access":
                logger.warning(f"JWT_CLAIMS_INVALID: 错误的 token type: {token_type}")
                raise JWTError("JWT_CLAIMS_INVALID: token type must be 'access'")

            # 验证 sub 非空
            sub = payload.get("sub")
            if not sub:
                logger.warning("JWT_CLAIMS_INVALID: 缺少 sub")
                raise JWTError("JWT_CLAIMS_INVALID: missing 'sub' claim")

            # 成功（只记录 sub，不记录 token）
            logger.info(f"✅ JWT 验证成功: sub={sub}")
            return payload

        except JWTError as e:
            error_msg = str(e)
            if "expired" in error_msg.lower():
                logger.warning(f"JWT_EXPIRED: {error_msg}")
                error_code = "JWT_EXPIRED"
            elif "signature" in error_msg.lower():
                logger.warning(f"JWT_SIGNATURE_INVALID: {error_msg}")
                error_code = "JWT_SIGNATURE_INVALID"
            else:
                logger.warning(f"JWT_CLAIMS_INVALID: {error_msg}")
                error_code = "JWT_CLAIMS_INVALID"

            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"code": error_code, "message": "Token 无效或已过期"},
                headers={"WWW-Authenticate": "Bearer"},
            )

        except Exception as e:
            logger.error(f"JWT 验证异常: {type(e).__name__}: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"code": "JWT_VERIFICATION_ERROR", "message": "Token 验证失败"},
                headers={"WWW-Authenticate": "Bearer"},
            )


# 全局 JWT 验证器实例（唯一实例）
jwt_verifier = JWTVerifier()


# FastAPI HTTPBearer 安全方案
security = HTTPBearer(auto_error=True)


async def get_current_user_payload(
    credentials: HTTPAuthorizationCredentials = HTTPBearer(auto_error=True),
) -> dict[str, Any]:
    """
    FastAPI 依赖：验证 JWT 并返回 payload

    这是唯一的 JWT 验证入口，所有需要认证的路由都应使用此依赖

    Returns:
        JWT payload（已验证）
    """
    token = credentials.credentials
    return jwt_verifier.verify_token(token)

