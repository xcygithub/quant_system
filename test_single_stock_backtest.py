"""
单股票回测单元测试
"""
import sys
sys.path.insert(0, 'c:/Users/FY/WorkBuddy/Claw/quant_system')

import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from backtest.engine import VectorizedBacktest
from strategy.moving_average import MovingAverageCrossStrategy


def create_sample_kline_data(days=100, start_price=100.0):
    """创建模拟K线数据"""
    dates = pd.date_range(start=datetime(2024, 1, 1), periods=days, freq='D')

    # 生成随机价格数据
    np.random.seed(42)
    returns = np.random.randn(days) * 0.02  # 日收益率波动2%
    close_prices = start_price * (1 + returns).cumprod()
    high_prices = close_prices * (1 + np.abs(np.random.randn(days) * 0.01))
    low_prices = close_prices * (1 - np.abs(np.random.randn(days) * 0.01))
    open_prices = close_prices * (1 + np.random.randn(days) * 0.005)
    volumes = np.random.randint(1000000, 10000000, days)

    df = pd.DataFrame({
        'date': dates,
        'open': open_prices,
        'high': high_prices,
        'low': low_prices,
        'close': close_prices,
        'volume': volumes,
        'symbol': 'TEST'
    })
    return df


def test_vectorized_backtest_basic():
    """测试VectorizedBacktest基本功能"""
    print("=" * 60)
    print("测试1: VectorizedBacktest基本功能")
    print("=" * 60)

    # 创建测试数据
    df = create_sample_kline_data(days=100)
    print(f"测试数据: {len(df)} 条K线")
    print(f"日期范围: {df['date'].min()} ~ {df['date'].max()}")

    # 创建信号序列 (简单策略: 均线金叉买，死叉卖)
    df['ma5'] = df['close'].rolling(5).mean()
    df['ma20'] = df['close'].rolling(20).mean()
    df['signal'] = np.where(df['ma5'] > df['ma20'], 1, -1)

    # 初始化回测引擎
    initial_capital = 100000.0
    commission_rate = 0.0003

    engine = VectorizedBacktest(
        initial_capital=initial_capital,
        commission_rate=commission_rate
    )

    # 运行回测
    signal_series = df['signal']
    results = engine.run(
        price_data=df,
        signal_series=signal_series
    )

    # 验证返回结果
    print(f"\n回测结果:")
    print(f"  总收益率: {results['total_return']:.2%}")
    print(f"  年化收益率: {results['annual_return']:.2%}")
    print(f"  夏普比率: {results['sharpe_ratio']:.2f}")
    print(f"  最大回撤: {results['max_drawdown']:.2%}")
    print(f"  交易次数: {len(results['trades'])}")

    # 验证equity_curve结构
    equity_df = results['equity_curve']
    print(f"\nequity_curve列名: {list(equity_df.columns)}")
    print(f"equity_curve行数: {len(equity_df)}")

    # 断言验证
    assert 'market_equity' in equity_df.columns, "缺少market_equity列"
    assert 'strategy_equity' in equity_df.columns, "缺少strategy_equity列"
    assert len(equity_df) == len(df), "equity_curve行数与输入数据不匹配"
    assert results['total_return'] is not None, "总收益率为None"
    assert results['sharpe_ratio'] is not None, "夏普比率为None"

    print("\n✓ 测试1通过!")
    return results


def test_vectorized_backtest_with_strategy():
    """测试VectorizedBacktest与策略集成"""
    print("\n" + "=" * 60)
    print("测试2: VectorizedBacktest与策略集成")
    print("=" * 60)

    # 创建测试数据
    df = create_sample_kline_data(days=100)
    print(f"测试数据: {len(df)} 条K线")

    # 使用策略生成信号
    strategy = MovingAverageCrossStrategy({
        'short_window': 5,
        'long_window': 20
    })

    signal_series = strategy.get_signal_series(df)
    print(f"信号序列长度: {len(signal_series)}")
    print(f"买入信号数量: {(signal_series == 1).sum()}")
    print(f"卖出信号数量: {(signal_series == -1).sum()}")

    # 运行回测
    engine = VectorizedBacktest(
        initial_capital=100000.0,
        commission_rate=0.0003
    )

    results = engine.run(
        price_data=df,
        signal_series=signal_series
    )

    print(f"\n回测结果:")
    print(f"  总收益率: {results['total_return']:.2%}")
    print(f"  年化收益率: {results['annual_return']:.2%}")
    print(f"  夏普比率: {results['sharpe_ratio']:.2f}")
    print(f"  最大回撤: {results['max_drawdown']:.2%}")
    print(f"  交易次数: {len(results['trades'])}")

    # 验证结果
    assert results['total_return'] is not None, "总收益率为None"
    assert abs(results['total_return']) < 100, "总收益率异常（超过100倍）"  # 合理范围检查

    print("\n✓ 测试2通过!")
    return results


