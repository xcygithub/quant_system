"""
测试数据获取和保存流程
"""
import sys
sys.path.insert(0, 'c:/Users/FY/WorkBuddy/Claw/quant_system')

from data.data_manager import DataManager
import pandas as pd

def test_data_fetch_and_save():
    """测试数据获取和保存"""
    print("=" * 60)
    print("测试数据获取和保存流程")
    print("=" * 60)

    dm = DataManager()

    symbol = '000001.SZ'
    start_date = '2024-01-01'
    end_date = '2024-03-19'

    print(f"\n1. 调用 dm.get_daily_kline('{symbol}', '{start_date}', '{end_date}')")

    # 先检查数据库中有什么
    print("\n2. 检查数据库中现有数据...")
    existing = dm._get_kline_from_db(symbol, start_date, end_date)
    print(f"   数据库中现有 {len(existing)} 条数据")
    if not existing.empty:
        print(f"   日期范围: {existing['date'].min()} ~ {existing['date'].max()}")

    # 获取数据
    print("\n3. 获取数据...")
    df = dm.get_daily_kline(symbol, start_date, end_date)
    print(f"   返回数据: {len(df)} 条")

    if not df.empty:
        print(f"   列名: {list(df.columns)}")
        print(f"   日期范围: {df['date'].min()} ~ {df['date'].max()}")
        print(f"   数据源: {df.get('data_source', 'unknown')}")

        # 检查 symbol 列
        if 'symbol' in df.columns:
            print(f"   symbol 示例: {df['symbol'].iloc[0]}")
        else:
            print("   [WARN] 没有 symbol 列!")

        # 检查是否保存成功
        print("\n4. 再次检查数据库...")
        existing_after = dm._get_kline_from_db(symbol, start_date, end_date)
        print(f"   数据库中现有 {len(existing_after)} 条数据")
        if len(existing_after) > len(existing):
            print(f"   [OK] 数据已保存! 新增 {len(existing_after) - len(existing)} 条")
        else:
            print(f"   [WARN] 数据可能没有增加")

    else:
        print("   [ERROR] 返回空数据!")

    print("\n" + "=" * 60)

if __name__ == '__main__':
    test_data_fetch_and_save()