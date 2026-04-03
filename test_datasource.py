"""
数据源测试脚本 - 检查各个数据源是否可用
"""
import sys
sys.path.insert(0, 'c:/Users/FY/WorkBuddy/Claw')

from quant_system.data.data_sources import (
    AkshareDataSource, 
    YfinanceDataSource, 
    SimulatedDataSource,
    MultiDataSource
)
import pandas as pd


def test_akshare():
    """测试 akshare 数据源"""
    print("=" * 60)
    print("测试 Akshare 数据源")
    print("=" * 60)
    
    source = AkshareDataSource()
    print(f"数据源名称: {source.name}")
    print(f"是否可用: {source.is_available}")
    
    if not source.is_available:
        print("[X] akshare 未安装")
        return False
    
    # 测试获取数据
    print("\n尝试获取 000001 (平安银行) 的数据...")
    try:
        df = source.get_daily_kline("000001", "2024-01-01", "2024-01-31")
        
        if not df.empty:
            print(f"[OK] 成功获取 {len(df)} 条数据")
            print(f"\n数据预览:")
            print(df.head())
            print(f"\n数据列: {df.columns.tolist()}")
            return True
        else:
            print("[X] 获取到空数据")
            return False
            
    except Exception as e:
        print(f"[X] 获取数据失败: {e}")
        import traceback
        print(traceback.format_exc())
        return False


def test_yfinance():
    """测试 yfinance 数据源"""
    print("\n" + "=" * 60)
    print("测试 Yfinance 数据源")
    print("=" * 60)
    
    source = YfinanceDataSource()
    print(f"数据源名称: {source.name}")
    print(f"是否可用: {source.is_available}")
    
    if not source.is_available:
        print("[X] yfinance 未安装")
        print("安装命令: pip install yfinance")
        return False
    
    # 测试获取数据
    print("\n尝试获取 000001 (平安银行) 的数据...")
    try:
        df = source.get_daily_kline("000001", "2024-01-01", "2024-01-31")
        
        if not df.empty:
            print(f"[OK] 成功获取 {len(df)} 条数据")
            print(f"\n数据预览:")
            print(df.head())
            return True
        else:
            print("[X] 获取到空数据")
            return False
            
    except Exception as e:
        print(f"[X] 获取数据失败: {e}")
        import traceback
        print(traceback.format_exc())
        return False


def test_simulated():
    """测试模拟数据源"""
    print("\n" + "=" * 60)
    print("测试 Simulated 数据源")
    print("=" * 60)
    
    source = SimulatedDataSource()
    print(f"数据源名称: {source.name}")
    print(f"是否可用: {source.is_available}")
    
    # 测试获取数据
    print("\n尝试获取 000001 (平安银行) 的模拟数据...")
    try:
        df = source.get_daily_kline("000001", "2024-01-01", "2024-01-31")
        
        if not df.empty:
            print(f"[OK] 成功生成 {len(df)} 条模拟数据")
            print(f"\n数据预览:")
            print(df.head())
            print(f"\n数据统计:")
            print(df.describe())
            return True
        else:
            print("[X] 生成数据失败")
            return False
            
    except Exception as e:
        print(f"[X] 生成数据失败: {e}")
        import traceback
        print(traceback.format_exc())
        return False


def test_multi_source():
    """测试多数据源管理器"""
    print("\n" + "=" * 60)
    print("测试 MultiDataSource (多数据源管理器)")
    print("=" * 60)
    
    mds = MultiDataSource()
    
    print(f"\n可用数据源列表:")
    for name in mds.get_available_sources():
        print(f"  - {name}")
    
    # 测试自动获取
    print("\n尝试自动获取数据...")
    try:
        df = mds.get_daily_kline("000001", "2024-01-01", "2024-01-31")
        
        if not df.empty:
            source_name = df['data_source'].iloc[0] if 'data_source' in df.columns else 'unknown'
            print(f"[OK] 成功获取 {len(df)} 条数据 (来源: {source_name})")
            return True
        else:
            print("[X] 获取数据失败")
            return False
            
    except Exception as e:
        print(f"[X] 获取数据失败: {e}")
        return False


def main():
    """运行所有测试"""
    print("\n" + "=" * 60)
    print("量化交易系统 - 数据源测试")
    print("=" * 60)
    
    results = {
        "Akshare": test_akshare(),
        "Yfinance": test_yfinance(),
        "Simulated": test_simulated(),
        "MultiSource": test_multi_source()
    }
    
    # 汇总结果
    print("\n" + "=" * 60)
    print("测试结果汇总")
    print("=" * 60)
    
    for name, result in results.items():
        status = "[OK] 通过" if result else "[X] 失败"
        print(f"{name}: {status}")
    
    # 建议
    print("\n" + "=" * 60)
    print("建议")
    print("=" * 60)
    
    if not results["Akshare"]:
        print("Akshare 不可用，可能原因:")
        print("1. 网络连接问题")
        print("2. akshare 版本过旧，尝试: pip install -U akshare")
        print("3. 东方财富接口限制")
    
    if not results["Yfinance"]:
        print("\nYfinance 不可用，如需使用请安装:")
        print("  pip install yfinance")
    
    if results["Simulated"]:
        print("\n[OK] 模拟数据可用，可以正常进行策略回测测试")


if __name__ == "__main__":
    main()
