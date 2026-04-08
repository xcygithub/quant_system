"""
多股票回测测试 - 使用真实数据库数据
"""
import sys
sys.path.insert(0, 'c:/Users/FY/WorkBuddy/Claw/quant_system')

import pandas as pd
import numpy as np
from datetime import datetime
from portfolio.multi_stock_backtest import MultiStockBacktest
from data.data_manager import DataManager


def test_with_real_data():
    """使用真实数据库数据测试"""
    print("=" * 60)
    print("Test: Real Data Backtest (601919, 000001.SH)")
    print("=" * 60)

    dm = DataManager()
    symbols = ['601919', '000001.SH']

    # 获取数据
    stock_data = {}
    signals = {}

    for symbol in symbols:
        # 获取日线数据
        df = dm.get_daily_kline(symbol, '2024-01-01', '2024-12-31')
        if df.empty:
            print(f"  [WARN] {symbol} no data")
            continue

        # 保留必要的列
        df = df[['date', 'open', 'high', 'low', 'close', 'volume']].copy()

        # 生成均线交叉信号
        df['ma5'] = df['close'].rolling(5).mean()
        df['ma20'] = df['close'].rolling(20).mean()
        df['signal'] = np.where(df['ma5'] > df['ma20'], 1,
                                np.where(df['ma5'] < df['ma20'], -1, 0))

        stock_data[symbol] = df

        # 创建信号序列
        signals[symbol] = df.set_index('date')['signal']

        print(f"  {symbol}: {len(df)} bars")
        print(f"    Signal counts: buy={len(df[df['signal']==1])}, sell={len(df[df['signal']==-1])}, hold={len(df[df['signal']==0])}")

    if len(stock_data) == 0:
        print("[ERROR] No stock data loaded!")
        return

    # 打印信号日期
    for symbol, sig in signals.items():
        buy_dates = [str(d)[:10] for d in sig[sig == 1].index]
        print(f"\n{symbol} BUY signals on: {buy_dates[:10]}...")

    # 运行回测
    backtest = MultiStockBacktest(
        initial_capital=1000000.0,
        max_positions=5,
        rebalance_days=5,
        commission_rate=0.0003
    )

    # 调试：先打印选股评分
    selector = backtest.selector
    scores = selector.score_stocks(stock_data, signals)

    print(f"\n=== Stock Scores ===")
    for s in scores:
        print(f"  {s.symbol}: composite_score={s.composite_score:.2f}, signal_type={s.signal_type}, signal_strength={s.signal_strength:.2f}")

    candidates = selector.select_buy_candidates(scores, top_n=backtest.max_positions, min_score=30)
    print(f"\n=== Buy Candidates (min_score=30) ===")
    for c in candidates:
        print(f"  {c.symbol}: score={c.composite_score:.2f}, signal_type={c.signal_type}")

    # 尝试降低门槛
    candidates_no_min = selector.select_buy_candidates(scores, top_n=backtest.max_positions, min_score=0)
    print(f"\n=== Buy Candidates (min_score=0) ===")
    for c in candidates_no_min:
        print(f"  {c.symbol}: score={c.composite_score:.2f}, signal_type={c.signal_type}")

    backtest.set_data(stock_data, signals)
    results = backtest.run('2024-01-01', '2024-12-31')

    print(f"\n=== Results ===")
    print(f"Total trades: {len(results['trades'])}")
    print(f"Trade details count: {len(backtest.trade_details)}")
    print(f"Active trades count: {len(backtest.active_trades)}")

    # 打印所有买入交易
    buy_trades = [t for t in results['trades'] if t.side == 'BUY']
    print(f"\nBUY trades ({len(buy_trades)}):")
    for t in buy_trades:
        print(f"  {t.date} {t.symbol} {t.quantity} @ {t.price:.2f}")

    # 打印所有交易详情
    print(f"\nTrade Details ({len(backtest.trade_details)}):")
    for td in backtest.trade_details:
        print(f"  [{td.trade_id}] {td.symbol}: entry={td.entry_date} @ {td.entry_price:.2f}, exit={td.exit_date} @ {td.exit_price:.2f}, status={td.status}")

    # 警告：检查有信号但没有交易的股票
    print("\n=== Signal vs Trade Comparison ===")
    for symbol in signals.keys():
        signal_count = len(signals[symbol][signals[symbol] == 1])
        has_trade = any(t.symbol == symbol for t in results['trades'])
        trade_detail_exists = any(td.symbol == symbol for td in backtest.trade_details)

        print(f"{symbol}:")
        print(f"  - Buy signals: {signal_count}")
        print(f"  - Has trade record: {has_trade}")
        print(f"  - Has trade detail: {trade_detail_exists}")

        if signal_count > 0 and not trade_detail_exists:
            print(f"  *** [ALERT] {symbol} has {signal_count} buy signals but NO trade detail! ***")

    # 获取交易详情DataFrame
    details_df = backtest.get_trade_details_df()
    if not details_df.empty:
        print(f"\n=== Trade Details DataFrame ===")
        # 使用utf-8编码避免中文编码问题
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
        print(details_df.to_string())


if __name__ == "__main__":
    test_with_real_data()
