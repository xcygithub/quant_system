"""测试 max_single 参数的影响"""
import sys
sys.path.insert(0, '.')

import pandas as pd
from data.data_manager import DataManager
from data.factor_data import FactorData
from strategy.moving_average import MovingAverageCrossStrategy
from portfolio.multi_stock_backtest import MultiStockBacktest

dm = DataManager()
symbols = ['000001.SH', '601919.SH']
start_date = '2023-01-01'
end_date = '2024-12-31'

# 加载数据
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

# 测试不同 max_single 值
for max_single in [0.2, 0.3, 0.4, 0.5]:
    engine = MultiStockBacktest(
        initial_capital=1000000.0,
        commission_rate=0.0003,
        max_positions=5,
        rebalance_days=5,
        position_method='equal',
        max_single_position=max_single,
        max_total_position=0.8
    )
    engine.set_data(stock_data, signals)
    results = engine.run(start_date, end_date)

    trade_counts = {}
    for td in engine.trade_details:
        trade_counts[td.symbol] = trade_counts.get(td.symbol, 0) + 1

    print(f"max_single={max_single}: {trade_counts}, total={len(engine.trade_details)}")