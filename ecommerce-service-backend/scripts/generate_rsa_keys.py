"""
生成 RSA 密钥对用于 RS256 JWT 签名
Private Key: Commerce Backend 用于签发 Token
Public Key: Agent Backend 用于验证 Token
"""
from pathlib import Path
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend


def generate_rsa_keypair():
    """生成 RSA 密钥对并保存到 keys 目录"""
    
    # 创建 keys 目录
    keys_dir = Path(__file__).parent.parent / "keys"
    keys_dir.mkdir(exist_ok=True)
    
    # 生成私钥
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
        backend=default_backend()
    )
    
    # 保存私钥（PEM 格式，无密码保护）
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    )
    
    private_key_path = keys_dir / "jwt_private_key.pem"
    private_key_path.write_bytes(private_pem)
    print(f"✅ 私钥已生成: {private_key_path}")
    
    # 提取公钥
    public_key = private_key.public_key()
    
    # 保存公钥（PEM 格式）
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    )
    
    public_key_path = keys_dir / "jwt_public_key.pem"
    public_key_path.write_bytes(public_pem)
    print(f"✅ 公钥已生成: {public_key_path}")
    
    print("\n⚠️  注意:")
    print("1. 私钥仅用于 Commerce Backend 签发 Token")
    print("2. 公钥需要复制到 Agent Backend 的 keys/ 目录")
    print("3. 生产环境务必妥善保管私钥，不要提交到代码仓库")


if __name__ == "__main__":
    generate_rsa_keypair()
