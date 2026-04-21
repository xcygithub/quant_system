"""
详细分析 _check_data_complete 的两个检查
"""
import sys
sys.path.insert(0, 'c:/Users/FY/WorkBuddy/Claw/quant_system')

from datetime import datetime, timedelta
import pandas as pd

def analyze_check():
    print("=" * 60)
    print("分析 _check_data_complete 的两个检查")
    print("=" * 60)

    start_date = '2023-01-01'
    end_date = '2024-03-19'

    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")
    total_days = (end - start).days

    print(f"\n区间: {start_date} ~ {end_date}")
    print(f"日历天数: {total_days}")

    # 检查1: 数据条数
    estimated_trading_days = int(total_days * 0.4)
    required = estimated_trading_days * 0.85
    print(f"\n检查1 - 数据条数:")
    print(f"  估算交易日数 = {total_days} * 0.4 = {estimated_trading_days}")
    print(f"  要求条数 >= {estimated_trading_days} * 0.85 = {required:.0f}")
    print(f"  实际数据库条数 = 50")
    print(f"  50 >= {required:.0f}? {50 >= required}")

    # 问题：用户查询的是 2023-01-01 到 2024-03-19，但数据库只有 2024-01-02 到 2024-03-19 的数据
    # 这意味着数据库中根本没有 2023 年的数据！

    print(f"\n实际数据库中数据范围: 2024-01-02 ~ 2024-03-19 (50条)")
    print(f"用户查询范围: {start_date} ~ {end_date}")
    print(f"  -> 数据库缺少 2023-01-01 ~ 2023-12-31 的数据!")

    print("\n" + "=" * 60)
    print("结论: 数据条数检查是合理的!")
    print("  - 数据库只有50条，覆盖 2024-01-02 ~ 2024-03-19")
    print("  - 查询的是 2023-01-01 ~ 2024-03-19，缺少年数据")
    print("  - 所以检查1失败是正确的")
    print("=" * 60)

    print("\n\n问题分析:")
    print("  回测时，用户设置 start_date=2023-01-01, end_date=2024-03-19")
    print("  数据库中只有 2024-01-02 之后的数据")
    print("  所以需要从 baostock 获取 2023-01-01 ~ 2023-12-31 的数据")
    print("  这是预期行为，不是 bug")

    print("\n\n但是，如果数据库已经有完整数据呢？")
    print("  假设数据库有 2023-01-01 ~ 2024-03-19 的完整数据 (约200条)")
    print(f"  那么检查1: 200 >= {required:.0f}? True")
    print("  检查2: latest_date (2024-03-19) >= ref_date (2024-03-19)? True")
    print("  结论: 数据完整，不需要重新获取")

if __name__ == '__main__':
    analyze_check()