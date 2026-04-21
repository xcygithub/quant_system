"""
测试 _check_data_complete 的逻辑问题
"""
import sys
sys.path.insert(0, 'c:/Users/FY/WorkBuddy/Claw/quant_system')

from data.data_manager import DataManager
from datetime import datetime, timedelta
import pandas as pd

def test_check_data_complete():
    """测试 _check_data_complete 的逻辑"""
    print("=" * 60)
    print("测试 _check_data_complete 逻辑")
    print("=" * 60)

    dm = DataManager()

    # 模拟数据库中有数据的情况
    # 假设今天是 2024-03-20 周三，数据库最新是 2024-03-19 周二
    today = datetime(2024, 3, 20)  # 假设今天是周三
    weekday = today.weekday()
    print(f"假设今天是: {today.strftime('%Y-%m-%d')} (weekday={weekday})")

    if weekday == 0:  # 周一
        days_back = 3
    elif weekday == 6:  # 周日
        days_back = 2
    else:  # 周二~周六
        days_back = 1

    ref_date = (today - timedelta(days=days_back)).date()
    print(f"参考日期 (最近交易日): {ref_date}")
    print(f"需要数据库最新日期 >= {ref_date}")

    # 模拟一个场景：数据库中的最新数据是周一 (2024-03-18)
    # 但今天是周三 (2024-03-20)，周一和周二都是交易日
    print("\n场景1: 数据库最新是周一 (2024-03-18)，今天是周三 (2024-03-20)")
    print("  周一是交易日，周二也是交易日")
    print(f"  ref_date = {ref_date}")
    print(f"  latest_date = 2024-03-18")
    print(f"  2024-03-18 < {ref_date}? {datetime(2024, 3, 18).date() < ref_date}")
    print("  结论: 会判断为数据不完整，需要重新获取!")

    # 实际测试：检查数据库中的数据日期
    symbol = '000001.SZ'
    existing = dm._get_kline_from_db(symbol, '2024-01-01', '2024-03-20')
    if not existing.empty:
        latest = existing['date'].max()
        print(f"\n实际数据库中 {symbol} 最新日期: {latest}")

        # 调用 _check_data_complete
        result = dm._check_data_complete(existing, '2024-01-01', '2024-03-20')
        print(f"_check_data_complete 结果: {result}")

    print("\n" + "=" * 60)

if __name__ == '__main__':
    test_check_data_complete()