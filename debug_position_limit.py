"""
诊断脚本：复现仓位超限问题
场景：多只股票，max_single_position=20%，初始100万
"""
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from portfolio.multi_stock_backtest import MultiStockBacktest, PortfolioPosition


def test_position_limit_issue():
    """
    复现问题：初始100万，max_single_position=20%
    多股票调仓时，某股票仓位可能超过20%

    原因分析：
    1. position_sizer.allocate() 基于 total_assets 计算权重
    2. 但 allocate() 返回的 weight 可能基于初始资金计算
    3. 当持仓市值增长后，重新调仓时权重计算可能出错
    """
    print("="*60)
    print("诊断：仓位超限问题")
    print("="*60)

    initial_capital = 1000000  # 100万
    max_single_position = 0.2  # 20%

    engine = MultiStockBacktest(
        initial_capital=initial_capital,
        max_positions=5,
        rebalance_days=5,
        max_single_position=max_single_position,
        max_total_position=0.8,
        commission_rate=0.0003,
    )

    # 创建测试数据：3只股票，120天
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
    # 持续买入信号
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
    results = engine.run()

    # 分析每次调仓的仓位变化
    print("\n" + "="*60)
    print("详细分析：每次调仓后的仓位")
    print("="*60)

    rebalance_count = 0
    for i, snapshot in enumerate(engine.snapshots):
        if len(snapshot.positions) > 0:
            total_val = snapshot.total_value
            print(f"\n交易日 {i} ({snapshot.date.strftime('%Y-%m-%d')}):")
            print(f"  总资产: {total_val:,.0f} 元")

            for symbol, pos in snapshot.positions.items():
                ratio = pos.market_value / initial_capital  # 用初始资金作为基准
                asset_ratio = pos.market_value / total_val  # 用总资产作为基准
                print(f"  {symbol}: 市值 {pos.market_value:,.0f}, "
                      f"占初始资金 {ratio:.2%}, "
                      f"占总资产 {asset_ratio:.2%}")

                if ratio > max_single_position + 0.001:
                    print(f"    [警告] 超过20%限制!")

    # 关键检查：每只股票的累计持仓是否超过限制
    print("\n" + "="*60)
    print("持仓记录：检查单只股票最大仓位")
    print("="*60)

    max_position_seen = 0
    violations = []

    for i, snapshot in enumerate(engine.snapshots):
        for symbol, pos in snapshot.positions.items():
            position_value = pos.market_value
            ratio = position_value / initial_capital

            if ratio > max_position_seen:
                max_position_seen = ratio

            if ratio > max_single_position + 0.005:  # 超过20.5%视为违规
                violations.append({
                    'day': i,
                    'date': snapshot.date,
                    'symbol': symbol,
                    'position_value': position_value,
                    'ratio': ratio
                })

    print(f"最大仓位占比（相对于初始资金）: {max_position_seen:.2%}")
    print(f"违规次数: {len(violations)}")

    if violations:
        print("\n违规详情:")
        for v in violations[:10]:
            print(f"  Day {v['day']}: {v['symbol']} "
                  f"市值 {v['position_value']:,.0f} ({v['ratio']:.2%})")

    return len(violations) == 0


if __name__ == "__main__":
    result = test_position_limit_issue()
    if result:
        print("\n[PASS] 没有仓位超限问题")
    else:
        print("\n[FAIL] 发现仓位超限问题!")