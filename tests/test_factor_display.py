"""
测试：多因子回测中展示每只股票各因子值的功能
验证 TradeDetail 扩展、缓存逻辑、调仓快照、UI 数据输出
"""
import pandas as pd
import numpy as np
from datetime import datetime
import sys

# 将项目根目录加入路径
sys.path.insert(0, 'c:/Users/FY/WorkBuddy/Claw/quant_system')

from portfolio.multi_stock_backtest import TradeDetail
from portfolio.multi_factor_backtest import MultiFactorBacktest, RebalanceSnapshot, run_multi_factor_backtest


def test_trade_detail_new_fields():
    """测试 TradeDetail 新增字段"""
    print("\n[Test 1] TradeDetail 新增字段测试")

    td = TradeDetail(
        trade_id=1,
        symbol="600519.SH",
        stock_name="贵州茅台",
        entry_date="2023-02-15",
        entry_price=1850.0,
        entry_quantity=100,
        entry_amount=185000.0,
        factor_values={"roe": 0.152, "pe": 25.3, "momentum_20": 0.121},
        factor_percentiles={"roe": 92.3, "pe": 45.2, "momentum_20": 88.7},
        composite_score=78.5,
        rank=2,
        total_candidates=50
    )

    assert td.stock_name == "贵州茅台", f"stock_name 错误: {td.stock_name}"
    assert td.factor_values["roe"] == 0.152
    assert td.factor_percentiles["momentum_20"] == 88.7
    assert td.composite_score == 78.5
    assert td.rank == 2
    assert td.total_candidates == 50

    # 测试默认值（向后兼容）
    td2 = TradeDetail(trade_id=2, symbol="000001.SZ")
    assert td2.stock_name == ""
    assert td2.factor_values == {}
    assert td2.composite_score == 0.0

    print("  [PASS] TradeDetail 新增字段正常")


