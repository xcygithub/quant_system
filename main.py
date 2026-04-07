"""
量化交易系统主入口

提供完整的量化交易流程示例
"""
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

# 导入系统模块
from data.data_manager import DataManager
from data.factor_data import FactorData
from backtest.engine import BacktestEngine, VectorizedBacktest
from backtest.performance import PerformanceAnalyzer
from strategy.moving_average import MovingAverageCrossStrategy, MACDStrategy, BollingerBandsStrategy
from strategy.multi_factor import MultiFactorStrategy, RSIStrategy
from risk.manager import RiskManager, PositionSizer, PositionSizingMethod, RiskLimits
from portfolio.watchlist import WatchlistManager, get_watchlist_manager
from portfolio.multi_stock_backtest import MultiStockBacktest, run_multi_stock_backtest


class QuantSystem:
    """
    量化交易系统主类
    
    整合数据、策略、回测、风控等模块
    """
    
    def __init__(self, config: dict = None):
        """
        初始化量化系统
        
        Args:
            config: 配置字典
        """
        self.config = config or {}
        
        # 初始化各模块
        self.data_manager = DataManager(
            db_path=self.config.get('db_path', None)  # 默认使用统一的数据库路径
        )
        
        self.risk_manager = RiskManager(
            limits=RiskLimits(
                max_position_pct=self.config.get('max_position_pct', 0.95),
                max_single_position_pct=self.config.get('max_single_position_pct', 0.3),
                max_drawdown_limit=self.config.get('max_drawdown_limit', 0.2)
            ),
            position_sizer=PositionSizer(
                method=PositionSizingMethod.FIXED_PERCENT,
                params={'position_pct': self.config.get('position_pct', 0.2)}
            )
        )
        
        self.results = {}
    
    def run_backtest(
        self,
        strategy: str,
        symbol: str,
        start_date: str,
        end_date: str,
        initial_capital: float = 1000000,
        strategy_params: dict = None
    ) -> dict:
        """
        运行策略回测
        
        Args:
            strategy: 策略名称 (ma_cross/macd/bollinger/multi_factor/rsi)
            symbol: 股票代码
            start_date: 开始日期
            end_date: 结束日期
            initial_capital: 初始资金
            strategy_params: 策略参数
            
        Returns:
            回测结果字典
        """
        print(f"\n{'='*60}")
        print(f"开始回测: {strategy} | {symbol} | {start_date} ~ {end_date}")
        print(f"{'='*60}\n")
        
        # 1. 获取数据
        print("📊 获取数据...")
        df = self.data_manager.get_daily_kline(symbol, start_date, end_date)
        
        if df.empty:
            print(f"❌ 未获取到 {symbol} 的数据")
            return {}
        
        print(f"✅ 获取到 {len(df)} 条数据")
        
        # 2. 计算因子
        print("🔢 计算因子...")
        factor_data = FactorData(df)
        df = factor_data.calculate_all_factors()
        print(f"✅ 计算了 {len(df.columns)} 个因子")
        
        # 3. 创建策略
        print("🎯 初始化策略...")
        strategy_params = strategy_params or {}
        
        if strategy == 'ma_cross':
            strat = MovingAverageCrossStrategy(strategy_params)
        elif strategy == 'macd':
            strat = MACDStrategy(strategy_params)
        elif strategy == 'bollinger':
            strat = BollingerBandsStrategy(strategy_params)
        elif strategy == 'multi_factor':
            strat = MultiFactorStrategy(strategy_params)
        elif strategy == 'rsi':
            strat = RSIStrategy(strategy_params)
        else:
            raise ValueError(f"未知策略: {strategy}")
        
        print(f"✅ 策略: {strat.name}")
        
        # 4. 运行回测
        print("🚀 运行回测...")
        engine = VectorizedBacktest(
            initial_capital=initial_capital,
            commission_rate=self.config.get('commission_rate', 0.0003)
        )
        
        signal_series = strat.get_signal_series(df)
        results = engine.run(df, signal_series)
        
        # 5. 绩效分析
        print("📈 分析绩效...")
        equity_curve = pd.DataFrame({
            'date': df['date'] if 'date' in df.columns else df.index,
            'equity': results['equity_curve']['strategy_equity']
        })
        
        analyzer = PerformanceAnalyzer(equity_curve)
        metrics = analyzer.calculate_all_metrics()
        
        # 6. 输出结果
        print("\n" + "="*60)
        print("回测结果")
        print("="*60)
        
        returns = metrics['returns']
        ratios = metrics['ratios']
        drawdown = metrics['drawdown']
        
        print(f"\n📊 收益指标:")
        print(f"  总收益率: {returns['total_return']:.2%}")
        print(f"  年化收益率: {returns['annual_return']:.2%}")
        
        print(f"\n⚖️ 风险指标:")
        print(f"  最大回撤: {drawdown['max_drawdown']:.2%}")
        print(f"  年化波动率: {metrics['risk']['volatility']:.2%}")
        
        print(f"\n📐 风险调整收益:")
        print(f"  夏普比率: {ratios['sharpe_ratio']:.2f}")
        print(f"  索提诺比率: {ratios['sortino_ratio']:.2f}")
        print(f"  卡玛比率: {ratios['calmar_ratio']:.2f}")
        
        print("\n" + "="*60)
        
        # 保存结果
        self.results = {
            'strategy': strategy,
            'symbol': symbol,
            'period': f"{start_date} ~ {end_date}",
            'metrics': metrics,
            'equity_curve': equity_curve,
            'data': df,
            'signals': signal_series
        }
        
        return self.results

    def run_multi_stock_backtest(
        self,
        strategy: str,
        symbols: list,
        start_date: str,
        end_date: str,
        initial_capital: float = 1000000,
        strategy_params: dict = None,
        max_positions: int = 5,
        rebalance_days: int = 5,
        position_method: str = "equal",
        max_single_position: float = 0.3,
        max_total_position: float = 0.8
    ) -> dict:
        """
        运行多股票策略回测

        Args:
            strategy: 策略名称 (ma_cross/macd/bollinger/multi_factor/rsi)
            symbols: 股票代码列表
            start_date: 开始日期
            end_date: 结束日期
            initial_capital: 初始资金
            strategy_params: 策略参数
            max_positions: 最大持仓股票数
            rebalance_days: 调仓周期（交易日）
            position_method: 仓位分配方法 (equal/risk_parity/momentum/score/kelly)
            max_single_position: 单只股票最大仓位比例
            max_total_position: 最大总仓位比例

        Returns:
            回测结果字典
        """
        print(f"\n{'='*60}")
        print(f"开始多股票回测 | 策略: {strategy} | 股票数: {len(symbols)}")
        print(f"回测期间: {start_date} ~ {end_date}")
        print(f"{'='*60}\n")

        # 1. 获取所有股票数据
        print("📊 获取股票数据...")
        stock_data = {}
        strategy_params = strategy_params or {}

        for symbol in symbols:
            df = self.data_manager.get_daily_kline(symbol, start_date, end_date)
            if not df.empty:
                stock_data[symbol] = df
                print(f"  ✅ {symbol}: {len(df)} 条数据")
            else:
                print(f"  ❌ {symbol}: 无数据")

        if len(stock_data) == 0:
            print("❌ 所有股票都没有数据!")
            return {}

        print(f"\n✅ 成功获取 {len(stock_data)} 只股票的数据")

        # 2. 为每只股票计算信号
        print("\n🎯 生成交易信号...")
        signals = {}

        for symbol, df in stock_data.items():
            try:
                # 计算因子
                factor_data = FactorData(df)
                df_with_factors = factor_data.calculate_all_factors()

                # 创建策略
                if strategy == 'ma_cross':
                    strat = MovingAverageCrossStrategy(strategy_params)
                elif strategy == 'macd':
                    strat = MACDStrategy(strategy_params)
                elif strategy == 'bollinger':
                    strat = BollingerBandsStrategy(strategy_params)
                elif strategy == 'multi_factor':
                    strat = MultiFactorStrategy(strategy_params)
                elif strategy == 'rsi':
                    strat = RSIStrategy(strategy_params)
                else:
                    raise ValueError(f"未知策略: {strategy}")

                # 获取信号
                signal_series = strat.get_signal_series(df_with_factors)
                signals[symbol] = signal_series

            except Exception as e:
                print(f"  ⚠️ {symbol} 信号计算失败: {e}")

        print(f"✅ 成功生成 {len(signals)} 只股票的信号")

        # 3. 运行多股票回测
        print("\n🚀 运行多股票回测...")
        engine = MultiStockBacktest(
            initial_capital=initial_capital,
            commission_rate=self.config.get('commission_rate', 0.0003),
            max_positions=max_positions,
            rebalance_days=rebalance_days,
            position_method=position_method,
            max_single_position=max_single_position,
            max_total_position=max_total_position
        )

        engine.set_data(stock_data, signals)
        results = engine.run(start_date, end_date)

        # 4. 保存结果
        self.results = results

        return results

    def compare_strategies(
        self,
        strategies: list,
        symbol: str,
        start_date: str,
        end_date: str
    ) -> pd.DataFrame:
        """
        对比多个策略
        
        Args:
            strategies: 策略名称列表
            symbol: 股票代码
            start_date: 开始日期
            end_date: 结束日期
            
        Returns:
            对比结果DataFrame
        """
        print(f"\n{'='*60}")
        print(f"策略对比: {symbol}")
        print(f"{'='*60}\n")
        
        comparison = []
        
        for strategy in strategies:
            result = self.run_backtest(strategy, symbol, start_date, end_date)
            
            if result:
                metrics = result['metrics']
                comparison.append({
                    '策略': strategy,
                    '总收益率': f"{metrics['returns']['total_return']:.2%}",
                    '年化收益': f"{metrics['returns']['annual_return']:.2%}",
                    '最大回撤': f"{metrics['drawdown']['max_drawdown']:.2%}",
                    '夏普比率': f"{metrics['ratios']['sharpe_ratio']:.2f}",
                    '索提诺比率': f"{metrics['ratios']['sortino_ratio']:.2f}",
                    '卡玛比率': f"{metrics['ratios']['calmar_ratio']:.2f}"
                })
        
        df_comparison = pd.DataFrame(comparison)
        print("\n📊 策略对比表:")
        print(df_comparison.to_string(index=False))
        
        return df_comparison
    
    def optimize_parameters(
        self,
        strategy: str,
        symbol: str,
        start_date: str,
        end_date: str,
        param_grid: dict
    ) -> dict:
        """
        策略参数优化
        
        Args:
            strategy: 策略名称
            symbol: 股票代码
            start_date: 开始日期
            end_date: 结束日期
            param_grid: 参数网格，如 {'fast_period': [5, 10, 20], 'slow_period': [30, 60]}
            
        Returns:
            最优参数和结果
        """
        print(f"\n{'='*60}")
        print(f"参数优化: {strategy}")
        print(f"{'='*60}\n")
        
        from itertools import product
        
        # 生成参数组合
        keys = list(param_grid.keys())
        values = list(param_grid.values())
        combinations = list(product(*values))
        
        print(f"共 {len(combinations)} 组参数需要测试")
        
        best_sharpe = -np.inf
        best_params = None
        best_result = None
        
        for i, combo in enumerate(combinations):
            params = dict(zip(keys, combo))
            print(f"\n测试参数 {i+1}/{len(combinations)}: {params}")
            
            result = self.run_backtest(
                strategy, symbol, start_date, end_date,
                strategy_params=params
            )
            
            if result:
                sharpe = result['metrics']['ratios']['sharpe_ratio']
                if sharpe > best_sharpe:
                    best_sharpe = sharpe
                    best_params = params
                    best_result = result
                    print(f"  ⭐ 新的最优参数! 夏普比率: {sharpe:.2f}")
        
        print(f"\n{'='*60}")
        print("参数优化完成")
        print(f"最优参数: {best_params}")
        print(f"最优夏普比率: {best_sharpe:.2f}")
        print(f"{'='*60}")
        
        return {
            'best_params': best_params,
            'best_result': best_result,
            'best_sharpe': best_sharpe
        }
    
    def generate_report(self, save_path: str = None):
        """生成详细报告"""
        if not self.results:
            print("请先运行回测")
            return
        
        analyzer = PerformanceAnalyzer(self.results['equity_curve'])
        report = analyzer.generate_report()
        
        print(report)
        
        if save_path:
            with open(save_path, 'w', encoding='utf-8') as f:
                f.write(report)
            print(f"\n报告已保存至: {save_path}")


