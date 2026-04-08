"""对比两个脚本的回测差异"""
import sys
sys.path.insert(0, '.')

import pandas as pd
from data.data_manager import DataManager
from data.factor_data import FactorData
from strategy.moving_average import MovingAverageCrossStrategy
from portfolio.multi_stock_backtest import MultiStockBacktest
from portfolio.watchlist import WatchlistManager

# 获取自选股
wl = WatchlistManager()
all_stocks = wl.get_all_stocks()
selected_symbols = [s.symbol for s in all_stocks[:5]]

dm = DataManager()
start_date = '2023-01-01'
end_date = '2024-12-31'

# 加载数据 - 与 diagnose_web_backtest.py 相同
stock_data = {}
signals = {}

for sym in selected_symbols:
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
print(f"Signals keys: {list(signals.keys())}")

# 运行回测 - 与 diagnose_web_backtest.py 相同
engine = MultiStockBacktest(
    initial_capital=1000000.0,
    commission_rate=0.0003,
    max_positions=5,
    rebalance_days=5,
    position_method='equal_weight',
    max_single_position=0.2,
    max_total_position=0.8
)

engine.set_data(stock_data, signals)
print(f"set_data done. stock_data: {len(engine.stock_data)}")

results = engine.run(start_date, end_date)
print(f"Backtest done.")

# 检查结果
print(f"\n=== Results ===")
print(f"trade_details count: {len(engine.trade_details)}")
print(f"active_trades count: {len(engine.active_trades)}")

# 每只股票的交易次数
trade_counts = {}
for td in engine.trade_details:
    trade_counts[td.symbol] = trade_counts.get(td.symbol, 0) + 1
print(f"\nTrades per symbol:")
for sym, count in sorted(trade_counts.items()):
    print(f"  {sym}: {count}")

# 检查 _get_common_dates
print(f"\n=== Checking dates ===")
all_dates = engine._get_common_dates(start_date, end_date)
print(f"Common dates count: {len(all_dates)}")
print(f"First 5 dates: {all_dates[:5]}")
print(f"Last 5 dates: {all_dates[-5:]}")

# 检查 Day 0 的信号
date_0 = all_dates[0]
print(f"\n=== Day 0 signals ===")
for sym in stock_data.keys():
    if sym in signals:
        sig = signals[sym]
        if date_0 in sig.index:
            print(f"  {sym}: signal={sig.loc[date_0]}")
        else:
            print(f"  {sym}: date {date_0} not in signal index")

# 检查 _select_candidates 在 Day 0
print(f"\n=== Day 0 _select_candidates ===")
from portfolio.selector import StockSelector
selector = StockSelector(top_n=5)
scores = selector.score_stocks(stock_data, signals)
for s in scores:
    print(f"  {s.symbol}: composite_score={s.composite_score:.2f}, signal_type={s.signal_type}")
candidates = selector.select_buy_candidates(scores, top_n=5, min_score=20)
print(f"Candidates (min_score=20): {[c.symbol for c in candidates]}")