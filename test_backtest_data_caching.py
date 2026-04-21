"""
测试完整回测场景的数据获取逻辑
"""
import sys
sys.path.insert(0, 'c:/Users/FY/WorkBuddy/Claw/quant_system')

from data.data_manager import DataManager
import pandas as pd

def test_backtest_scenario():
    print("=" * 60)
    print("测试回测场景数据获取")
    print("=" * 60)

    dm = DataManager()

    # 模拟回测参数
    symbol = '000001.SZ'
    start_date = '2023-01-01'
    end_date = '2024-03-19'

    print(f"\n回测参数: {symbol}, {start_date} ~ {end_date}")

    # 第一次调用 - 应该从 baostock 获取并保存
    print("\n=== 第一次调用 get_daily_kline ===")
    df1 = dm.get_daily_kline(symbol, start_date, end_date)
    print(f"返回: {len(df1)} 条数据")

    # 检查数据库
    db1 = dm._get_kline_from_db(symbol, start_date, end_date)
    print(f"数据库: {len(db1)} 条数据")

    # 第二次调用 - 应该从数据库读取
    print("\n=== 第二次调用 get_daily_kline ===")
    print("（如果数据库数据完整，应该直接从数据库读取，不打印 '从在线数据源获取...'）")
    df2 = dm.get_daily_kline(symbol, start_date, end_date)
    print(f"返回: {len(df2)} 条数据")

    print("\n" + "=" * 60)
    print("结论:")
    if len(df2) > 0 and df2.equals(df1):
        print("  [OK] 第二次调用从数据库读取，数据一致")
    else:
        print("  [可能有问题] 检查输出是否包含 '从在线数据源获取'")

    print("=" * 60)

if __name__ == '__main__':
    test_backtest_scenario()