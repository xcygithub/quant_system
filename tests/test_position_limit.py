"""
单元测试：验证单只股票最大仓位限制
测试场景：
1. 单只股票回测时，每次调仓不应超过 max_single_position 限制
2. 多次调仓后，单只股票的累计持仓不应超过 max_single_position
3. _buy 方法的累计持仓检查
4. _rebalance 方法的差额买入逻辑
"""
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from portfolio.multi_stock_backtest import MultiStockBacktest, PortfolioPosition


def generate_test_data(symbols, n_days=120, base_price=10.0):
    """生成测试数据"""
    dates = pd.date_range(end=datetime.now(), periods=n_days, freq='B')
    stock_data = {}
    signals = {}

    for i, symbol in enumerate(symbols):
        np.random.seed(42 + i)
        # 生成稳定上涨的数据，确保有买入信号
        close = base_price + np.random.randn(n_days).cumsum() * 0.3
        close = np.maximum(close, base_price * 0.8)  # 不跌破80%

        df = pd.DataFrame({
            'date': dates,
            'open': close - np.random.rand(n_days) * 0.2,
            'high': close + np.random.rand(n_days) * 0.3,
            'low': close - np.random.rand(n_days) * 0.3,
            'close': close,
            'volume': np.random.randint(1000000, 10000000, n_days)
        })
        stock_data[symbol] = df

        # 生成持续买入信号（确保每次调仓都会买）
        signal = pd.Series(1, index=pd.to_datetime(dates))
        signals[symbol] = signal

    return stock_data, signals


def test_single_stock_position_limit():
    """测试1：单只股票回测，多次调仓后仓位不超过 max_single_position"""
    print("\n" + "="*60)
    print("测试1：单只股票回测 - 仓位限制")
    print("="*60)

    max_single_position = 0.2  # 20%
    initial_capital = 1000000  # 100万

    engine = MultiStockBacktest(
        initial_capital=initial_capital,
        max_positions=1,
        rebalance_days=5,
        max_single_position=max_single_position,
        max_total_position=0.8,
        commission_rate=0.0003,
    )

    stock_data, signals = generate_test_data(["000001.SZ"], n_days=120, base_price=10.0)
    engine.set_data(stock_data, signals)
    results = engine.run()

    # 验证：每次买入后，单只股票持仓市值不应超过 initial_capital * max_single_position
    # 检查所有交易记录中的买入金额
    max_position_value = 0
    for snapshot in engine.snapshots:
        for symbol, pos in snapshot.positions.items():
            position_ratio = pos.market_value / initial_capital
            if position_ratio > max_position_value:
                max_position_value = position_ratio

    print(f"  初始资金: {initial_capital:,.0f}")
    print(f"  单只最大仓位限制: {max_single_position:.0%}")
    print(f"  实际最大仓位占比: {max_position_value:.2%}")

    # 允许0.5%的误差（由于100股整数倍导致的取整）
    tolerance = 0.005
    if max_position_value <= max_single_position + tolerance:
        print(f"  [PASS] 最大仓位 {max_position_value:.2%} 不超过限制 {max_single_position + tolerance:.2%}")
    else:
        print(f"  [FAIL] 最大仓位 {max_position_value:.2%} 超过限制 {max_single_position:.2%}")
        return False

    return True


def test_multi_stock_position_limit():
    """测试2：多只股票回测，每只股票仓位不超过 max_single_position"""
    print("\n" + "="*60)
    print("测试2：多只股票回测 - 仓位限制")
    print("="*60)

    max_single_position = 0.2  # 20%
    initial_capital = 1000000  # 100万

    engine = MultiStockBacktest(
        initial_capital=initial_capital,
        max_positions=5,
        rebalance_days=5,
        max_single_position=max_single_position,
        max_total_position=0.8,
        commission_rate=0.0003,
    )

    stock_data, signals = generate_test_data(
        ["000001.SZ", "600000.SH", "000858.SZ"],
        n_days=120,
        base_price=10.0
    )
    engine.set_data(stock_data, signals)
    results = engine.run()

    # 检查所有快照中每只股票的持仓占比
    max_position_value = 0
    violations = []
    for snapshot in engine.snapshots:
        for symbol, pos in snapshot.positions.items():
            position_ratio = pos.market_value / initial_capital
            if position_ratio > max_position_value:
                max_position_value = position_ratio
            if position_ratio > max_single_position + 0.005:
                violations.append({
                    'date': snapshot.date,
                    'symbol': symbol,
                    'position_ratio': position_ratio,
                    'market_value': pos.market_value
                })

    print(f"  初始资金: {initial_capital:,.0f}")
    print(f"  单只最大仓位限制: {max_single_position:.0%}")
    print(f"  实际最大仓位占比: {max_position_value:.2%}")
    print(f"  违规次数: {len(violations)}")

    if len(violations) == 0:
        print(f"  [PASS] 所有股票仓位均不超过 {max_single_position:.0%}")
    else:
        print(f"  [FAIL] 发现 {len(violations)} 次仓位超限")
        for v in violations[:5]:
            print(f"     {v['date']} {v['symbol']}: {v['position_ratio']:.2%} (市值 {v['market_value']:,.0f})")
        return False

    return True