def test_equity_curve_structure():
    """测试权益曲线数据结构"""
    print("\n" + "=" * 60)
    print("测试3: 权益曲线数据结构")
    print("=" * 60)

    df = create_sample_kline_data(days=50)
    df['signal'] = np.where(df['close'].pct_change() > 0, 1, -1)

    engine = VectorizedBacktest(initial_capital=100000.0)
    results = engine.run(price_data=df, signal_series=df['signal'])

    equity_df = results['equity_curve']

    # 检查必需列
    required_cols = ['market_equity', 'strategy_equity']
    for col in required_cols:
        assert col in equity_df.columns, f"缺少必需列: {col}"

    # 检查数据类型
    assert equity_df['market_equity'].dtype in [np.float64, np.float32], "market_equity类型错误"
    assert equity_df['strategy_equity'].dtype in [np.float64, np.float32], "strategy_equity类型错误"

    # 检查值是否为正
    assert (equity_df['market_equity'] > 0).all(), "market_equity存在非正值"
    assert (equity_df['strategy_equity'] > 0).all(), "strategy_equity存在非正值"

    print(f"权益曲线结构验证通过")
    print(f"  初始权益: {equity_df['strategy_equity'].iloc[0]:,.2f}")
    print(f"  最终权益: {equity_df['strategy_equity'].iloc[-1]:,.2f}")

    print("\n✓ 测试3通过!")


def test_trades_generation():
    """测试交易记录生成"""
    print("\n" + "=" * 60)
    print("测试4: 交易记录生成")
    print("=" * 60)

    df = create_sample_kline_data(days=60)

    # 创建明显的金叉死叉信号
    df['ma5'] = df['close'].rolling(5).mean()
    df['ma20'] = df['close'].rolling(20).mean()
    df['signal'] = np.where(df['ma5'] > df['ma20'], 1, -1)

    engine = VectorizedBacktest(initial_capital=100000.0)
    results = engine.run(price_data=df, signal_series=df['signal'])

    trades = results['trades']
    print(f"生成交易记录: {len(trades)} 笔")

    if len(trades) > 0:
        print(f"\n第一笔交易:")
        t = trades[0]
        print(f"  买入日期: {t['entry_date']}")
        print(f"  买入价格: {t['entry_price']:.2f}")
        print(f"  买入数量: {t['entry_quantity']}")
        print(f"  买入金额: {t['entry_value']:,.2f}")
        if t['exit_date'] != '持有中':
            print(f"  卖出日期: {t['exit_date']}")
            print(f"  卖出价格: {t['exit_price']:.2f}")
            print(f"  收益率: {t['return_rate']:.2%}")
            print(f"  收益金额: {t['profit']:.2f}")
        else:
            print(f"  状态: 持有中")
            print(f"  浮动收益率: {t['return_rate']:.2%}")
            print(f"  浮动盈亏: {t['profit']:.2f}")

    print("\n✓ 测试4通过!")


def test_empty_signal():
    """测试无交易信号的情况"""
    print("\n" + "=" * 60)
    print("测试5: 无交易信号情况")
    print("=" * 60)

    df = create_sample_kline_data(days=30)
    # 全是持仓信号（不交易）
    df['signal'] = 0

    engine = VectorizedBacktest(initial_capital=100000.0)
    results = engine.run(price_data=df, signal_series=df['signal'])

    print(f"交易次数: {len(results['trades'])}")
    print(f"总收益率: {results['total_return']:.2%}")
    print(f"换手率: {results['turnover']:.2%}")

    assert results['turnover'] == 0, "无信号时换手率应为0"
    assert len(results['trades']) == 0, "无信号时应无交易记录"

    print("\n✓ 测试5通过!")


def test_edge_cases():
    """测试边界情况"""
    print("\n" + "=" * 60)
    print("测试6: 边界情况测试")
    print("=" * 60)

    # 测试1: 极短数据
    print("\n6.1 极短数据 (5条)")
    df = create_sample_kline_data(days=5)
    df['signal'] = 1
    engine = VectorizedBacktest(initial_capital=100000.0)
    try:
        results = engine.run(price_data=df, signal_series=df['signal'])
        print(f"    收益率: {results['total_return']:.2%}")
    except Exception as e:
        print(f"    异常: {e}")

    # 测试2: 初始资金为0
    print("\n6.2 初始资金为0")
    df = create_sample_kline_data(days=30)
    df['signal'] = 1
    engine = VectorizedBacktest(initial_capital=0.0)
    try:
        results = engine.run(price_data=df, signal_series=df['signal'])
        print(f"    收益率: {results['total_return']:.2%}")
    except Exception as e:
        print(f"    异常: {e}")

    # 测试3: 全是买入信号
    print("\n6.3 全是买入信号")
    df = create_sample_kline_data(days=30)
    df['signal'] = 1
    engine = VectorizedBacktest(initial_capital=100000.0)
    try:
        results = engine.run(price_data=df, signal_series=df['signal'])
        print(f"    交易次数: {len(results['trades'])}")
        print(f"    收益率: {results['total_return']:.2%}")
    except Exception as e:
        print(f"    异常: {e}")

    # 测试4: 手续费为0
    print("\n6.4 手续费为0")
    df = create_sample_kline_data(days=30)
    df['signal'] = 1
    engine = VectorizedBacktest(initial_capital=100000.0, commission_rate=0.0)
    try:
        results = engine.run(price_data=df, signal_series=df['signal'])
        print(f"    收益率: {results['total_return']:.2%}")
    except Exception as e:
        print(f"    异常: {e}")

    print("\n✓ 测试6完成!")


if __name__ == "__main__":
    print("\n" + "#" * 60)
    print("# 单股票回测单元测试")
    print("#" * 60)

    try:
        test_vectorized_backtest_basic()
        test_vectorized_backtest_with_strategy()
        test_equity_curve_structure()
        test_trades_generation()
        test_empty_signal()
        test_edge_cases()

        print("\n" + "#" * 60)
        print("# 所有测试通过!")
        print("#" * 60)
    except AssertionError as e:
        print(f"\n测试失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    except Exception as e:
        print(f"\n测试异常: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)