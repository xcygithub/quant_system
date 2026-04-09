"""
详细跟踪第一天调仓的完整过程
"""
import pandas as pd
import numpy as np
from datetime import datetime
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from portfolio.multi_stock_backtest import MultiStockBacktest


def trace_first_day():
    """跟踪第一天的完整调仓过程"""
    print("="*60)
    print("跟踪第一天调仓过程")
    print("="*60)

    initial_capital = 1000000
    max_single_position = 0.2

    engine = MultiStockBacktest(
        initial_capital=initial_capital,
        max_positions=5,
        rebalance_days=5,
        max_single_position=max_single_position,
        max_total_position=0.8,
        commission_rate=0.0003,
    )

    # 创建简单的测试数据
    dates = pd.date_range(end=datetime.now(), periods=120, freq='B')

    stock_data = {}
    signals = {}

    # 股票1：000001.SZ - 价格10元
    np.random.seed(42)
    close1 = 10 + np.random.randn(120).cumsum() * 0.3
    stock_data["000001.SZ"] = pd.DataFrame({
        'date': dates,
        'open': close1 - np.random.rand(120) * 0.2,
        'high': close1 + np.random.rand(120) * 0.3,
        'low': close1 - np.random.rand(120) * 0.3,
        'close': close1,
        'volume': np.random.randint(1000000, 10000000, 120)
    })
    signals["000001.SZ"] = pd.Series(1, index=pd.to_datetime(dates))

    # 股票2：600000.SH - 价格8元
    np.random.seed(43)
    close2 = 8 + np.random.randn(120).cumsum() * 0.25
    stock_data["600000.SH"] = pd.DataFrame({
        'date': dates,
        'open': close2 - np.random.rand(120) * 0.2,
        'high': close2 + np.random.rand(120) * 0.3,
        'low': close2 - np.random.rand(120) * 0.3,
        'close': close2,
        'volume': np.random.randint(1000000, 10000000, 120)
    })
    signals["600000.SH"] = pd.Series(1, index=pd.to_datetime(dates))

    # 股票3：000858.SZ - 价格9元
    np.random.seed(44)
    close3 = 9 + np.random.randn(120).cumsum() * 0.28
    stock_data["000858.SZ"] = pd.DataFrame({
        'date': dates,
        'open': close3 - np.random.rand(120) * 0.2,
        'high': close3 + np.random.rand(120) * 0.3,
        'low': close3 - np.random.rand(120) * 0.3,
        'close': close3,
        'volume': np.random.randint(1000000, 10000000, 120)
    })
    signals["000858.SZ"] = pd.Series(1, index=pd.to_datetime(dates))

    engine.set_data(stock_data, signals)

    # 获取第一天数据
    all_dates = engine._get_common_dates(None, None)
    first_date = all_dates[0]

    print(f"\n第一天: {first_date}")
    print(f"初始现金: {engine.cash:,.0f}")

    # 模拟 _rebalance 开始
    print("\n" + "-"*40)
    print("开始 _rebalance 分析")
    print("-"*40)

    # Step 1: _select_candidates
    new_candidates = engine._select_candidates()
    print(f"\n候选股票: {[c.symbol for c in new_candidates]}")

    # Step 2: 计算 total_assets
    total_assets = engine.cash + sum(p.market_value for p in engine.positions.values())
    print(f"total_assets = cash + positions = {engine.cash:,.0f} + 0 = {total_assets:,.0f}")

    # Step 3: 准备候选数据
    candidate_data = []
    for score in new_candidates:
        volatility = engine._estimate_volatility(score.symbol)
        candidate_data.append((score.symbol, score.composite_score, volatility))
    print(f"\n候选数据: {candidate_data}")

    # Step 4: 调用 position_sizer.allocate
    prices = engine._get_prices_on_date(first_date)
    print(f"当日价格: {prices}")

    allocations = engine.position_sizer.allocate(
        candidate_data,
        total_assets,
        prices
    )
    print(f"\nposition_sizer.allocate() 结果:")
    for a in allocations:
        print(f"  {a.symbol}: weight={a.weight:.4f}, amount={a.amount:,.0f}, shares={a.shares}")

    # Step 5: 执行买入
    print(f"\n执行买入:")
    for alloc in allocations:
        if alloc.symbol in prices and alloc.weight > 0:
            target_amount = total_assets * alloc.weight
            current_holding = engine.positions[alloc.symbol].market_value if alloc.symbol in engine.positions else 0
            buy_amount_needed = target_amount - current_holding

            print(f"\n  {alloc.symbol}:")
            print(f"    target_amount = total_assets * weight = {total_assets:,} * {alloc.weight:.4f} = {target_amount:,.0f}")
            print(f"    current_holding = {current_holding:,.0f}")
            print(f"    buy_amount_needed = {target_amount:,.0f} - {current_holding:,.0f} = {buy_amount_needed:,.0f}")

            price = prices[alloc.symbol]
            buy_shares = int(buy_amount_needed / price / 100) * 100
            print(f"    price = {price}")
            print(f"    buy_shares = int({buy_amount_needed:,.0f} / {price} / 100) * 100 = {buy_shares}")

            if buy_shares >= 100:
                # 实际调用 _buy
                print(f"    -> 调用 _buy(amount={price * buy_shares:,.0f}, total_assets={total_assets:,.0f})")
                engine._buy(alloc.symbol, first_date, price, buy_shares, total_assets, "调仓买入")

    print(f"\n买入后持仓:")
    for symbol, pos in engine.positions.items():
        ratio = pos.market_value / initial_capital
        print(f"  {symbol}: {pos.quantity} 股, 市值 {pos.market_value:,.0f}, 占初始资金 {ratio:.2%}")

    print(f"\n剩余现金: {engine.cash:,.0f}")


if __name__ == "__main__":
    trace_first_day()