"""
多股票回测调试测试 - 逐步验证每只股票的交易情况
"""
import sys
sys.path.insert(0, 'c:/Users/FY/WorkBuddy/Claw/quant_system')

import pandas as pd
import numpy as np
from datetime import datetime
from portfolio.multi_stock_backtest import MultiStockBacktest
from portfolio.selector import create_selector


def create_stock_data_with_distinct_signals(symbol, days=60, start_price=100.0, signal_bias=0):
    """
    创建单只股票测试数据 - 控制信号偏向

    signal_bias: 0=均衡, 正值=偏向买入信号多, 负值=偏向卖出信号多
    """
    np.random.seed(hash(symbol) % 1000 + signal_bias)
    dates = pd.date_range('2024-01-01', periods=days, freq='D')

    # 创建有明显趋势的价格
    trend = np.linspace(0, 0.3 * signal_bias, days) if signal_bias != 0 else 0
    close_prices = start_price * (1 + trend + np.random.randn(days) * 0.02).cumprod()

    df = pd.DataFrame({
        'date': dates,
        'open': close_prices * 0.99,
        'high': close_prices * 1.02,
        'low': close_prices * 0.98,
        'close': close_prices,
        'volume': np.random.randint(1000000, 10000000, days)
    })

    # 添加均线信号 - 根据趋势倾向调整
    df['ma5'] = df['close'].rolling(5).mean()
    df['ma20'] = df['close'].rolling(20).mean()

    # signal_bias > 0: MA5更容易大于MA20 (买入信号多)
    # signal_bias < 0: MA5更容易小于MA20 (卖出信号多)
    if signal_bias > 0:
        df['signal'] = np.where(df['ma5'] > df['ma20'] * (1 - 0.02 * signal_bias), 1, -1)
    elif signal_bias < 0:
        df['signal'] = np.where(df['ma5'] > df['ma20'] * (1 + 0.02 * abs(signal_bias)), 1, -1)
    else:
        df['signal'] = np.where(df['ma5'] > df['ma20'], 1, -1)

    # 确保有足够的买入和卖出信号
    buy_count = (df['signal'] == 1).sum()
    sell_count = (df['signal'] == -1).sum()

    print(f"  {symbol}: days={days}, close_range={close_prices[0]:.2f}->{close_prices[-1]:.2f}, "
          f"buy_signals={buy_count}, sell_signals={sell_count}")

    return df


def test_multi_stock_with_distinct_symbols():
    """
    测试多股票回测 - 验证不同股票代码都有交易记录

    关键验证点：
    1. 每只股票是否都有机会被选中（至少有一次入选候选）
    2. 每只股票是否都有买入记录（至少一次）
    3. 交易明细表里有多少只不同的股票代码
    """
    print("\n" + "#" * 60)
    print("# Test: Multi-stock backtest with DISTINCT symbols")
    print("#" * 60)

    # 创建三只有明显不同特征的股票
    stocks = {}
    signals = {}

    stock_configs = [
        ('601919.SH', 100.0, 1),    # 601919 - 上涨趋势，买入信号多
        ('000001.SZ', 50.0, 0),     # 000001 - 震荡市，信号均衡
        ('600519.SH', 80.0, -1),    # 600519 - 下跌趋势，卖出信号多
    ]

    print("\n[Step 1] Creating stock data:")
    for symbol, start_price, bias in stock_configs:
        df = create_stock_data_with_distinct_signals(symbol, days=60, start_price=start_price, signal_bias=bias)
        stocks[symbol] = df
        # 信号转Series并设置日期索引
        sig = pd.Series(df['signal'].values, index=pd.to_datetime(df['date']))
        signals[symbol] = sig

    # 打印信号分布
    print("\n[Step 2] Signal distribution:")
    for symbol, sig in signals.items():
        buy = (sig == 1).sum()
        sell = (sig == -1).sum()
        hold = (sig == 0).sum()
        print(f"  {symbol}: buy={buy}, sell={sell}, hold={hold}")

    # 手动测试选股器
    print("\n[Step 3] Testing selector:")
    selector = create_selector(method="composite", top_n=5)
    scores = selector.score_stocks(stocks, signals)

    print("  All stocks scored:")
    for s in scores:
        print(f"    {s.symbol}: composite={s.composite_score:.2f}, "
              f"momentum={s.momentum_score:.2f}, signal={s.signal_score:.2f} ({s.signal_type}), "
              f"vol={s.volatility_score:.2f}, liq={s.liquidity_score:.2f}")

    print("\n  Buy candidates (select_buy_candidates):")
    candidates = selector.select_buy_candidates(scores, top_n=5, min_score=30)
    for c in candidates:
        print(f"    {c.symbol}: composite={c.composite_score:.2f} ({c.signal_type})")

    # 运行多股票回测
    print("\n[Step 4] Running multi-stock backtest:")
    backtest = MultiStockBacktest(
        initial_capital=1000000.0,
        commission_rate=0.0003,
        stamp_tax=0.001,
        max_positions=5,
        rebalance_days=5,
        position_method="equal",
        selector_method="composite"
    )

    backtest.set_data(stocks, signals)

    # 手动打印选股过程
    print("\n  Manual candidate selection (first 5 days):")
    for i in range(min(5, len(pd.date_range('2024-01-01', periods=60, freq='D')))):
        # 模拟 _select_candidates
        data_for_scoring = {}
        for symbol, df in stocks.items():
            if len(df) >= 20:
                data_for_scoring[symbol] = df

        scores_day = selector.score_stocks(data_for_scoring, signals)
        candidates_day = selector.select_buy_candidates(scores_day, top_n=5, min_score=30)
        print(f"    Day {i}: candidates = {[c.symbol for c in candidates_day]}")

    results = backtest.run()

    # 分析结果
    print("\n[Step 5] Results analysis:")
    print(f"  Total trades: {len(results['trades'])}")
    print(f"  Trade details count: {len(backtest.trade_details)}")
    print(f"  Unique symbols in trades: {set(t.symbol for t in results['trades'])}")
    print(f"  Unique symbols in trade_details: {set(td.symbol for td in backtest.trade_details)}")

    # 打印所有交易记录
    print("\n  All trades:")
    for t in results['trades']:
        print(f"    {t.date} {t.side} {t.symbol} {t.quantity} @ {t.price:.2f}")

    # 打印交易明细
    print("\n  Trade details (trade_details):")
    for td in backtest.trade_details:
        print(f"    {td.symbol}: entry={td.entry_date} @ {td.entry_price:.2f}, "
              f"exit={td.exit_date} @ {td.exit_price:.2f}, "
              f"holding={td.holding_days}days, ret={td.return_rate:.2%}, status={td.status}")

    # 核心验证
    unique_symbols_in_trades = set(td.symbol for td in backtest.trade_details)
    print(f"\n[RESULT] Unique symbols with trade records: {len(unique_symbols_in_trades)}")
    print(f"  Symbols: {unique_symbols_in_trades}")

    # 验证：应该有至少2只不同的股票有交易记录
    if len(unique_symbols_in_trades) >= 2:
        print("\n[PASS] Test passed! Multiple stocks have trade records.")
    else:
        print(f"\n[FAIL] Test failed! Only {len(unique_symbols_in_trades)} stock(s) have trade records.")
        print("  Expected: >= 2 different stocks")
        print("  This indicates a bug in stock selection or trading logic.")

    return backtest, results


