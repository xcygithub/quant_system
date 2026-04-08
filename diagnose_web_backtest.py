"""
诊断 Web 界面回测问题
"""
import sys
sys.path.insert(0, '.')

import pandas as pd
from data.data_manager import DataManager
from data.factor_data import FactorData
from strategy.moving_average import MovingAverageCrossStrategy
from portfolio.multi_stock_backtest import MultiStockBacktest
from portfolio.watchlist import WatchlistManager

print("=== 诊断 Web 界面回测问题 ===\n")

# 1. 获取自选股列表
wl = WatchlistManager()
all_stocks = wl.get_all_stocks()
print(f"自选股总数: {len(all_stocks)}")

# 2. 获取选中的股票 (模拟 session_state['backtest_selected_stocks'])
selected_symbols = [s.symbol for s in all_stocks[:5]]  # 前5只
print(f"选中的股票: {selected_symbols}\n")

# 3. 回测参数 (模拟 Web 界面参数)
start_date = '2023-01-01'
end_date = '2024-12-31'
initial_capital = 1000000.0
commission_rate = 0.0003
max_positions = 5
rebalance_days = 5
position_method = 'equal'
max_single = 0.2
max_total = 0.8

# 4. 加载数据
dm = DataManager()
stock_data = {}
signals = {}
failed_symbols = []

print("=== 加载数据 ===")
for sym in selected_symbols:
    try:
        df = dm.get_daily_kline(sym, start_date, end_date)
        if df.empty:
            print(f"  [WARN] {sym}: 无数据")
            failed_symbols.append(sym)
            continue

        stock_data[sym] = df

        # 计算信号
        factor_data = FactorData(df)
        df_with_factors = factor_data.calculate_all_factors()
        strat = MovingAverageCrossStrategy({'fast_period': 20, 'slow_period': 60})
        signal_series = strat.get_signal_series(df_with_factors)

        # 设置索引
        if 'date' in df.columns:
            signal_series.index = pd.to_datetime(df['date'])

        signals[sym] = signal_series

        buy_count = sum(signal_series == 1)
        sell_count = sum(signal_series == -1)
        print(f"  {sym}: {len(df)} bars, 信号: buy={buy_count}, sell={sell_count}")

    except Exception as e:
        print(f"  [ERROR] {sym}: {e}")
        failed_symbols.append(sym)

print(f"\n加载成功: {len(stock_data)} 只")
print(f"加载失败: {failed_symbols}\n")

# 5. 运行回测
print("=== 运行回测 ===")
try:
    engine = MultiStockBacktest(
        initial_capital=initial_capital,
        commission_rate=commission_rate,
        max_positions=max_positions,
        rebalance_days=rebalance_days,
        position_method=position_method,
        max_single_position=max_single,
        max_total_position=max_total
    )

    engine.set_data(stock_data, signals)
    print(f"set_data 完成, stock_data: {len(engine.stock_data)} 只")

    results = engine.run(start_date, end_date)
    print(f"run 完成, results keys: {list(results.keys()) if results else 'None'}\n")

except Exception as e:
    print(f"回测执行失败: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# 6. 检查结果
print("=== 检查结果 ===")
print(f"engine.trade_details 数量: {len(engine.trade_details)}")
print(f"engine.active_trades 数量: {len(engine.active_trades)}")

# 检查每只股票的交易数量
symbol_trade_count = {}
for td in engine.trade_details:
    symbol_trade_count[td.symbol] = symbol_trade_count.get(td.symbol, 0) + 1

print(f"\n每只股票的交易次数:")
for sym, count in symbol_trade_count.items():
    print(f"  {sym}: {count} 次")

# 7. 检查 get_trade_details_df()
print(f"\n=== get_trade_details_df() ===")
details_df = engine.get_trade_details_df()
print(f"返回的 DataFrame 行数: {len(details_df)}")
print(f"返回的 DataFrame 列数: {len(details_df.columns)}")
print(f"列名: {details_df.columns.tolist()}")

if not details_df.empty:
    print(f"\nget_trade_details_df() returned {len(details_df)} rows")
    print(f"Columns: {details_df.columns.tolist()}")
    
    # 检查是否包含 000001.SH
    sym_000001 = details_df[details_df['股票'] == '000001.SH']
    print(f"\n000001.SH records: {len(sym_000001)}")
else:
    print("[ERROR] get_trade_details_df() returned empty DataFrame!")

# 8. 检查 active_trades
print(f"\n=== active_trades ===")
for sym, td in engine.active_trades.items():
    print(f"  {sym}: status={td.status}, entry_date={td.entry_date}")