"""
验证修复后的 _check_data_complete 逻辑
"""
import sys
sys.path.insert(0, 'c:/Users/FY/WorkBuddy/Claw/quant_system')

# 重新加载模块确保使用最新代码
import importlib
from data import data_manager
importlib.reload(data_manager)

from data.data_manager import DataManager
from datetime import datetime, timedelta
import pandas as pd

def test_fixed_check_data_complete():
    print("=" * 60)
    print("验证修复后的 _check_data_complete 逻辑")
    print("=" * 60)

    dm = DataManager()

    symbol = '000001.SZ'
    start_date = '2023-01-01'
    end_date = '2024-03-19'  # 历史日期

    # 检查数据库中的数据
    existing = dm._get_kline_from_db(symbol, start_date, end_date)
    if not existing.empty:
        print(f"\n数据库中 {symbol} 数据:")
        print(f"  日期范围: {existing['date'].min()} ~ {existing['date'].max()}")
        print(f"  共 {len(existing)} 条")

    # 调用修复后的 _check_data_complete
    result = dm._check_data_complete(existing, start_date, end_date)

    print(f"\n调用 _check_data_complete({start_date}, {end_date}):")
    print(f"  end_date ({end_date}) < today ({datetime.now().strftime('%Y-%m-%d')})? {datetime.strptime(end_date, '%Y-%m-%d').date() < datetime.now().date()}")
    print(f"  结论: 使用 end_date ({end_date}) 作为参考日期")
    print(f"\n  _check_data_complete 结果: {result}")
    if result:
        print("  [OK] 数据被认为完整，不会重新获取!")
    else:
        print("  [FAIL] 数据被认为不完整，仍会重新获取!")

    print("\n" + "=" * 60)

    # 测试2: 当 end_date 是今天时
    print("\n测试2: end_date 是今天")
    today_str = datetime.now().strftime('%Y-%m-%d')
    result2 = dm._check_data_complete(existing, '2024-01-01', today_str)
    print(f"  _check_data_complete('2024-01-01', '{today_str}'): {result2}")
    if not result2:
        print("  [OK] 因为是今天，使用当前日期逻辑判断")

    print("\n" + "=" * 60)

if __name__ == '__main__':
    test_fixed_check_data_complete()