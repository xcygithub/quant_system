"""Verify trade_details_df contains 000001.SH"""
import sys
sys.path.insert(0, 'c:/Users/FY/WorkBuddy/Claw/quant_system')

import pandas as pd
from data.data_manager import DataManager
from data.factor_data import FactorData
from strategy.moving_average import MovingAverageCrossStrategy
from portfolio.multi_stock_backtest import MultiStockBacktest

dm = DataManager()
symbols = ['000001.SH', '601919.SH']
start_date = '2023-01-01'
end_date = '2024-12-31'

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

    if 'date' in df.columns:
        signal_series.index = pd.to_datetime(df['date'])
    signals[sym] = signal_series

engine = MultiStockBacktest(
    initial_capital=1000000.0,
    max_positions=5,
    rebalance_days=5,
    commission_rate=0.0003
)

engine.set_data(stock_data, signals)
results = engine.run(start_date, end_date)

print()
print("=== get_trade_details_df() Test ===")
trade_details_df = engine.get_trade_details_df()

print(f"trade_details_df shape: {trade_details_df.shape}")
print(f"Columns: {list(trade_details_df.columns)}")

# Find 000001.SH records
print()
mask = trade_details_df.apply(lambda row: '000001' in str(row.values), axis=1)
df_000001 = trade_details_df[mask]
print(f"Records containing 000001: {len(df_000001)}")

# Check symbols in trade_details
print()
print("Symbols in trade_details:")
print(f"  engine.trade_details count: {len(engine.trade_details)}")
for td in engine.trade_details:
    if td.symbol == '000001.SH':
        entry = str(td.entry_date)[:10] if td.entry_date else 'None'
        exit = str(td.exit_date)[:10] if td.exit_date else 'None'
        print(f"  [{td.trade_id}] {td.symbol}: entry={entry}, exit={exit}, status={td.status}")