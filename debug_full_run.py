"""
检查 _get_common_dates 是否正确
"""
import pandas as pd
import numpy as np
from datetime import datetime
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from portfolio.multi_stock_backtest import MultiStockBacktest

# 重现完整场景
initial_capital = 1000000
max_single_position = 0.2

engine = MultiStockBacktest(
    initial_capital=initial_capital,
    max_positions=5,
    rebalance_days=5,
    max_single_position=max_single_position,
    max_total_position=0.8,
    commission_rate=0.0003,
)

# 创建测试数据 - 使用完全相同的种子
dates = pd.date_range(end=datetime.now(), periods=120, freq='B')
stock_data = {}
signals = {}

np.random.seed(42)
close1 = 10 + np.random.randn(120).cumsum() * 0.3
close1 = np.maximum(close1, 8)  # 不跌破8元
stock_data["000001.SZ"] = pd.DataFrame({
    'date': dates,
    'open': close1 - np.random.rand(120) * 0.2,
    'high': close1 + np.random.rand(120) * 0.3,
    'low': close1 - np.random.rand(120) * 0.3,
    'close': close1,
    'volume': np.random.randint(1000000, 10000000, 120)
})
signals["000001.SZ"] = pd.Series(1, index=pd.to_datetime(dates))

np.random.seed(43)
close2 = 8 + np.random.randn(120).cumsum() * 0.25
close2 = np.maximum(close2, 6)
stock_data["600000.SH"] = pd.DataFrame({
    'date': dates,
    'open': close2 - np.random.rand(120) * 0.2,
    'high': close2 + np.random.rand(120) * 0.3,
    'low': close2 - np.random.rand(120) * 0.3,
    'close': close2,
    'volume': np.random.randint(1000000, 10000000, 120)
})
signals["600000.SH"] = pd.Series(1, index=pd.to_datetime(dates))

np.random.seed(44)
close3 = 9 + np.random.randn(120).cumsum() * 0.28
close3 = np.maximum(close3, 7)
stock_data["000858.SZ"] = pd.DataFrame({
    'date': dates,
    'open': close3 - np.random.rand(120) * 0.2,
    'high': close3 + np.random.rand(120) * 0.3,
    'low': close3 - np.random.rand(120) * 0.3,
    'close': close3,
    'volume': np.random.randint(1000000, 10000000, 120)
})
signals["000858.SZ"] = pd.Series(1, index=pd.to_datetime(dates))

engine.set_data(stock_data, signals)

# 检查日期
all_dates = engine._get_common_dates(None, None)
print(f"共同日期数量: {len(all_dates)}")
print(f"第一天: {all_dates[0]}")
print(f"第二天: {all_dates[1]}")

# 获取第一天价格
first_date = all_dates[0]
first_prices = engine._get_prices_on_date(first_date)
print(f"\n第一天价格: {first_prices}")

# 计算每只股票的买入股数
for symbol in first_prices:
    price = first_prices[symbol]
    target_amount = 1000000 * 0.2  # 20% of initial capital
    shares = int(target_amount / price / 100) * 100
    actual_amount = shares * price
    ratio = actual_amount / initial_capital
    print(f"  {symbol}: price={price:.2f}, shares={shares}, amount={actual_amount:,.0f}, ratio={ratio:.2%}")

# 现在运行完整回测
print("\n" + "="*60)
print("运行完整回测")
print("="*60)

results = engine.run()

# 检查第一次调仓后的持仓
print("\n" + "="*60)
print("第一次调仓后（Day 0）的持仓")
print("="*60)
for symbol, pos in engine.snapshots[0].positions.items():
    ratio = pos.market_value / initial_capital
    print(f"  {symbol}: {pos.quantity} 股, 市值 {pos.market_value:,.0f}, 占比 {ratio:.2%}")