"""检查 max_single=0.2 时 000001.SH 的买入金额"""
import sys
sys.path.insert(0, '.')

import pandas as pd
from data.data_manager import DataManager

dm = DataManager()
symbol = '000001.SH'

# 获取 Day 0 的数据
df = dm.get_daily_kline(symbol, '2023-01-01', '2023-01-10')
print(f"000001.SH Day 0 price: {df.iloc[0]['close']}")

# 计算 max_single=0.2 时的买入金额
total_capital = 1000000.0
max_single = 0.2
max_total = 0.8

# 假设只有 000001.SH 一只股票（极端情况）
weight = 0.5  # _equal_weight(1)
weight = weight * max_total  # 0.4
weight = min(weight, max_single)  # 0.2
amount = total_capital * weight  # 200000

print(f"\nWith max_single=0.2, max_total=0.8:")
print(f"  Weight before max_single limit: 0.5 * 0.8 = 0.4")
print(f"  Weight after max_single limit: min(0.4, 0.2) = 0.2")
print(f"  Amount per stock: {total_capital} * 0.2 = {amount}")
print(f"  000001.SH Day 0 price: {df.iloc[0]['close']}")
print(f"  Shares to buy (100 per lot): {int(amount / df.iloc[0]['close'] / 100) * 100}")

# 现在假设有 2 只股票
print(f"\nWith 2 stocks (equal weight):")
weight_per_stock = 0.5 * max_total  # 0.4
weight_per_stock = min(weight_per_stock, max_single)  # 0.2
amount_per_stock = total_capital * weight_per_stock  # 200000
print(f"  Weight per stock: 0.5 * 0.8 = 0.4 -> min(0.4, 0.2) = 0.2")
print(f"  Amount per stock: {total_capital} * 0.2 = {amount_per_stock}")
print(f"  000001.SH price: {df.iloc[0]['close']}")
print(f"  Shares: {int(amount_per_stock / df.iloc[0]['close'] / 100) * 100}")

# 检查 601919.SH
df2 = dm.get_daily_kline('601919.SH', '2023-01-01', '2023-01-10')
print(f"\n  601919.SH Day 0 price: {df2.iloc[0]['close']}")
print(f"  Shares: {int(amount_per_stock / df2.iloc[0]['close'] / 100) * 100}")