def test_factor_caches_and_rebalance():
    """测试 MultiFactorBacktest 缓存和调仓快照"""
    print("\n[Test 2] MultiFactorBacktest 缓存与调仓快照测试")

    dates = pd.date_range('2023-01-01', periods=60, freq='B')
    symbols = ['000001.SZ', '600000.SH', '600519.SH', '600016.SH', '601318.SH']
    stock_names = {
        '000001.SZ': '平安银行',
        '600000.SH': '浦发银行',
        '600519.SH': '贵州茅台',
        '600016.SH': '民生银行',
        '601318.SH': '中国平安'
    }

    stock_data = {}
    for symbol in symbols:
        np.random.seed(hash(symbol) % 2**32)
        stock_data[symbol] = pd.DataFrame({
            'date': dates,
            'open': 10 + np.random.randn(60).cumsum(),
            'high': 10.5 + np.random.randn(60).cumsum(),
            'low': 9.5 + np.random.randn(60).cumsum(),
            'close': 10 + np.random.randn(60).cumsum(),
            'volume': np.random.randint(1000000, 10000000, 60),
            # 基本面因子（模拟）
            'roe': np.random.uniform(0.05, 0.20, 60),
            'pe': np.random.uniform(5, 30, 60),
            'pb': np.random.uniform(0.5, 5, 60),
            'revenue_growth': np.random.uniform(-0.1, 0.3, 60),
            'debt_ratio': np.random.uniform(0.2, 0.8, 60),
        })

    backtest = MultiFactorBacktest(
        initial_capital=1000000,
        max_positions=3,
        rebalance_days=10,
        factor_weights={
            'roe': 0.30,
            'pe': 0.20,
            'pb': 0.10,
            'momentum_20': 0.25,
            'revenue_growth': 0.15
        },
        use_ic_weighting=False
    )
    backtest.stock_names = stock_names

    # 设置数据
    backtest.set_data(stock_data)

    print(f"    DEBUG: set_data 后 panel_cache size = {len(backtest._factor_panel_cache)}")

    # 运行回测
    results = backtest.run(
        symbols=symbols,
        stock_data=stock_data,
        start_date='2023-01-01',
        end_date='2023-03-31'
    )

    print(f"    DEBUG: run 后 panel_cache size = {len(backtest._factor_panel_cache)}")
    print(f"    DEBUG: run 后 percentiles_cache size = {len(backtest._factor_percentiles_cache)}")
    print(f"    DEBUG: run 后 scores_cache size = {len(backtest._composite_scores_cache)}")
    print(f"    DEBUG: rebalance_snapshots = {len(results.get('rebalance_snapshots', []))}")

    # 验证缓存
    assert len(backtest._factor_panel_cache) > 0, "因子面板缓存为空"
    assert len(backtest._factor_percentiles_cache) > 0, "百分位缓存为空"
    assert len(backtest._composite_scores_cache) > 0, "综合得分缓存为空"
    print(f"  [PASS] 缓存正常: panel={len(backtest._factor_panel_cache)}, percentiles={len(backtest._factor_percentiles_cache)}, scores={len(backtest._composite_scores_cache)}")

    # 验证调仓快照
    snapshots = results.get('rebalance_snapshots', [])
    assert len(snapshots) > 0, "调仓快照为空"
    print(f"  [PASS] 调仓快照数量: {len(snapshots)}")

    # 验证快照内容
    snap = snapshots[0]
    assert isinstance(snap, RebalanceSnapshot)
    assert snap.date is not None
    assert len(snap.all_scores) > 0, "快照中无综合得分"
    assert len(snap.all_factor_values) > 0, "快照中无因子原始值"
    print(f"  [PASS] 快照内容正常: scores={len(snap.all_scores)}, factor_values={len(snap.all_factor_values)}")

    # 验证交易明细中的因子信息
    trade_details = results.get('trade_details')
    assert trade_details is not None and not trade_details.empty, "交易明细为空"

    # 检查是否包含因子得分列
    assert '综合得分' in trade_details.columns, "缺少综合得分列"
    assert '排名' in trade_details.columns, "缺少排名列"

    # 检查股票中文名
    first_row = trade_details.iloc[0]
    symbol_str = first_row['股票']
    assert ' - ' in symbol_str, f"股票显示格式错误: {symbol_str}"
    print(f"  [PASS] 交易明细股票显示: {symbol_str}")

    # 检查因子得分列是否存在（以 _得分 结尾的列）
    score_cols = [c for c in trade_details.columns if c.endswith('_得分')]
    print(f"  [PASS] 交易明细因子得分列: {score_cols}")

    # 验证综合得分非空（至少部分交易有得分）
    valid_scores = trade_details['综合得分'].dropna()
    assert len(valid_scores) > 0, "没有交易记录到综合得分"
    print(f"  [PASS] 有 {len(valid_scores)} 笔交易记录了综合得分")

    print("  [PASS] MultiFactorBacktest 缓存与调仓快照测试通过")


def test_run_multi_factor_backtest_with_names():
    """测试便捷函数传入 stock_names"""
    print("\n[Test 3] run_multi_factor_backtest 传入 stock_names 测试")

    dates = pd.date_range('2023-01-01', periods=60, freq='B')
    symbols = ['000001.SZ', '600519.SH']
    stock_names = {'000001.SZ': '平安银行', '600519.SH': '贵州茅台'}

    stock_data = {}
    for symbol in symbols:
        np.random.seed(hash(symbol) % 2**32)
        stock_data[symbol] = pd.DataFrame({
            'date': dates,
            'open': 10 + np.random.randn(60).cumsum(),
            'high': 10.5 + np.random.randn(60).cumsum(),
            'low': 9.5 + np.random.randn(60).cumsum(),
            'close': 10 + np.random.randn(60).cumsum(),
            'volume': np.random.randint(1000000, 10000000, 60),
            'roe': np.random.uniform(0.05, 0.20, 60),
            'pe': np.random.uniform(5, 30, 60),
            'momentum_20': np.random.uniform(-0.1, 0.1, 60),
        })

    results = run_multi_factor_backtest(
        symbols=symbols,
        stock_data=stock_data,
        start_date='2023-01-01',
        end_date='2023-03-31',
        initial_capital=1000000,
        max_positions=2,
        rebalance_days=10,
        factor_weights={'roe': 0.5, 'pe': 0.3, 'momentum_20': 0.2},
        use_ic_weighting=False,
        stock_names=stock_names
    )

    trade_details = results.get('trade_details')
    assert trade_details is not None and not trade_details.empty

    # 验证股票名称
    for _, row in trade_details.iterrows():
        sym_display = row['股票']
        code = row['股票代码']
        name = row['股票名称']
        assert name in stock_names.values(), f"股票名称未正确记录: {name}"
        expected_display = f"{code} - {name}"
        assert sym_display == expected_display, f"显示格式错误: {sym_display} != {expected_display}"

    print(f"  [PASS] 便捷函数 stock_names 传递正常，共 {len(trade_details)} 笔交易")
    print("  [PASS] run_multi_factor_backtest 测试通过")


