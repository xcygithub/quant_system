"""调试多股票回测时的选股逻辑"""
import sys
sys.path.insert(0, '.')

import pandas as pd
from data.data_manager import DataManager
from data.factor_data import FactorData
from strategy.moving_average import MovingAverageCrossStrategy
from portfolio.multi_stock_backtest import MultiStockBacktest

dm = DataManager()
symbols = ['000001.SH', '601919.SH']

# 模拟回测第一天
start_date = '2023-01-03'  # Day 0
end_date = '2024-12-31'

# 加载数据
stock_data = {}
signals = {}

for sym in symbols:
    df = dm.get_daily_kline(sym, start_date, end_date)
    stock_data[sym] = df

    factor_data = FactorData(df)
    df_with_factors = factor_data.calculate_all_factors()
    strat = MovingAverageCrossStrategy({'fast_period': 20, 'slow_period': 60})
    signal_series = strat.get_signal_series(df_with_factors)
    signal_series.index = pd.to_datetime(df['date'])
    signals[sym] = signal_series

# 模拟 MultiStockBacktest 的 _select_candidates 方法
from portfolio.selector import StockSelector

selector = StockSelector(top_n=5)

# 对 Day 0 进行评分
scores = selector.score_stocks(stock_data, signals)

print("=== Day 0 Scores ===")
for s in scores:
    print(f"{s.symbol}: composite_score={s.composite_score:.2f}, signal_type={s.signal_type}")

# 选择买入候选
candidates = selector.select_buy_candidates(scores, top_n=5, min_score=20)
print(f"\nBuy candidates (min_score=20): {[c.symbol for c in candidates]}")

candidates_all = selector.select_buy_candidates(scores, top_n=5, min_score=0)
print(f"Buy candidates (min_score=0): {[c.symbol for c in candidates_all]}")

# 检查信号序列
print(f"\n=== Signals on Day 0 ===")
for sym in symbols:
    sig = signals[sym]
    date_idx = pd.Timestamp('2023-01-03')
    if date_idx in sig.index:
        print(f"{sym}: signal={sig.loc[date_idx]}")
    else:
        print(f"{sym}: date not in index")

# 运行完整回测并检查每只股票的买入次数
print(f"\n=== Running full backtest ===")
engine = MultiStockBacktest(
    initial_capital=1000000.0,
    max_positions=5,
    rebalance_days=5,
    commission_rate=0.0003
)
engine.set_data(stock_data, signals)
results = engine.run(start_date, end_date)

print(f"\n=== Trade counts per symbol ===")
trade_counts = {}
for td in engine.trade_details:
    trade_counts[td.symbol] = trade_counts.get(td.symbol, 0) + 1

for sym, count in trade_counts.items():
    print(f"{sym}: {count} trades")