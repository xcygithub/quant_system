"""
调试为什么 000001.SH 没有被交易
"""
import sys
sys.path.insert(0, '.')

import pandas as pd
from data.data_manager import DataManager
from data.factor_data import FactorData
from strategy.moving_average import MovingAverageCrossStrategy
from portfolio.selector import StockSelector

dm = DataManager()
symbol = '000001.SH'

# 获取数据
df = dm.get_daily_kline(symbol, '2023-01-01', '2024-12-31')
print(f"{symbol}: {len(df)} bars")

# 计算信号
factor_data = FactorData(df)
df_with_factors = factor_data.calculate_all_factors()
strat = MovingAverageCrossStrategy({'fast_period': 20, 'slow_period': 60})
signal_series = strat.get_signal_series(df_with_factors)
signal_series.index = pd.to_datetime(df['date'])

print(f"Signals: buy={sum(signal_series==1)}, sell={sum(signal_series==-1)}, hold={sum(signal_series==0)}")

# 关键：检查 Day 0 时 000001.SH 是否在候选列表中
stock_data = {symbol: df}
signals = {symbol: signal_series}

selector = StockSelector(top_n=5)
scores = selector.score_stocks(stock_data, signals)

print(f"\n=== Day 0 Selection ===")
for s in scores:
    print(f"{s.symbol}: composite_score={s.composite_score:.2f}, signal_type={s.signal_type}")

candidates = selector.select_buy_candidates(scores, top_n=5, min_score=20)
print(f"\nCandidates (min_score=20): {[c.symbol for c in candidates]}")

candidates_all = selector.select_buy_candidates(scores, top_n=5, min_score=0)
print(f"Candidates (min_score=0): {[c.symbol for c in candidates_all]}")

# 检查 Day 0 时 MA 条件
first_row = df_with_factors.iloc[0]
print(f"\n=== Day 0 Indicators ===")
print(f"ma5={first_row.get('ma5', 'N/A')}, ma20={first_row.get('ma20', 'N/A')}, ma60={first_row.get('ma60', 'N/A')}")

# 检查前25天数据
print(f"\n=== First 25 Days ===")
for i in range(min(25, len(df_with_factors))):
    row = df_with_factors.iloc[i]
    date = df_with_factors.iloc[i]['date']
    sig = signal_series.iloc[i] if i < len(signal_series) else 'N/A'
    ma5 = row.get('ma5', 'N/A')
    ma20 = row.get('ma20', 'N/A')
    ma5_str = f"{ma5:.2f}" if isinstance(ma5, (int, float)) else str(ma5)
    ma20_str = f"{ma20:.2f}" if isinstance(ma20, (int, float)) else str(ma20)
    print(f"Day {i} ({str(date)[:10]}): signal={sig}, ma5={ma5_str}, ma20={ma20_str}")