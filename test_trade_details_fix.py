"""
测试交易明细修复
验证 _calculate_results 返回 trade_details，以及 get_trade_details_df 正确生成表格
"""
import sys
sys.path.insert(0, 'c:/Users/FY/WorkBuddy/Claw/quant_system')

import pandas as pd
import numpy as np
from portfolio.multi_stock_backtest import MultiStockBacktest


def create_stock_data(symbol, days=60, start_price=100.0):
    """创建单只股票测试数据"""
    np.random.seed(hash(symbol) % 1000)
    dates = pd.date_range('2024-01-01', periods=days, freq='B')  # 工作日
    close_prices = start_price * (1 + np.random.randn(days) * 0.02).cumprod()

    df = pd.DataFrame({
        'date': dates,
        'open': close_prices * 0.99,
        'high': close_prices * 1.02,
        'low': close_prices * 0.98,
        'close': close_prices,
        'volume': np.random.randint(1000000, 10000000, days)
    })
    return df


def create_signals_for_stock(df):
    """为单只股票创建信号：每5天买入一次"""
    dates = pd.to_datetime(df['date']).dt.strftime('%Y-%m-%d')
    signals = pd.Series(0, index=dates)
    # 每5个交易日信号为1（买入）
    signals.iloc[::5] = 1
    return signals


def test_trade_details_in_results():
    """测试 _calculate_results 返回结果中包含 trade_details"""
    print("=" * 60)
    print("Test 1: trade_details in results")
    print("=" * 60)

    # 创建测试数据
    stocks = {
        'TEST1': create_stock_data('TEST1', days=60, start_price=100.0),
        'TEST2': create_stock_data('TEST2', days=60, start_price=50.0),
    }

    # 创建信号
    signals = {}
    for symbol, df in stocks.items():
        signals[symbol] = create_signals_for_stock(df)

    # 运行回测
    backtest = MultiStockBacktest(
        initial_capital=100000.0,
        max_positions=2,
        rebalance_days=5
    )
    backtest.set_data(stocks, signals)
    results = backtest.run()

    # 检查 results 中是否包含 trade_details
    print(f"\n检查 results['trade_details']:")
    if 'trade_details' in results:
        trade_df = results['trade_details']
        print(f"  [PASS] trade_details 键存在")
        print(f"  类型: {type(trade_df)}")
        if not trade_df.empty:
            print(f"  形状: {trade_df.shape}")
            print(f"  列名: {list(trade_df.columns)}")
            print(f"\n前3条交易明细:")
            print(trade_df.head(3).to_string())
        else:
            print(f"  [WARN] trade_details 为空 DataFrame")
    else:
        print(f"  [FAIL] trade_details 键不存在!")
        print(f"  实际键: {list(results.keys())}")
        return False

    return True


def test_get_trade_details_df():
    """测试 get_trade_details_df 方法"""
    print("\n" + "=" * 60)
    print("Test 2: get_trade_details_df() method")
    print("=" * 60)

    # 创建测试数据
    stocks = {
        'TEST1': create_stock_data('TEST1', days=60, start_price=100.0),
    }

    # 创建信号
    signals = {}
    for symbol, df in stocks.items():
        signals[symbol] = create_signals_for_stock(df)

    # 运行回测
    backtest = MultiStockBacktest(
        initial_capital=100000.0,
        max_positions=1,
        rebalance_days=5
    )
    backtest.set_data(stocks, signals)
    results = backtest.run()

    # 直接调用 get_trade_details_df
    trade_df = backtest.get_trade_details_df()

    print(f"\nget_trade_details_df() 结果:")
    print(f"  类型: {type(trade_df)}")
    if not trade_df.empty:
        print(f"  形状: {trade_df.shape}")
        print(f"  列名: {list(trade_df.columns)}")
        print(f"\n所有交易明细:")
        print(trade_df.to_string())
    else:
        print(f"  [WARN] 返回空 DataFrame")
        print(f"  engine.trade_details 数量: {len(backtest.trade_details)}")
        for td in backtest.trade_details:
            print(f"    {td.symbol}: entry={td.entry_date}, exit={td.exit_date}, status={td.status}")

    return not trade_df.empty


def test_multi_factor_backtest_trade_details():
    """测试 MultiFactorBacktest 返回 trade_details"""
    print("\n" + "=" * 60)
    print("Test 3: MultiFactorBacktest trade_details")
    print("=" * 60)

    from portfolio.multi_factor_backtest import run_multi_factor_backtest

    # 创建测试数据
    stocks = {
        'TEST1': create_stock_data('TEST1', days=60, start_price=100.0),
        'TEST2': create_stock_data('TEST2', days=60, start_price=50.0),
    }

    # 因子数据
    factor_data = {}
    for symbol, df in stocks.items():
        np.random.seed(hash(symbol) % 1000)
        factor_df = pd.DataFrame({
            'date': df['date'],
            'symbol': symbol,
            'roe': np.random.uniform(0.05, 0.20, len(df)),
            'pe': np.random.uniform(5, 30, len(df)),
        })
        factor_data[symbol] = factor_df

    # 运行多因子回测
    results = run_multi_factor_backtest(
        symbols=list(stocks.keys()),
        stock_data=stocks,
        factor_data=factor_data,
        start_date='2024-01-01',
        end_date='2024-04-01',
        initial_capital=100000.0,
        max_positions=2,
        rebalance_days=5,
        use_ic_weighting=False  # 简化测试
    )

    print(f"\n多因子回测结果:")
    print(f"  total_return: {results.get('total_return', 'N/A'):.2%}")
    print(f"  final_value: {results.get('final_value', 'N/A'):,.2f}")

    # 检查 trade_details
    if 'trade_details' in results:
        trade_df = results['trade_details']
        print(f"\n  [PASS] trade_details 存在")
        if not trade_df.empty:
            print(f"  交易明细数量: {len(trade_df)}")
            print(f"  列名: {list(trade_df.columns)}")
        else:
            print(f"  [WARN] trade_details 为空")
    else:
        print(f"  [FAIL] trade_details 不存在!")
        print(f"  可用键: {list(results.keys())}")
        return False

    return True


if __name__ == '__main__':
    print("交易明细修复测试")
    print("=" * 60)

    all_passed = True

    # Test 1
    try:
        result1 = test_trade_details_in_results()
        all_passed = all_passed and result1
    except Exception as e:
        print(f"[ERROR] Test 1 failed: {e}")
        import traceback
        traceback.print_exc()
        all_passed = False

    # Test 2
    try:
        result2 = test_get_trade_details_df()
        all_passed = all_passed and result2
    except Exception as e:
        print(f"[ERROR] Test 2 failed: {e}")
        import traceback
        traceback.print_exc()
        all_passed = False

    # Test 3
    try:
        result3 = test_multi_factor_backtest_trade_details()
        all_passed = all_passed and result3
    except Exception as e:
        print(f"[ERROR] Test 3 failed: {e}")
        import traceback
        traceback.print_exc()
        all_passed = False

    print("\n" + "=" * 60)
    if all_passed:
        print("所有测试通过!")
    else:
        print("部分测试失败!")
    print("=" * 60)