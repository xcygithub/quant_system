"""
测试用例：验证止损逻辑
场景：持仓中有3只股票，其中一只已经亏了6%，今天跌了1%，正好7%
预期：今天应该卖出，持有收益率应该是-7%
"""
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

    # 构造简单的测试数据
def create_test_data():
    """
    创建3只股票的测试数据
    股票A (000001.SZ): 20天数据，成本价10元，第20天跌到9.3元（亏损7%）
    股票B (000002.SZ): 20天数据，正常波动
    股票C (000003.SZ): 20天数据，正常波动
    """
    dates = pd.date_range(start='2024-01-01', periods=20, freq='D')

    # 股票A: 20天内从10元跌到8.5元（亏损15%，明显超过7%止损线）
    # 第1天买入价10元，第20天收盘价8.5元
    # 前15天保持在10元，最后5天从10跌到8.5
    prices_a = [10.0] * 15 + [9.5, 9.2, 9.0, 8.7, 8.5]
    stock_a = pd.DataFrame({
        'date': dates,
        'open': prices_a,
        'high': [p + 0.1 for p in prices_a],
        'low': [p - 0.1 for p in prices_a],
        'close': prices_a,
        'volume': [1000000] * 20
    })

    # 股票B: 正常上涨
    stock_b = pd.DataFrame({
        'date': dates,
        'open': [10.0 + i * 0.05 for i in range(20)],
        'high': [10.1 + i * 0.05 for i in range(20)],
        'low': [9.9 + i * 0.05 for i in range(20)],
        'close': [10.0 + i * 0.05 for i in range(20)],
        'volume': [1000000] * 20
    })

    # 股票C: 正常波动
    stock_c = pd.DataFrame({
        'date': dates,
        'open': [10.0] * 20,
        'high': [10.2] * 20,
        'low': [9.8] * 20,
        'close': [10.0 + 0.05 * (i % 2) for i in range(20)],
        'volume': [1000000] * 20
    })

    return {
        '000001.SZ': stock_a,
        '000002.SZ': stock_b,
        '000003.SZ': stock_c
    }


def create_signals(stock_data):
    """
    创建信号：第1天全买1，其余天持股不动
    这样第1天建仓，然后测试止损逻辑
    """
    signals = {}
    for symbol, df in stock_data.items():
        # 第1天买入信号(1)，其余天持有(0)
        sig = [1] + [0] * (len(df) - 1)
        signals[symbol] = pd.Series(sig, index=df['date'])
    return signals


def test_stop_loss_at_7_percent():
    """
    测试：持仓亏损7%时是否触发止损
    """
    from portfolio.multi_stock_backtest import MultiStockBacktest

    print("=" * 60)
    print("测试：持仓亏损7%时止损测试")
    print("=" * 60)

    # 创建测试数据
    stock_data = create_test_data()

    # 信号：第1天全买1，其余天持股不动
    signals = create_signals(stock_data)

    # 创建回测引擎
    # stop_loss = -0.07 表示亏损7%时止损
    engine = MultiStockBacktest(
        initial_capital=1000000,  # 100万初始资金
        commission_rate=0.0003,
        max_positions=3,
        rebalance_days=5,  # 第5天调仓一次
        position_method="equal",
        max_single_position=0.3,
        max_total_position=0.9,
        stop_loss=-0.07  # 7%止损
    )

    engine.set_data(stock_data, signals)

    # 手动注入调试，打印每天的持仓和止损检查
    original_check_stop_loss = engine._check_stop_loss
    def debug_check_stop_loss(date, prices):
        for symbol, pos in engine.positions.items():
            if pos.avg_price > 0 and symbol in prices:
                current_price = prices[symbol]
                return_rate = (current_price - pos.avg_price) / pos.avg_price
                print(f"[DEBUG] 日期={str(date)[:10]}, 股票={symbol}, "
                      f"成本={pos.avg_price:.2f}, 现价={current_price:.2f}, "
                      f"收益率={return_rate*100:.2f}%, 止损={engine.stop_loss*100:.2f}%, "
                      f"是否触发={return_rate <= engine.stop_loss}")
        original_check_stop_loss(date, prices)
    engine._check_stop_loss = debug_check_stop_loss

    # 运行回测（不限制日期范围）
    results = engine.run()

    # 获取交易详情
    trade_details = engine.get_trade_details_df()

    print("\n" + "=" * 60)
    print("回测结果分析")
    print("=" * 60)

    if trade_details.empty:
        print("\n没有交易记录！")
        print("可能原因：")
        print("1. 止损逻辑没有触发")
        print("2. 调仓日设置问题（rebalance_days=5，第一天不会调仓买入）")
    else:
        print(f"\n共有 {len(trade_details)} 条交易记录:")
        print(trade_details.to_string())

        # 筛选止损卖出的记录（状态是"已卖出"且收益率接近-7%）
        closed_trades = trade_details[trade_details['状态'] == '已卖出']
        if not closed_trades.empty:
            print(f"\n已卖出的交易 ({len(closed_trades)} 条):")
            for idx, row in closed_trades.iterrows():
                print(f"\n--- 交易 {row['交易ID']} ---")
                print(f"股票: {row['股票']}")
                print(f"买入日期: {row['买入日期']}, 买入价格: {row['买入价格（元）']}")
                print(f"卖出日期: {row['卖出日期']}, 卖出价格: {row['卖出价格（元）']}")
                print(f"收益率: {row['收益率（%）']}%")
                print(f"净收益率: {row['净收益率（%）']}%")
                print(f"持有天数: {row['持有天数']}")

    # 检查持仓
    print("\n" + "=" * 60)
    print("最终持仓状态")
    print("=" * 60)

    if results.get('final_positions'):
        for symbol, info in results['final_positions'].items():
            print(f"{symbol}: {info['quantity']}股, 成本{info['avg_price']:.2f}, "
                  f"现价{info['current_price']:.2f}, 收益率{info['return']:.2%}")
    else:
        print("没有最终持仓（已全部卖出）")

    return results, trade_details