def test_with_debug_print():
    """带详细调试输出的测试"""
    print("\n" + "#" * 60)
    print("# Test: Debug - tracing _select_candidates")
    print("#" * 60)

    stocks = {}
    signals = {}

    # 使用两只明显不同的股票
    np.random.seed(42)
    dates = pd.date_range('2024-01-01', periods=60, freq='D')

    # 股票A：持续上涨
    close_a = 100 * (1 + np.linspace(0, 0.5, 60) + np.random.randn(60) * 0.01).cumprod()
    df_a = pd.DataFrame({
        'date': dates, 'close': close_a,
        'volume': np.random.randint(1000000, 5000000, 60)
    })
    df_a['ma5'] = df_a['close'].rolling(5).mean()
    df_a['ma20'] = df_a['close'].rolling(20).mean()
    df_a['signal'] = np.where(df_a['ma5'] > df_a['ma20'], 1, -1)

    stocks['STOCK_A'] = df_a
    signals['STOCK_A'] = pd.Series(df_a['signal'].values, index=pd.to_datetime(df_a['date']))

    # 股票B：持续下跌
    close_b = 100 * (1 - np.linspace(0, 0.3, 60) + np.random.randn(60) * 0.01).cumprod()
    df_b = pd.DataFrame({
        'date': dates, 'close': close_b,
        'volume': np.random.randint(1000000, 5000000, 60)
    })
    df_b['ma5'] = df_b['close'].rolling(5).mean()
    df_b['ma20'] = df_b['close'].rolling(20).mean()
    df_b['signal'] = np.where(df_b['ma5'] > df_b['ma20'], 1, -1)

    stocks['STOCK_B'] = df_b
    signals['STOCK_B'] = pd.Series(df_b['signal'].values, index=pd.to_datetime(df_b['date']))

    print(f"STOCK_A: buy={(signals['STOCK_A']==1).sum()}, sell={(signals['STOCK_A']==-1).sum()}")
    print(f"STOCK_B: buy={(signals['STOCK_B']==1).sum()}, sell={(signals['STOCK_B']==-1).sum()}")

    backtest = MultiStockBacktest(
        initial_capital=100000.0,
        max_positions=2,
        rebalance_days=5
    )
    backtest.set_data(stocks, signals)
    results = backtest.run()

    unique = set(td.symbol for td in backtest.trade_details)
    print(f"\n[RESULT] Unique symbols: {unique} (count={len(unique)})")

    if len(unique) >= 2:
        print("[PASS]")
    else:
        print("[FAIL]")


if __name__ == "__main__":
    try:
        test_multi_stock_with_distinct_symbols()
        test_with_debug_print()
        print("\n" + "#" * 60)
        print("# All tests completed!")
        print("#" * 60)
    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()