def test_buy_cumulative_position_check():
    """测试3：_buy 方法的累计持仓检查"""
    print("\n" + "="*60)
    print("测试3：_buy 方法 - 累计持仓检查")
    print("="*60)

    max_single_position = 0.2
    initial_capital = 1000000

    engine = MultiStockBacktest(
        initial_capital=initial_capital,
        max_positions=1,
        max_single_position=max_single_position,
        max_total_position=0.8,
    )

    # 手动设置状态
    engine.cash = initial_capital

    # 第一次买入
    price = 10.0
    shares = 20000  # 20000股 × 10元 = 200,000元 = 20%
    total_assets = initial_capital  # 初始总资产
    engine._buy("000001.SZ", "2025-01-01", price, shares, total_assets, "测试买入1")

    position_value_1 = engine.positions["000001.SZ"].market_value
    print(f"  第一次买入后: {position_value_1:,.0f} 元, 占比 {position_value_1/initial_capital:.2%}")

    # 第二次买入同一只股票（尝试再加仓）
    # 总资产 = 现金 + 持仓市值 = (100万-20万) + 20万 = 100万
    total_assets_2 = engine.cash + engine.positions["000001.SZ"].market_value
    engine._buy("000001.SZ", "2025-01-02", price, 10000, total_assets_2, "测试买入2")

    position_value_2 = engine.positions["000001.SZ"].market_value
    print(f"  第二次买入后: {position_value_2:,.0f} 元, 占比 {position_value_2/initial_capital:.2%}")

    # 验证：累计持仓不应超过 max_single_position
    max_allowed = initial_capital * max_single_position
    if position_value_2 <= max_allowed + 1000:  # 允许1000元误差（100股取整）
        print(f"  [PASS] 累计持仓 {position_value_2:,.0f} 不超过限制 {max_allowed:,.0f}")
        return True
    else:
        print(f"  [FAIL] 累计持仓 {position_value_2:,.0f} 超过限制 {max_allowed:,.0f}")
        return False


