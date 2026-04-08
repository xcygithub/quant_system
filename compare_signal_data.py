"""对比两个脚本的数据差异"""
import sys
sys.path.insert(0, '.')

import pandas as pd
from data.data_manager import DataManager
from data.factor_data import FactorData
from strategy.moving_average import MovingAverageCrossStrategy
from portfolio.watchlist import WatchlistManager

wl = WatchlistManager()
all_stocks = wl.get_all_stocks()

print(f"自选股列表: {[(s.symbol, s.name) for s in all_stocks]}")

dm = DataManager()
symbol = '000001.SH'
start_date = '2023-01-01'
end_date = '2024-12-31'

df = dm.get_daily_kline(symbol, start_date, end_date)
print(f"\n000001.SH data shape: {df.shape}")
print(f"Date column type: {type(df['date'].iloc[0])}")
print(f"Date values sample: {df['date'].tolist()[:5]}")

# 方法1: diagnose_web_backtest.py 的方式
factor_data1 = FactorData(df)
df_with_factors1 = factor_data1.calculate_all_factors()
strat = MovingAverageCrossStrategy({'fast_period': 20, 'slow_period': 60})
signal_series1 = strat.get_signal_series(df_with_factors1)
if 'date' in df.columns:
    signal_series1.index = pd.to_datetime(df['date'])

# 方法2: debug_selection_at_rebalance.py 的方式 (一样的方式)
factor_data2 = FactorData(df)
df_with_factors2 = factor_data2.calculate_all_factors()
strat2 = MovingAverageCrossStrategy({'fast_period': 20, 'slow_period': 60})
signal_series2 = strat2.get_signal_series(df_with_factors2)
signal_series2.index = pd.to_datetime(df['date'])

print(f"\nSignal series 1 shape: {signal_series1.shape}")
print(f"Signal series 2 shape: {signal_series2.shape}")
print(f"Are they equal: {signal_series1.equals(signal_series2)}")

# 检查 Day 0 的信号
date_idx = pd.Timestamp('2023-01-03')
print(f"\nDay 0 signal 1: {signal_series1.loc[date_idx] if date_idx in signal_series1.index else 'NOT IN INDEX'}")
print(f"Day 0 signal 2: {signal_series2.loc[date_idx] if date_idx in signal_series2.index else 'NOT IN INDEX'}")

# 检查索引
print(f"\nIndex type 1: {type(signal_series1.index)}")
print(f"Index type 2: {type(signal_series2.index)}")
print(f"Index equal: {signal_series1.index.equals(signal_series2.index)}")