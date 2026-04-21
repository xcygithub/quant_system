"""
验证 _check_data_complete 使用 datetime.now() 的问题
"""
import sys
sys.path.insert(0, 'c:/Users/FY/WorkBuddy/Claw/quant_system')

from data.data_manager import DataManager
from datetime import datetime, timedelta
import pandas as pd

def test_timing_issue():
    print("=" * 60)
    print("验证时间判断问题")
    print("=" * 60)

    dm = DataManager()

    # 检查数据库中的数据
    symbol = '000001.SZ'
    existing = dm._get_kline_from_db(symbol, '2023-01-01', '2024-03-19')

    if not existing.empty:
        print(f"\n数据库中 {symbol} 数据:")
        print(f"  日期范围: {existing['date'].min()} ~ {existing['date'].max()}")
        print(f"  共 {len(existing)} 条")

    # 问题：_check_data_complete 用 datetime.now() 判断
    # 今天是 2026-04-21，周二，所以 ref_date = 2026-04-20（昨天）
    today = datetime.now()
    print(f"\n当前日期: {today.strftime('%Y-%m-%d')} (weekday={today.weekday()})")
    print(f"  days_back = 1 (因为是周二)")
    print(f"  ref_date = {today.strftime('%Y-%m-%d')} - 1天 = 2026-04-20")

    print(f"\n回测区间 end_date = 2024-03-19")
    print(f"但 ref_date = 2026-04-20")
    print(f"数据库最新 = {existing['date'].max() if not existing.empty else 'N/A'}")
    print(f"\n比较: latest_date ({existing['date'].max() if not existing.empty else 'N/A'}) < ref_date (2026-04-20)?")
    if not existing.empty:
        latest = pd.to_datetime(existing['date'].max())
        ref = today - timedelta(days=1)
        print(f"  {latest.date()} < {ref.date()} = {latest.date() < ref.date()}")
        print(f"  结果: 数据被认为不完整，会重新获取!")

    print("\n" + "=" * 60)
    print("结论: _check_data_complete 的逻辑有问题！")
    print("  - 回测历史区间时，应该用 end_date 判断数据完整性")
    print("  - 不应该用当前日期 (datetime.now()) 来判断")
    print("=" * 60)

if __name__ == '__main__':
    test_timing_issue()