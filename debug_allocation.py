"""调试分配问题"""
import sys
sys.path.insert(0, '.')

import pandas as pd
from data.data_manager import DataManager
from portfolio.position_sizer import PositionSizer, PositionMethod

dm = DataManager()
symbol = '000001.SH'

# 获取 Day 0 的价格
df = dm.get_daily_kline(symbol, '2023-01-01', '2023-01-10')
price_000001 = df.iloc[0]['close']
df2 = dm.get_daily_kline('601919.SH', '2023-01-01', '2023-01-10')
price_601919 = df2.iloc[0]['close']

print(f"000001.SH Day 0 price: {price_000001}")
print(f"601919.SH Day 0 price: {price_601919}")

# 模拟分配
candidates = [
    ('000001.SH', 64.45, 0.01),  # (symbol, score, volatility)
    ('601919.SH', 59.44, 0.02),
]
prices = {
    '000001.SH': price_000001,
    '601919.SH': price_601919,
}
total_capital = 1000000.0

print(f"\n=== max_single=0.2 ===")
sizer = PositionSizer(
    method=PositionMethod.EQUAL_WEIGHT,
    max_total_position=0.8,
    max_single_position=0.2
)
allocations = sizer.allocate(candidates, total_capital, prices)
for a in allocations:
    print(f"  {a.symbol}: weight={a.weight:.4f}, amount={a.amount:.2f}, shares={a.shares}")

print(f"\n=== max_single=0.3 ===")
sizer = PositionSizer(
    method=PositionMethod.EQUAL_WEIGHT,
    max_total_position=0.8,
    max_single_position=0.3
)
allocations = sizer.allocate(candidates, total_capital, prices)
for a in allocations:
    print(f"  {a.symbol}: weight={a.weight:.4f}, amount={a.amount:.2f}, shares={a.shares}")

# 计算当 shares > 0 时需要的最小金额
min_amount_000001 = price_000001 * 100
min_amount_601919 = price_601919 * 100
print(f"\n=== 最小买入金额 ===")
print(f"  000001.SH 需要 {min_amount_000001:.2f} 元 (100股)")
print(f"  601919.SH 需要 {min_amount_601919:.2f} 元 (100股)")

# 当 max_single=0.2, max_total=0.8, 2只股票时
weight_per_stock = 0.5  # equal weight
weight_after_max = min(weight_per_stock * 0.8, 0.2)
amount = total_capital * weight_after_max
print(f"\n=== 当 max_single=0.2 时 ===")
print(f"  每只股票的权重: 0.5 * 0.8 = 0.4 -> min(0.4, 0.2) = {weight_after_max}")
print(f"  每只股票的金额: 1000000 * {weight_after_max} = {amount:.2f}")
print(f"  000001.SH 可买股数: {int(amount / price_000001 / 100) * 100} 股 (需要 {min_amount_000001:.2f})")
print(f"  601919.SH 可买股数: {int(amount / price_601919 / 100) * 100} 股 (需要 {min_amount_601919:.2f})")