def test_rebalance_snapshot_content():
    """测试调仓快照具体内容"""
    print("\n[Test 4] 调仓快照内容验证")

    dates = pd.date_range('2023-01-01', periods=40, freq='B')
    symbols = ['000001.SZ', '600000.SH', '600519.SH']
    stock_names = {
        '000001.SZ': '平安银行',
        '600000.SH': '浦发银行',
        '600519.SH': '贵州茅台'
    }

    stock_data = {}
    for symbol in symbols:
        np.random.seed(hash(symbol) % 2**32)
        stock_data[symbol] = pd.DataFrame({
            'date': dates,
            'open': 10 + np.random.randn(40).cumsum(),
            'high': 10.5 + np.random.randn(40).cumsum(),
            'low': 9.5 + np.random.randn(40).cumsum(),
            'close': 10 + np.random.randn(40).cumsum(),
            'volume': np.random.randint(1000000, 10000000, 40),
            'roe': np.random.uniform(0.05, 0.25, 40),
            'pe': np.random.uniform(5, 30, 40),
            'pb': np.random.uniform(0.5, 5, 40),
            'momentum_20': np.random.uniform(-0.1, 0.1, 40),
        })

    backtest = MultiFactorBacktest(
        initial_capital=1000000,
        max_positions=2,
        rebalance_days=15,
        factor_weights={'roe': 0.4, 'pe': 0.3, 'pb': 0.15, 'momentum_20': 0.15},
        use_ic_weighting=False
    )
    backtest.stock_names = stock_names
    backtest.set_data(stock_data)

    results = backtest.run(
        symbols=symbols,
        stock_data=stock_data,
        start_date='2023-01-01',
        end_date='2023-02-28'
    )

    snapshots = results.get('rebalance_snapshots', [])
    assert len(snapshots) >= 1, "应至少有1次调仓"

    snap = snapshots[0]
    # 验证 all_scores 包含所有股票
    for sym in symbols:
        assert sym in snap.all_scores, f"快照缺少 {sym} 的综合得分"

    # 验证 all_factor_values 包含因子原始值
    for sym in symbols:
        assert sym in snap.all_factor_values, f"快照缺少 {sym} 的因子原始值"
        vals = snap.all_factor_values[sym]
        assert 'roe' in vals or 'pe' in vals, f"{sym} 因子值内容异常: {vals}"

    # 验证 all_factor_percentiles 包含百分位得分
    for sym in symbols:
        assert sym in snap.all_factor_percentiles, f"快照缺少 {sym} 的百分位得分"
        percs = snap.all_factor_percentiles[sym]
        for factor in ['roe', 'pe', 'pb', 'momentum_20']:
            if factor in percs:
                assert 0 <= percs[factor] <= 100, f"{sym}.{factor} 百分位超出范围: {percs[factor]}"

    # 验证 selected_symbols 不为空（因为初始持仓应该买入股票）
    assert len(snap.selected_symbols) > 0, "首次调仓应买入股票"
    print(f"  [PASS] 首次调仓买入: {snap.selected_symbols}")
    print(f"  [PASS] 调仓快照内容验证通过")


def main():
    print("=" * 60)
    print("多因子因子值展示功能测试")
    print("=" * 60)

    try:
        test_trade_detail_new_fields()
        test_factor_caches_and_rebalance()
        test_run_multi_factor_backtest_with_names()
        test_rebalance_snapshot_content()

        print("\n" + "=" * 60)
        print("[SUCCESS] 所有测试通过！")
        print("=" * 60)
    except AssertionError as e:
        print(f"\n[FAIL] 测试失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    except Exception as e:
        print(f"\n[FAIL] 测试异常: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
