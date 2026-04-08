"""测试 Web 界面回测逻辑"""
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

print('=== Loading Data ===')
for sym in symbols:
    df = dm.get_daily_kline(sym, start_date, end_date)
    if df.empty:
        print(f'{sym}: no data')
        continue
    stock_data[sym] = df

    factor_data = FactorData(df)
    df_with_factors = factor_data.calculate_all_factors()
    strat = MovingAverageCrossStrategy({'fast_period': 20, 'slow_period': 60})
    signal_series = strat.get_signal_series(df_with_factors)

    if 'date' in df.columns:
        signal_series.index = pd.to_datetime(df['date'])
    signals[sym] = signal_series

    print(f'{sym}: {len(df)} bars')
    print(f'  Signals - buy={sum(signal_series==1)}, sell={sum(signal_series==-1)}, hold={sum(signal_series==0)}')

print()
print('=== Running Backtest ===')

engine = MultiStockBacktest(
    initial_capital=1000000.0,
    max_positions=5,
    rebalance_days=5,
    commission_rate=0.0003
)

engine.set_data(stock_data, signals)
results = engine.run(start_date, end_date)

print()
print('=== Results ===')
trades = results.get('trades', [])
print(f'Total trades: {len(trades)}')
print(f'Trade details: {len(engine.trade_details)}')
print(f'Active trades: {len(engine.active_trades)}')

print()
print('=== Trade Details ===')
for td in engine.trade_details:
    entry_str = str(td.entry_date)[:10] if td.entry_date else 'None'
    exit_str = str(td.exit_date)[:10] if td.exit_date else 'None'
    print(f'  [{td.trade_id}] {td.symbol}: entry={entry_str}@{td.entry_price:.2f}, exit={exit_str}@{td.exit_price:.2f}, status={td.status}')

print()
print('=== Active Trades ===')
for sym, td in engine.active_trades.items():
    entry_str = str(td.entry_date)[:10] if td.entry_date else 'None'
    print(f'  {sym}: entry={entry_str}@{td.entry_price:.2f}, status={td.status}')

print()
print('=== Buy Trades ===')
for t in trades:
    if t.side == 'BUY':
        date_str = str(t.date)[:10] if t.date else 'None'
        print(f'  {t.symbol}: {date_str} {t.quantity}@{t.price:.2f}')