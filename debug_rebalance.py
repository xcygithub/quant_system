"""调试 position_method 对选股的影响"""
import sys
sys.path.insert(0, '.')

import pandas as pd
from data.data_manager import DataManager
from data.factor_data import FactorData
from strategy.moving_average import MovingAverageCrossStrategy
from portfolio.multi_stock_backtest import MultiStockBacktest
from portfolio.selector import StockSelector

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

# 创建一个引擎来检查 _rebalance 的行为
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

# 获取共同日期
all_dates = engine._get_common_dates(start_date, end_date)
print(f"Total trading days: {len(all_dates)}")

# 检查前10天的调仓情况
print("\n=== First 10 trading days ===")
for i in range(min(10, len(all_dates))):
    date = all_dates[i]

    # 模拟 _select_candidates
    scores = engine.selector.score_stocks(engine.stock_data, engine.signals, date)
    candidates = engine.selector.select_buy_candidates(scores, top_n=5, min_score=20)

    # 检查是否有持仓
    current_positions = list(engine.positions.keys())
    needs_rebalance = engine._needs_rebalance(date, i)

    # 获取价格
    prices = engine._get_prices_on_date(date)

    # 获取信号
    day_signals = {}
    for sym in engine.stock_data.keys():
        sig = engine.signals[sym]
        if date in sig.index:
            day_signals[sym] = sig.loc[date]
        else:
            day_signals[sym] = 0

    print(f"Day {i} ({str(date)[:10]}): positions={current_positions}, needs_rebalance={needs_rebalance}")
    print(f"  Candidates: {[c.symbol for c in candidates]}")
    print(f"  Signals: {day_signals}")
    print(f"  Prices: {prices}")

    # 手动模拟 _rebalance 的选股逻辑
    if needs_rebalance and candidates:
        # 检查 _allocate_positions
        allocations = engine.position_sizer.allocate(
            [(c.symbol, c.composite_score, prices.get(c.symbol, 0)) for c in candidates],
            engine.cash + sum(engine.positions.values()),
            prices
        )
        print(f"  Allocations: {[(a.symbol, a.shares, a.amount) for a in allocations]}")

    # 执行当天的 _rebalance
    if needs_rebalance:
        engine._rebalance(date, i)

print(f"\n=== Final Results ===")
print(f"Trade details: {len(engine.trade_details)}")
trade_counts = {}
for td in engine.trade_details:
    trade_counts[td.symbol] = trade_counts.get(td.symbol, 0) + 1
print(f"Trades per symbol: {trade_counts}")