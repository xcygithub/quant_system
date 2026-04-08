"""Debug _sell for 000001.SH - full backtest"""
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

# Track all _sell calls for 000001.SH
original_sell = MultiStockBacktest._sell
sell_log = []

def tracked_sell(self, symbol, date, price, quantity, reason=""):
    if symbol == '000001.SH':
        sell_log.append({
            'date': date,
            'price': price,
            'quantity': quantity,
            'reason': reason,
            'positions_keys': list(self.positions.keys()),
            'cash_before': self.cash
        })
        print(f"[SELL 000001.SH] date={str(date)[:10]}, price={price}, qty={quantity}, reason={reason}")
        print(f"  positions before: {list(self.positions.keys())}")
        if symbol in self.positions:
            print(f"  pos.quantity: {self.positions[symbol].quantity}")
        else:
            print(f"  WARNING: {symbol} NOT in positions!")
    return original_sell(self, symbol, date, price, quantity, reason)

MultiStockBacktest._sell = tracked_sell

engine = MultiStockBacktest(
    initial_capital=1000000.0,
    max_positions=5,
    rebalance_days=5,
    commission_rate=0.0003
)

engine.set_data(stock_data, signals)
results = engine.run(start_date, end_date)

print()
print(f"Total _sell calls for 000001.SH: {len(sell_log)}")
print(f"trade_details count: {len(engine.trade_details)}")
print(f"active_trades count: {len(engine.active_trades)}")

# Find 000001.SH in trade_details
found_in_details = [td for td in engine.trade_details if td.symbol == '000001.SH']
print(f"000001.SH in trade_details: {len(found_in_details)}")

# Find 000001.SH in active_trades
if '000001.SH' in engine.active_trades:
    print(f"000001.SH in active_trades: YES, qty={engine.active_trades['000001.SH'].entry_quantity}")
else:
    print(f"000001.SH in active_trades: NO")

# Summary of sell calls
print()
print("Sell call summary:")
for log in sell_log:
    print(f"  {str(log['date'])[:10]}: qty={log['quantity']}, price={log['price']}, reason={log['reason']}")