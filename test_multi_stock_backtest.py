"""
多股票回测测试用例
用于诊断回测数据问题
"""
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from data.data_manager import DataManager
from data.factor_data import FactorData
from strategy.moving_average import MovingAverageCrossStrategy
from portfolio.multi_stock_backtest import MultiStockBacktest


def test_data_availability():
    """测试股票数据可用性"""
    print("=" * 60)
    print("测试1: 股票数据可用性")
    print("=" * 60)

    dm = DataManager()
    symbols = ["000001.SZ", "601919.SH"]  # 测试用的两只股票
    start_date = "2023-01-01"
    end_date = "2024-12-31"

    stock_data = {}
    for symbol in symbols:
        df = dm.get_daily_kline(symbol, start_date, end_date)
        print(f"\n股票: {symbol}")
        print(f"  数据条数: {len(df)}")
        if not df.empty:
            print(f"  日期范围: {df['date'].min()} ~ {df['date'].max()}")
            print(f"  列名: {list(df.columns)}")
            print(f"  前5行:\n{df.head()}")
            print(f"  后5行:\n{df.tail()}")
            stock_data[symbol] = df
        else:
            print(f"  ❌ 无数据!")

    return stock_data


def test_signal_generation(stock_data):
    """测试信号生成"""
    print("\n" + "=" * 60)
    print("测试2: 信号生成")
    print("=" * 60)

    signals = {}
    strategy_params = {'fast_period': 20, 'slow_period': 60}

    for symbol, df in stock_data.items():
        print(f"\n股票: {symbol}")

        # 计算因子
        factor_data = FactorData(df)
        df_with_factors = factor_data.calculate_all_factors()
        print(f"  计算因子后数据条数: {len(df_with_factors)}")

        # 创建策略
        strategy = MovingAverageCrossStrategy(strategy_params)

        # 获取信号
        signal_series = strategy.get_signal_series(df_with_factors)
        signals[symbol] = signal_series

        print(f"  信号类型: {type(signal_series)}")
        print(f"  信号长度: {len(signal_series)}")
        print(f"  信号索引类型: {type(signal_series.index)}")
        print(f"  信号索引前5个: {list(signal_series.index[:5])}")
        print(f"  信号值分布:")
        print(f"    -1 (卖出): {(signal_series == -1).sum()}")
        print(f"     0 (持有): {(signal_series == 0).sum()}")
        print(f"     1 (买入): {(signal_series == 1).sum()}")
        print(f"  信号前10个:\n{signal_series.head(10)}")

    return signals


def test_date_alignment(stock_data, signals):
    """测试日期对齐"""
    print("\n" + "=" * 60)
    print("测试3: 日期对齐检查")
    print("=" * 60)

    for symbol in stock_data.keys():
        df = stock_data[symbol]
        signal = signals[symbol]

        print(f"\n股票: {symbol}")

        # 数据日期
        data_dates = pd.to_datetime(df['date'])
        print(f"  数据日期类型: {type(data_dates.iloc[0])}")
        print(f"  数据日期示例: {data_dates.iloc[0]}")

        # 信号日期
        signal_dates = signal.index
        print(f"  信号日期类型: {type(signal_dates[0])}")
        print(f"  信号日期示例: {signal_dates[0]}")

        # 检查是否一致
        if hasattr(signal_dates, 'tz') and signal_dates.tz is not None:
            print(f"  信号日期有时区: {signal_dates.tz}")
        if hasattr(data_dates, 'tz') and data_dates.tz is not None:
            print(f"  数据日期有时区: {data_dates.tz}")

        # 转换为相同格式比较
        data_dates_normalized = pd.to_datetime(data_dates).dt.normalize()
        signal_dates_normalized = pd.to_datetime(signal_dates).normalize() if hasattr(signal_dates, 'normalize') else pd.to_datetime(signal_dates)

        common_dates = set(data_dates_normalized) & set(signal_dates_normalized)
        print(f"  共同日期数量: {len(common_dates)}")
        print(f"  数据独有日期: {len(set(data_dates_normalized) - set(signal_dates_normalized))}")
        print(f"  信号独有日期: {len(set(signal_dates_normalized) - set(data_dates_normalized))}")


def test_backtest_engine(stock_data, signals):
    """测试回测引擎"""
    print("\n" + "=" * 60)
    print("测试4: 回测引擎")
    print("=" * 60)

    engine = MultiStockBacktest(
        initial_capital=1000000,
        commission_rate=0.0003,
        max_positions=5,
        rebalance_days=5,
        position_method="equal",
        max_single_position=0.2,
        max_total_position=0.8
    )

    engine.set_data(stock_data, signals)

    # 检查内部状态
    print(f"\n回测引擎状态:")
    print(f"  股票数据数量: {len(engine.stock_data)}")
    print(f"  信号数量: {len(engine.signals)}")

    # 获取共同日期
    all_dates = engine._get_common_dates("2023-01-01", "2024-12-31")
    print(f"  共同交易日数量: {len(all_dates)}")
    if len(all_dates) > 0:
        print(f"  回测日期范围: {all_dates[0]} ~ {all_dates[-1]}")
        print(f"  前10个日期: {all_dates[:10]}")

    # 运行回测
    print("\n开始运行回测...")
    results = engine.run("2023-01-01", "2024-12-31")

    print(f"\n回测结果:")
    if results:
        print(f"  总收益率: {results.get('total_return', 0):.2%}")
        print(f"  年化收益率: {results.get('annual_return', 0):.2%}")
        print(f"  夏普比率: {results.get('sharpe_ratio', 0):.2f}")
        print(f"  最大回撤: {results.get('max_drawdown', 0):.2%}")
        print(f"  总交易次数: {results.get('total_trades', 0)}")
        print(f"  买入次数: {results.get('buy_trades', 0)}")
        print(f"  卖出次数: {results.get('sell_trades', 0)}")

        # 检查交易记录
        trades_df = engine.get_trades_df()
        print(f"\n  交易记录数量: {len(trades_df)}")
        if not trades_df.empty:
            print(f"  交易记录前5条:\n{trades_df.head()}")
    else:
        print("  ❌ 回测结果为空!")

    return results


def main():
    """主测试函数"""
    print("\n" + "=" * 60)
    print("多股票回测诊断测试")
    print("=" * 60)

    # 测试1: 数据可用性
    stock_data = test_data_availability()

    if not stock_data:
        print("\n❌ 没有获取到任何股票数据，测试终止")
        return

    # 测试2: 信号生成
    signals = test_signal_generation(stock_data)

    # 测试3: 日期对齐
    test_date_alignment(stock_data, signals)

    # 测试4: 回测引擎
    results = test_backtest_engine(stock_data, signals)

    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)


if __name__ == "__main__":
    main()
