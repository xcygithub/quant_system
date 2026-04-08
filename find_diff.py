"""直接对比两个脚本的关键差异"""
import sys
sys.path.insert(0, '.')

import pandas as pd
from data.data_manager import DataManager
from data.factor_data import FactorData
from strategy.moving_average import MovingAverageCrossStrategy
from portfolio.multi_stock_backtest import MultiStockBacktest

dm = DataManager()
symbols = ['000001.SH', '601919.SH']

# 使用与 diagnose_web_backtest.py 完全相同的日期范围
start_date = '2023-01-01'
end_date = '2024-12-31'

# 加载数据 - 与 diagnose_web_backtest.py 完全相同
stock_data = {}
signals = {}

for sym in symbols:
    df = dm.get_daily_kline(sym, start_date, end_date)
    if df.empty:
        continue
    stock_data[sym] = df

    factor_data = FactorData(df)
    df_with_factors = factor_data.calculate_all_factors()
    strat = MovingAverageCrossStrategy({'fast_period': 20, 'slow_period': 60})
    signal_series = strat.get_signal_series(df_with_factors)
    signal_series.index = pd.to_datetime(df['date'])
    signals[sym] = signal_series

print(f"Loaded {len(stock_data)} stocks")

# 测试1: 使用 diagnose_web_backtest.py 的参数
print("\n=== Test 1: diagnose_web_backtest.py parameters ===")
engine1 = MultiStockBacktest(
    initial_capital=1000000.0,
    commission_rate=0.0003,
    max_positions=5,
    rebalance_days=5,
    position_method='equal_weight',  # diagnose_web_backtest.py 使用的参数
    max_single_position=0.2,
    max_total_position=0.8
)
engine1.set_data(stock_data, signals)
results1 = engine1.run(start_date, end_date)
trade_counts1 = {}
for td in engine1.trade_details:
    trade_counts1[td.symbol] = trade_counts1.get(td.symbol, 0) + 1
print(f"Trade counts: {trade_counts1}")
print(f"Total: {len(engine1.trade_details)}")

# 测试2: 使用 debug_selection_at_rebalance.py 的参数（默认值）
print("\n=== Test 2: debug_selection_at_rebalance.py parameters ===")
engine2 = MultiStockBacktest(
    initial_capital=1000000.0,
    max_positions=5,
    rebalance_days=5,
    commission_rate=0.0003
)
engine2.set_data(stock_data, signals)
results2 = engine2.run(start_date, end_date)
trade_counts2 = {}
for td in engine2.trade_details:
    trade_counts2[td.symbol] = trade_counts2.get(td.symbol, 0) + 1
print(f"Trade counts: {trade_counts2}")
print(f"Total: {len(engine2.trade_details)}")

# 测试3: position_method='equal' (默认值)
print("\n=== Test 3: position_method='equal' ===")
engine3 = MultiStockBacktest(
    initial_capital=1000000.0,
    max_positions=5,
    rebalance_days=5,
    commission_rate=0.0003,
    position_method='equal'
)
engine3.set_data(stock_data, signals)
results3 = engine3.run(start_date, end_date)
trade_counts3 = {}
for td in engine3.trade_details:
    trade_counts3[td.symbol] = trade_counts3.get(td.symbol, 0) + 1
print(f"Trade counts: {trade_counts3}")
print(f"Total: {len(engine3.trade_details)}")