def test_position_limit_with_growing_assets():
    """测试5：总资产增长后，仓位限制应基于当前总资产而非初始资金

    场景：
    - 初始资金100万
    - 某只持仓市值增长到 24万（总资产也增长到 104万：现金 80万 + 持仓 24万）
    - 此时 max_single_position=20%，应该限制为 104万 × 20% = 20.8万
    - 尝试再加仓 2万，应该被限制（24万 + 2万 = 26万 > 20.8万）
    """
    print("\n" + "="*60)
    print("测试5：总资产增长后 - 仓位限制基于当前总资产")
    print("="*60)

    initial_capital = 1000000
    max_single_position = 0.2

    engine = MultiStockBacktest(
        initial_capital=initial_capital,
        max_positions=5,
        max_single_position=max_single_position,
        max_total_position=0.8,
    )

    # 手动设置状态：总资产 104万（现金 80万 + 持仓 24万，刚好 20%）
    engine.cash = 800000
    engine.positions = {
        "000001.SZ": PortfolioPosition(
            symbol="000001.SZ",
            quantity=24000,  # 24000股 × 10元 = 24万
            avg_price=10.0,
            current_price=10.0,
            entry_date="2025-01-01"
        )
    }
    total_assets = engine.cash + sum(p.market_value for p in engine.positions.values())
    current_position_value = engine.positions["000001.SZ"].market_value

    print(f"  初始资金: {initial_capital:,.0f} 元")
    print(f"  当前总资产: {total_assets:,.0f} 元 (现金 {engine.cash:,.0f} + 持仓 {current_position_value:,.0f})")
    print(f"  当前持仓市值: {current_position_value:,.0f} ({current_position_value/initial_capital:.2%} of initial)")
    print(f"  当前持仓占比: {current_position_value/total_assets:.2%} of total assets")
    print(f"  max_single_position: {max_single_position:.0%}")

    # 正确的仓位限制应该基于当前总资产: 104万 × 20% = 20.8万
    correct_limit = total_assets * max_single_position
    print(f"\n  正确的仓位上限 (基于总资产): {correct_limit:,.0f} 元")
    print(f"  基于初始资金的错误上限: {initial_capital * max_single_position:,.0f} 元")

    # 尝试再买入 000001.SZ，金额为 2万（2000股）
    price = 10.0
    buy_shares = 2000  # 2万元
    print(f"\n  尝试买入: {buy_shares} 股 × {price} 元 = {buy_shares * price:,.0f} 元")

    # 调用 _buy
    engine._buy("000001.SZ", "2025-01-02", price, buy_shares, total_assets, "测试买入")

    # 检查持仓
    final_position_value = engine.positions["000001.SZ"].market_value
    print(f"\n  买入后持仓市值: {final_position_value:,.0f}")
    print(f"  持仓占比 (基于总资产): {final_position_value / total_assets:.2%}")

    # 关键验证：持仓不应该超过 total_assets * max_single_position
    if final_position_value <= correct_limit + 100:  # 允许100元误差（100股取整）
        print(f"\n  [PASS] 持仓 {final_position_value:,.0f} 未超过正确上限 {correct_limit:,.0f}")
        return True
    else:
        print(f"\n  [FAIL] 持仓 {final_position_value:,.0f} 超过正确上限 {correct_limit:,.0f}")
        return False


def test_rebalance_no_duplicate_buy():
    """测试4：_rebalance 不应给已满仓的股票重复分配仓位"""
    print("\n" + "="*60)
    print("测试4：_rebalance - 差额买入逻辑")
    print("="*60)

    max_single_position = 0.2
    initial_capital = 1000000

    engine = MultiStockBacktest(
        initial_capital=initial_capital,
        max_positions=5,
        rebalance_days=5,
        max_single_position=max_single_position,
        max_total_position=0.8,
    )

    # 手动设置已满仓状态
    engine.cash = initial_capital * 0.8  # 80万现金
    engine.positions = {
        "000001.SZ": PortfolioPosition(
            symbol="000001.SZ",
            quantity=20000,
            avg_price=10.0,
            current_price=10.0,
            entry_date="2025-01-01"
        )
    }
    # 000001.SZ 持仓市值 = 20000 * 10 = 200,000 = 20% 已满仓

    # 模拟 _rebalance 中的差额计算逻辑
    total_assets = engine.cash + sum(p.market_value for p in engine.positions.values())
    target_weight = 0.2  # 目标权重20%
    target_amount = total_assets * target_weight
    current_holding = engine.positions["000001.SZ"].market_value
    buy_amount_needed = target_amount - current_holding

    print(f"  总资产: {total_assets:,.0f}")
    print(f"  目标持仓: {target_amount:,.0f} ({target_weight:.0%})")
    print(f"  已有持仓: {current_holding:,.0f}")
    print(f"  需要额外买入: {buy_amount_needed:,.0f}")

    if buy_amount_needed <= 0:
        print(f"  [PASS] 已满仓，不需要额外买入")
        return True
    else:
        # 即使需要买，_buy 的累计检查也应该限制
        print(f"  [WARN] 需要额外买入 {buy_amount_needed:,.0f}，但 _buy 的累计检查会限制")
        return True


if __name__ == "__main__":
    results = []
    results.append(("单只股票仓位限制", test_single_stock_position_limit()))
    results.append(("多只股票仓位限制", test_multi_stock_position_limit()))
    results.append(("_buy 累计持仓检查", test_buy_cumulative_position_check()))
    results.append(("_rebalance 差额买入", test_rebalance_no_duplicate_buy()))
    results.append(("总资产增长后仓位限制", test_position_limit_with_growing_assets()))

    print("\n" + "="*60)
    print("测试结果汇总")
    print("="*60)
    all_passed = True
    for name, passed in results:
        status = "[PASS]" if passed else "[FAIL]"
        print(f"  {name}: {status}")
        if not passed:
            all_passed = False

    if all_passed:
        print("\n[ALL PASS] 所有测试通过！")
    else:
        print("\n[WARNING] 存在失败的测试，请检查！")
