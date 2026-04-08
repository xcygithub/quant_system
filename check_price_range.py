"""检查价格范围"""
import sys
sys.path.insert(0, '.')
from data.data_manager import DataManager

dm = DataManager()
df = dm.get_daily_kline('000001.SH', '2023-01-01', '2024-12-31')
print(f'000001.SH price range:')
print(f'  Min: {df["close"].min():.2f}')
print(f'  Max: {df["close"].max():.2f}')
print(f'  Mean: {df["close"].mean():.2f}')

# 检查有多少天价格 <= 2000
days_can_buy = (df['close'] <= 2000).sum()
print(f'  Days with price <= 2000: {days_can_buy}')

print()
print(f'With max_single=0.2, max_total=0.8:')
print(f'  Amount per stock: 1000000 * 0.2 = 200000')
print(f'  To buy 100 shares: need price <= {200000 / 100:.2f}')
print(f'  Actual min price: {df["close"].min():.2f}')
print(f'  Can buy 100 shares: {df["close"].min() <= 2000}')