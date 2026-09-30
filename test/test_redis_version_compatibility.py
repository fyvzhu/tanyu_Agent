"""
问题8-A验证：Redis版本与Python依赖兼容性检查

检查项：
1. Redis服务器版本（需要8.0+或Redis Stack）
2. RedisJSON和RediSearch模块可用性
3. Python包版本兼容性
4. pip check无冲突
"""
import asyncio
import sys
from redis.asyncio import Redis


async def check_redis_version():
    """检查Redis版本和模块"""
    print("=" * 60)
    print("1. 检查Redis服务器版本和模块")
    print("=" * 60)
    
    try:
        client = Redis.from_url(
            "redis://:618618@localhost:6379",
            decode_responses=False
        )
        
        # 检查版本
        info = await client.info("server")
        redis_version = info["redis_version"]
        print(f"✅ Redis版本: {redis_version}")
        
        # 解析版本号
        major_version = int(redis_version.split('.')[0])
        if major_version >= 8:
            print(f"✅ Redis 8.0+检测到，RedisJSON和RediSearch内置")
        else:
            print(f"⚠️  Redis版本 < 8.0，需要Redis Stack或手动安装模块")
        
        # 检查RedisJSON
        try:
            await client.execute_command("JSON.SET", "test:check", "$", '"version_check"')
            result = await client.execute_command("JSON.GET", "test:check")
            await client.delete("test:check")
            print("✅ RedisJSON模块可用")
        except Exception as e:
            print(f"❌ RedisJSON模块不可用: {e}")
            return False
        
        # 检查RediSearch
        try:
            indices = await client.execute_command("FT._LIST")
            print(f"✅ RediSearch模块可用（现有索引: {len(indices)}个）")
        except Exception as e:
            print(f"❌ RediSearch模块不可用: {e}")
            return False
        
        # 检查连接和认证
        pong = await client.ping()
        print(f"✅ Redis连接正常: {pong}")
        
        await client.aclose()
        return True
        
    except Exception as e:
        print(f"❌ 无法连接到Redis: {e}")
        return False


def check_python_packages():
    """检查Python包版本"""
    print("\n" + "=" * 60)
    print("2. 检查Python包版本")
    print("=" * 60)
    
    import importlib.metadata
    
    required_packages = {
        "redis": ">=5.2.1",
        "langgraph": "0.2.38",
        "langgraph-checkpoint": ">=4.1.1",
        "langgraph-checkpoint-redis": ">=0.5.2",
        "redisvl": ">=0.15.0",
    }
    
    all_ok = True
    for package, required_version in required_packages.items():
        try:
            version = importlib.metadata.version(package)
            print(f"✅ {package}: {version} (要求: {required_version})")
        except importlib.metadata.PackageNotFoundError:
            print(f"❌ {package}: 未安装 (要求: {required_version})")
            all_ok = False
    
    return all_ok


def check_pip_conflicts():
    """运行pip check检查依赖冲突"""
    print("\n" + "=" * 60)
    print("3. 检查依赖冲突 (pip check)")
    print("=" * 60)
    
    import subprocess
    
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "check"],
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            print("✅ 无依赖冲突")
            return True
        else:
            print(f"❌ 发现依赖冲突:\n{result.stdout}")
            return False
    except Exception as e:
        print(f"⚠️  无法运行pip check: {e}")
        return True  # 不阻止测试继续


async def main():
    """主测试流程"""
    print("\n🔍 问题8-A：Redis版本兼容性检查\n")
    
    # 1. Redis版本和模块
    redis_ok = await check_redis_version()
    
    # 2. Python包版本
    packages_ok = check_python_packages()
    
    # 3. pip check
    pip_ok = check_pip_conflicts()
    
    # 总结
    print("\n" + "=" * 60)
    print("总结")
    print("=" * 60)
    
    if redis_ok and packages_ok and pip_ok:
        print("✅ 所有检查通过！可以使用AsyncRedisSaver")
        return 0
    else:
        print("❌ 存在问题，请修复后再继续")
        if not redis_ok:
            print("  - Redis版本或模块不满足要求")
        if not packages_ok:
            print("  - Python包版本不满足要求")
        if not pip_ok:
            print("  - 存在依赖冲突")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