def test_stop_loss_same_day_rebuy():
    """
    测试：止损卖出后，当天是否会被重新买回
    场景：第1天买A股票，第2天跌了7%触发止损
          但如果候选列表中A股票仍然排名第一，会不会被重新买回？
    """
    from portfolio.multi_stock_backtest import MultiStockBacktest

    print("\n" + "=" * 60)
    print("测试：止损后当天是否重新买回")
    print("=" * 60)

    # 构造数据：让A股票始终是候选第一名（需要>=20天数据才能通过选股）
    dates = pd.date_range(start='2024-01-01', periods=20, freq='D')

    # 股票A: 持续下跌
    prices_a = [10.0 - i * 0.3 for i in range(20)]  # 从10跌到4.3
    stock_a = pd.DataFrame({
        'date': dates,
        'open': prices_a,
        'high': [p + 0.1 for p in prices_a],
        'low': [p - 0.1 for p in prices_a],
        'close': prices_a,
        'volume': [1000000] * 20
    })

    # 股票B: 轻微下跌
    prices_b = [10.0 - i * 0.1 for i in range(20)]  # 从10跌到8.1
    stock_b = pd.DataFrame({
        'date': dates,
        'open': prices_b,
        'high': [p + 0.1 for p in prices_b],
        'low': [p - 0.1 for p in prices_b],
        'close': prices_b,
        'volume': [1000000] * 20
    })

    stock_data = {
        '000001.SZ': stock_a,
        '000002.SZ': stock_b
    }

    # 信号：第1天买入(1)，中间天持有(0)，第16天触发止损后由系统卖出
    sig_list = [1] + [0] * 19
    signals = {
        '000001.SZ': pd.Series(sig_list, index=dates),
        '000002.SZ': pd.Series(sig_list, index=dates)
    }

    engine = MultiStockBacktest(
        initial_capital=1000000,
        commission_rate=0.0003,
        max_positions=2,
        rebalance_days=5,  # 第5天才调仓
        position_method="equal",
        max_single_position=0.5,
        max_total_position=0.9,
        stop_loss=-0.07  # 7%止损
    )

    engine.set_data(stock_data, signals)
    results = engine.run()

    trade_details = engine.get_trade_details_df()

    print("\n交易记录:")
    if not trade_details.empty:
        print(trade_details.to_string())
    else:
        print("无交易记录")

    # 分析：如果止损触发但没被重新买回，应该有2笔买入+2笔卖出
    # 如果止损触发后被重新买回，买卖次数会更多

    return results, trade_details


if __name__ == "__main__":
    print("开始止损逻辑测试...")
    print()

    # 测试1：基本止损
    results1, details1 = test_stop_loss_at_7_percent()

    # 测试2：止损后重新买回
    # results2, details2 = test_stop_loss_same_day_rebuy()
