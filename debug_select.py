"""Debug _select_candidates for 000001.SH"""
import sys
sys.path.insert(0, 'c:/Users/FY/WorkBuddy/Claw/quant_system')

import pandas as pd
from data.data_manager import DataManager
from data.factor_data import FactorData
from strategy.moving_average import MovingAverageCrossStrategy
from portfolio.multi_stock_backtest import MultiStockBacktest
from portfolio.selector import StockSelector

dm = DataManager()
symbols = ['000001.SH', '601919.SH']
start_date = '2023-01-01'
end_date = '2023-01-10'  # Short for debug

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

    print(f"{sym}: {len(df)} bars, signal buy={sum(signal_series==1)}, sell={sum(signal_series==-1)}")

# Create engine and manually check _select_candidates
engine = MultiStockBacktest(
    initial_capital=1000000.0,
    max_positions=5,
    rebalance_days=5,
    commission_rate=0.0003
)

engine.set_data(stock_data, signals)

# Manually run first day
engine.cash = 1000000.0
engine.positions = {}

print()
print("=== _select_candidates Debug ===")

# Check data_for_scoring
data_for_scoring = {}
signals_for_scoring = {}

for symbol, df in engine.stock_data.items():
    print(f"Checking {symbol}: len(df)={len(df)}")
    if len(df) >= 20:
        data_for_scoring[symbol] = df
        if symbol in engine.signals:
            signals_for_scoring[symbol] = engine.signals[symbol]
        print(f"  Added to data_for_scoring")
    else:
        print(f"  SKIPPED: len(df) < 20")

print()
print(f"data_for_scoring keys: {list(data_for_scoring.keys())}")
print(f"signals_for_scoring keys: {list(signals_for_scoring.keys())}")

# Score stocks
scores = engine.selector.score_stocks(data_for_scoring, signals_for_scoring)
print()
print(f"Scores ({len(scores)} stocks):")
for s in scores:
    print(f"  {s.symbol}: composite_score={s.composite_score:.2f}, signal_type={s.signal_type}")

# Select candidates
candidates = engine.selector.select_buy_candidates(scores, top_n=5, min_score=20)
print()
print(f"Candidates (top_n=5, min_score=20, {len(candidates)} returned):")
for c in candidates:
    print(f"  {c.symbol}: score={c.composite_score:.2f}")

# Check with min_score=0
candidates_zero = engine.selector.select_buy_candidates(scores, top_n=5, min_score=0)
print()
print(f"Candidates (top_n=5, min_score=0, {len(candidates_zero)} returned):")
for c in candidates_zero:
    print(f"  {c.symbol}: score={c.composite_score:.2f}")