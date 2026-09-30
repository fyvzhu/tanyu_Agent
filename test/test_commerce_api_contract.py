"""
Commerce API Contract 测试执行脚本

自动化执行以下步骤：
1. 检查Docker环境
2. 启动MySQL和Embedding服务
3. 导入测试数据
4. 启动Commerce服务
5. 运行Contract测试
6. 生成测试报告

测试内容：
- 商品列表API返回统一字段（category、main_image_url、价格范围等）
- SKU列表使用标准枚举值（in_stock/out_of_stock）
- 促销信息包含完整字段和标准枚举
- 图片URL可访问性
"""
import sys
import subprocess
import time
from pathlib import Path

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent
ECOMMERCE_BACKEND = PROJECT_ROOT / "ecommerce-service-backend"
DOCKER_DIR = PROJECT_ROOT / "docker"

# Python环境
PYTHON_ENV = r"C:\Users\HP\anaconda3\envs\ECommerce"
PYTHON_EXE = Path(PYTHON_ENV) / "python.exe"


def run_command(cmd, cwd=None, check=True):
    """运行命令并打印输出"""
    print(f"\n{'='*60}")
    print(f"执行命令: {cmd}")
    print(f"工作目录: {cwd or Path.cwd()}")
    print('='*60)

    result = subprocess.run(
        cmd,
        shell=True,
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding='utf-8',
        errors='replace'  # 忽略编码错误
    )

    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)

    if check and result.returncode != 0:
        print(f"❌ 命令执行失败，退出码: {result.returncode}")
        sys.exit(1)

    return result


def check_docker():
    """检查Docker是否运行"""
    print("\n🔍 检查Docker环境...")
    result = run_command("docker ps", check=False)
    if result.returncode != 0:
        print("❌ Docker未运行，请先启动Docker Desktop")
        sys.exit(1)
    print("✅ Docker正在运行")


def start_docker_services():
    """启动Docker服务"""
    print("\n🚀 启动Docker服务（MySQL + Embedding）...")
    
    # 停止并删除旧容器
    print("停止旧容器...")
    run_command("docker-compose down", cwd=DOCKER_DIR, check=False)
    
    # 启动MySQL和Embedding
    print("启动MySQL和Embedding服务...")
    run_command(
        "docker-compose up -d mysql embedding",
        cwd=DOCKER_DIR
    )
    
    # 等待MySQL启动
    print("等待MySQL启动（30秒）...")
    time.sleep(30)
    
    # 检查服务状态
    run_command("docker-compose ps", cwd=DOCKER_DIR)
    print("✅ Docker服务已启动")


def import_test_data():
    """导入测试数据"""
    print("\n📥 导入测试数据...")
    
    import_script = ECOMMERCE_BACKEND / "scripts" / "import_data.py"
    
    run_command(
        f'"{PYTHON_EXE}" "{import_script}"',
        cwd=ECOMMERCE_BACKEND
    )
    print("✅ 测试数据导入完成")


def start_commerce_service():
    """启动Commerce服务"""
    print("\n🚀 启动Commerce服务...")
    print("（服务将在后台运行，按Ctrl+C停止测试时会自动关闭）")
    
    # 使用uvicorn启动
    cmd = f'"{PYTHON_EXE}" -m uvicorn app.app:app --host 0.0.0.0 --port 8001 --reload'
    
    # 在后台启动（不等待）
    process = subprocess.Popen(
        cmd,
        shell=True,
        cwd=ECOMMERCE_BACKEND,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    
    # 等待服务启动
    print("等待服务启动（10秒）...")
    time.sleep(10)
    
    # 检查服务是否正常
    result = run_command(
        'Invoke-WebRequest -Uri http://localhost:8001/api/v1/catalog/products?page=1 -UseBasicParsing',
        check=False
    )
    
    if result.returncode == 0:
        print("✅ Commerce服务已启动")
    else:
        print("⚠️  服务可能未完全启动，继续执行...")
    
    return process


def run_tests():
    """运行Contract测试"""
    print("\n🧪 运行Commerce API Contract测试...")
    
    test_dir = ECOMMERCE_BACKEND / "tests" / "contract"
    
    # 安装pytest（如果还没有）
    print("检查pytest...")
    run_command(f'"{PYTHON_EXE}" -m pip install pytest pytest-asyncio httpx -q', check=False)
    
    # 运行测试
    run_command(
        f'"{PYTHON_EXE}" -m pytest "{test_dir}" -v --tb=short',
        cwd=ECOMMERCE_BACKEND
    )
    print("✅ 测试完成")


def main():
    """主流程"""
    print("="*60)
    print("Commerce API Contract 测试流程")
    print("="*60)
    
    try:
        # 1. 检查Docker
        check_docker()
        
        # 2. 启动Docker服务
        start_docker_services()
        
        # 3. 导入测试数据
        import_test_data()
        
        # 4. 启动Commerce服务
        commerce_process = start_commerce_service()
        
        # 5. 运行测试
        run_tests()
        
        print("\n" + "="*60)
        print("✅ 所有测试流程完成！")
        print("="*60)
        
    except KeyboardInterrupt:
        print("\n\n⚠️  测试被用户中断")
    except Exception as e:
        print(f"\n\n❌ 测试过程中出错: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # 清理：停止Commerce服务
        if 'commerce_process' in locals():
            print("\n🛑 停止Commerce服务...")
            commerce_process.terminate()
            commerce_process.wait()
        
        print("\n提示：Docker服务仍在运行，如需停止请执行: docker-compose -f docker/docker-compose.yml down")


if __name__ == "__main__":
    main()