def demo():
    """演示量化系统的使用"""
    print("\n" + "="*70)
    print("🚀 量化交易系统演示")
    print("="*70)
    
    # 初始化系统
    config = {
        'initial_capital': 1000000,
        'commission_rate': 0.0003,
        'position_pct': 0.3,
        'max_drawdown_limit': 0.15
    }
    
    system = QuantSystem(config)
    
    # 设置回测参数
    symbol = "000001"  # 平安银行
    start_date = "2023-01-01"
    end_date = "2024-12-31"
    
    # 1. 单策略回测
    print("\n" + "-"*70)
    print("【演示1】单策略回测 - 均线交叉策略")
    print("-"*70)
    
    result = system.run_backtest(
        strategy='ma_cross',
        symbol=symbol,
        start_date=start_date,
        end_date=end_date,
        strategy_params={'fast_period': 10, 'slow_period': 30}
    )
    
    # 2. 多策略对比
    print("\n" + "-"*70)
    print("【演示2】多策略对比")
    print("-"*70)
    
    comparison = system.compare_strategies(
        strategies=['ma_cross', 'macd', 'rsi', 'bollinger'],
        symbol=symbol,
        start_date=start_date,
        end_date=end_date
    )
    
    # 3. 参数优化
    print("\n" + "-"*70)
    print("【演示3】参数优化")
    print("-"*70)
    
    optimization = system.optimize_parameters(
        strategy='ma_cross',
        symbol=symbol,
        start_date=start_date,
        end_date=end_date,
        param_grid={
            'fast_period': [5, 10, 20],
            'slow_period': [30, 60, 120]
        }
    )
    
    print("\n" + "="*70)
    print("✅ 演示完成！")
    print("="*70)


if __name__ == "__main__":
    demo()
