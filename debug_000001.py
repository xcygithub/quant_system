"""Debug active_trades for 000001.SH"""
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

# Monkey patch to track active_trades changes
original_sell = MultiStockBacktest._sell
original_buy = MultiStockBacktest._buy

sell_count = 0
buy_count = 0

def tracked_sell(self, symbol, date, price, quantity, reason=""):
    global sell_count
    sell_count += 1
    print(f"[SELL #{sell_count}] {symbol}: qty={quantity}, price={price}, reason={reason}")
    print(f"  active_trades before: {list(self.active_trades.keys())}")
    result = original_sell(self, symbol, date, price, quantity, reason)
    print(f"  active_trades after: {list(self.active_trades.keys())}")
    print(f"  trade_details count: {len(self.trade_details)}")
    return result

def tracked_buy(self, symbol, date, price, quantity, reason=""):
    global buy_count
    buy_count += 1
    print(f"[BUY #{buy_count}] {symbol}: qty={quantity}, price={price}, reason={reason}")
    print(f"  active_trades before: {list(self.active_trades.keys())}")
    result = original_buy(self, symbol, date, price, quantity, reason)
    if symbol in self.active_trades:
        print(f"  active_trades[{symbol}] exists after buy")
    else:
        print(f"  WARNING: active_trades[{symbol}] NOT exists after buy!")
    return result

MultiStockBacktest._sell = tracked_sell
MultiStockBacktest._buy = tracked_buy

engine = MultiStockBacktest(
    initial_capital=1000000.0,
    max_positions=5,
    rebalance_days=5,
    commission_rate=0.0003
)

engine.set_data(stock_data, signals)

# Only run for first 20 days to limit output
all_dates = engine._get_common_dates(start_date, end_date)
test_dates = all_dates[:20]

print(f"Testing first {len(test_dates)} days")
print()

# Manually run first few days
for i, date in enumerate(test_dates):
    engine.trading_days = i
    current_prices = engine._get_prices_on_date(date)
    engine._update_positions(current_prices)

    should_rebalance = (i - engine.last_rebalance_day) >= engine.rebalance_days
    needs_initial_position = (len(engine.positions) == 0 and engine.cash > 0)

    print(f"Day {i} ({str(date)[:10]}):")
    print(f"  positions: {list(engine.positions.keys())}")
    print(f"  cash: {engine.cash:.2f}")
    print(f"  should_rebalance: {should_rebalance}, needs_initial_position: {needs_initial_position}")

    # Check sell signals
    if '000001.SH' in engine.positions:
        sig = signals['000001.SH']
        try:
            sig_val = sig.loc[date] if date in sig.index else sig.iloc[0]
            print(f"  000001.SH signal: {sig_val}")
        except:
            print(f"  000001.SH signal: ERROR")

    if (should_rebalance or needs_initial_position) and engine.cash > 0:
        print(f"  -> REBALANCE triggered")
        engine._rebalance(date, current_prices)

    print()

print()
print(f"Final: trade_details count = {len(engine.trade_details)}")
print(f"Final: active_trades count = {len(engine.active_trades)}")

# Check 000001.SH specifically
if '000001.SH' in engine.active_trades:
    td = engine.active_trades['000001.SH']
    print(f"000001.SH in active_trades: entry_date={td.entry_date}, qty={td.entry_quantity}")
elif any(td.symbol == '000001.SH' for td in engine.trade_details):
    print("000001.SH is in trade_details (closed)")
    for td in engine.trade_details:
        if td.symbol == '000001.SH':
            print(f"  entry={td.entry_date}, exit={td.exit_date}, status={td.status}")
else:
    print("000001.SH NOT FOUND in active_trades or trade_details!")