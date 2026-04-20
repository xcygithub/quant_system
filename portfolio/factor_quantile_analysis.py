"""
因子分层回测模块
将股票按因子值分为N组，观察各组收益差异
"""
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
from datetime import datetime
import warnings
warnings.filterwarnings('ignore')

try:
    from backtest.engine import VectorizedBacktest
except ImportError:
    from quant_system.backtest.engine import VectorizedBacktest


class FactorQuantileAnalysis:
    """
    因子分层回测

    将股票按因子值分为N组，观察各组收益差异
    用于验证因子有效性：有效因子应该呈现明显的分层效应
    """

    def __init__(self, n_groups: int = 5):
        """
        初始化

        Args:
            n_groups: 分组数量（默认5组，即五分位数）
        """
        self.n_groups = n_groups

    def quantile_analysis(
        self,
        factor_data: pd.DataFrame,
        returns_data: pd.DataFrame,
        holding_period: int = 20,
        weight_method: str = 'equal'  # 'equal' / '市值加权'
    ) -> Dict:
        """
        分层分析

        Args:
            factor_data: DataFrame(index=date, columns=symbol) 因子值
            returns_data: DataFrame(index=date, columns=symbol) 收益率
            holding_period: 持有期（天）
            weight_method: 权重方法

        Returns:
            {
                'group_returns': DataFrame,  # 各组日均收益
                'cumulative_returns': DataFrame,  # 各组累计收益
                'long_short_return': Series,  # 多空组合收益
                'metrics': {
                    'long_short_ir': 0.8,
                    'top_minus_bottom': 0.12,
                    'spread稳定性': ...
                },
                'group_metrics': {
                    'Group1': {'mean': 0.001, 'std': 0.02, ...},
                    ...
                }
            }
        """
        results = {
            'group_returns': pd.DataFrame(),
            'cumulative_returns': pd.DataFrame(),
            'long_short_return': pd.Series(dtype=float),
            'metrics': {},
            'group_metrics': {}
        }

        if factor_data.empty or returns_data.empty:
            return results

        # 获取所有日期
        dates = sorted(factor_data.index.intersection(returns_data.index))

        if len(dates) < holding_period:
            print(f"[警告] 数据不足: {len(dates)} 天 < {holding_period} 天")
            return results

        # 按日期逐步回测
        group_returns_list = []
        long_short_list = []

        for i in range(holding_period, len(dates)):
            rebalance_date = dates[i - holding_period]
            current_date = dates[i]

            # 获取当日因子值
            if rebalance_date not in factor_data.index:
                continue

            factor_row = factor_data.loc[rebalance_date]

            # 获取未来收益
            if current_date not in returns_data.index:
                continue

            return_row = returns_data.loc[current_date]

            # 去除NaN
            valid_symbols = factor_row.dropna().index.intersection(return_row.dropna().index)

            if len(valid_symbols) < self.n_groups * 2:
                continue

            # 分组
            factor_vals = factor_row[valid_symbols]
            quantiles = pd.qcut(factor_vals, q=self.n_groups, labels=False, duplicates='drop')

            # 计算各组收益
            group_returns = {}
            for g in range(self.n_groups):
                group_symbols = quantiles[quantiles == g].index
                if len(group_symbols) > 0:
                    if weight_method == 'equal':
                        group_returns[f'Group{g+1}'] = return_row[group_symbols].mean()
                    else:
                        # 市值加权（简化：等权重）
                        group_returns[f'Group{g+1}'] = return_row[group_symbols].mean()

            if len(group_returns) == self.n_groups:
                group_returns['date'] = current_date
                group_returns_list.append(group_returns)

                # 多空组合（GroupN - Group1）
                if 'Group1' in group_returns and f'Group{self.n_groups}' in group_returns:
                    long_short = group_returns[f'Group{self.n_groups}'] - group_returns['Group1']
                    long_short_list.append({'date': current_date, 'long_short': long_short})

        if not group_returns_list:
            return results

        # 整理结果
        group_df = pd.DataFrame(group_returns_list).set_index('date')

        results['group_returns'] = group_df

        # 累计收益
        results['cumulative_returns'] = (1 + group_df).cumprod() - 1

        # 多空收益
        if long_short_list:
            ls_df = pd.DataFrame(long_short_list).set_index('date')
            results['long_short_return'] = ls_df['long_short']

            # 多空累计收益
            results['long_short_cumulative'] = (1 + ls_df['long_short']).cumprod() - 1

        # 计算各组统计指标
        for col in group_df.columns:
            if col.startswith('Group'):
                returns = group_df[col].dropna()
                results['group_metrics'][col] = {
                    'mean': returns.mean(),
                    'std': returns.std(),
                    'sharpe': returns.mean() / returns.std() * np.sqrt(252) if returns.std() > 0 else 0,
                    'win_rate': (returns > 0).mean(),
                    'max': returns.max(),
                    'min': returns.min()
                }

        # 计算多空指标
        if not results['long_short_return'].empty:
            ls_returns = results['long_short_return']
            results['metrics']['long_short_ir'] = (
                ls_returns.mean() / ls_returns.std() * np.sqrt(252) if ls_returns.std() > 0 else 0
            )
            results['metrics']['top_minus_bottom'] = (
                (1 + results['cumulative_returns'].iloc[-1][f'Group{self.n_groups}']) /
                (1 + results['cumulative_returns'].iloc[-1]['Group1']) - 1
                if not results['cumulative_returns'].empty else 0
            )

        return results

    def plot_quantile_results(
        self,
        results: Dict,
        save_path: str = None
    ):
        """
        可视化分层回测结果

        Args:
            results: quantile_analysis 返回的结果
            save_path: 保存路径
        """
        try:
            import matplotlib.pyplot as plt
            plt.rcParams['font.sans-serif'] = ['SimHei', 'Arial Unicode MS']
            plt.rcParams['axes.unicode_minus'] = False
        except ImportError:
            print("[警告] matplotlib 未安装")
            return

        if results['cumulative_returns'].empty:
            print("[警告] 无数据可绘图")
            return

        fig, axes = plt.subplots(2, 2, figsize=(14, 10))

        # 1. 累计收益曲线
        ax1 = axes[0, 0]
        cumret = results['cumulative_returns']
        for col in cumret.columns:
            if col.startswith('Group'):
                ax1.plot(cumret.index, cumret[col] * 100, label=col, linewidth=1.5)
        ax1.set_title('Group Cumulative Returns (%)', fontsize=12)
        ax1.set_xlabel('Date')
        ax1.set_ylabel('Return (%)')
        ax1.legend()
        ax1.grid(True, alpha=0.3)

        # 2. 多空累计收益
        ax2 = axes[0, 1]
        if 'long_short_cumulative' in results:
            ax2.plot(results['long_short_cumulative'].index,
                    results['long_short_cumulative'] * 100,
                    color='purple', linewidth=2)
            ax2.axhline(y=0, color='black', linestyle='--', alpha=0.5)
            ax2.set_title('Long-Short Portfolio (Group5 - Group1)', fontsize=12)
            ax2.set_xlabel('Date')
            ax2.set_ylabel('Return (%)')
            ax2.grid(True, alpha=0.3)

        # 3. 分组收益热力图
        ax3 = axes[1, 0]
        group_ret = results['group_returns']
        if not group_ret.empty:
            # 按月聚合
            monthly = group_ret.groupby(pd.Grouper(freq='M')).mean()
            im = ax3.imshow(monthly.T * 100, cmap='RdYlGn', aspect='auto')
            ax3.set_yticks(range(len(monthly.columns)))
            ax3.set_yticklabels(monthly.columns)
            ax3.set_title('Monthly Returns Heatmap (%)', fontsize=12)
            plt.colorbar(im, ax=ax3)

        # 4. 各组统计柱状图
        ax4 = axes[1, 1]
        if results['group_metrics']:
            groups = list(results['group_metrics'].keys())
            means = [results['group_metrics'][g]['mean'] * 100 for g in groups]
            stds = [results['group_metrics'][g]['std'] * 100 for g in groups]

            x = np.arange(len(groups))
            ax4.bar(x, means, yerr=stds, capsize=5, color='steelblue', alpha=0.7)
            ax4.set_xticks(x)
            ax4.set_xticklabels(groups)
            ax4.set_title('Group Mean Returns (%)', fontsize=12)
            ax4.set_ylabel('Return (%)')
            ax4.axhline(y=0, color='black', linestyle='--', alpha=0.5)
            ax4.grid(True, alpha=0.3)

        plt.tight_layout()

        if save_path:
            plt.savefig(save_path, dpi=150, bbox_inches='tight')
            print(f"[保存] 图表已保存: {save_path}")

        return fig

    def generate_quantile_report(
        self,
        results: Dict,
        factor_name: str = None
    ) -> str:
        """
        生成分层回测报告

        Returns:
            Markdown 格式报告
        """
        lines = []
        lines.append(f"# 因子分层回测报告\n")

        if factor_name:
            lines.append(f"**因子**: {factor_name}\n")

        lines.append(f"**分组数**: {self.n_groups}\n")

        if not results['group_metrics']:
            lines.append("\n无有效数据")
            return "\n".join(lines)

        # 各组收益统计
        lines.append("\n## 各组收益统计\n")
        lines.append("| 组别 | 日均收益 | 收益标准差 | 年化夏普 | 胜率 | 最大收益 | 最小收益 |")
        lines.append("|------|---------|-----------|---------|------|---------|---------|")

        for group, metrics in results['group_metrics'].items():
            lines.append(
                f"| {group} | {metrics['mean']*100:.4f}% | {metrics['std']*100:.4f}% | "
                f"{metrics['sharpe']:.2f} | {metrics['win_rate']:.2%} | "
                f"{metrics['max']*100:.2f}% | {metrics['min']*100:.2f}% |"
            )

        # 多空指标
        lines.append("\n## 多空组合指标\n")

        if results['metrics']:
            ls_ir = results['metrics'].get('long_short_ir', 0)
            tmb = results['metrics'].get('top_minus_bottom', 0)

            lines.append(f"- **多空夏普比率**: {ls_ir:.2f}")
            lines.append(f"- **Top-Bottom 收益差**: {tmb*100:.2f}%")

        # 结论
        lines.append("\n## 结论\n")

        if results['group_metrics']:
            g1_return = results['group_metrics'].get('Group1', {}).get('mean', 0)
            gn_return = results['group_metrics'].get(f'Group{self.n_groups}', {}).get('mean', 0)

            if gn_return > g1_return:
                lines.append(f"- 因子呈现 **正向** 分层效应：高分组合表现优于低分组合")
            elif gn_return < g1_return:
                lines.append(f"- 因子呈现 **反向** 分层效应：低分组合表现优于高分组合")
            else:
                lines.append(f"- 因子无明显分层效应")

            if results['metrics'].get('long_short_ir', 0) > 0.5:
                lines.append(f"- 多空组合夏普比率 > 0.5，因子 **稳定有效**")
            elif results['metrics'].get('long_short_ir', 0) > 0.3:
                lines.append(f"- 多空组合夏普比率 > 0.3，因子 **有效**")
            else:
                lines.append(f"- 多空组合夏普比率较低，因子 **效果有限**")

        return "\n".join(lines)


class ICAnalysisVisualizer:
    """
    IC 分析可视化
    """

    @staticmethod
    def plot_ic_series(
        ic_series: pd.Series,
        title: str = 'IC Time Series',
        save_path: str = None
    ):
        """绘制 IC 时间序列"""
        try:
            import matplotlib.pyplot as plt
            import matplotlib.dates as mdates
        except ImportError:
            print("[警告] matplotlib 未安装")
            return

        fig, axes = plt.subplots(2, 1, figsize=(12, 8))

        # IC 柱状图
        ax1 = axes[0]
        colors = ['green' if ic > 0 else 'red' for ic in ic_series]
        ax1.bar(ic_series.index, ic_series, color=colors, alpha=0.7)
        ax1.axhline(y=0, color='black', linestyle='-', alpha=0.5)
        ax1.axhline(y=ic_series.mean(), color='blue', linestyle='--', alpha=0.7,
                   label=f'Mean={ic_series.mean():.4f}')
        ax1.set_title(f'{title} - IC Values', fontsize=12)
        ax1.set_ylabel('IC')
        ax1.legend()
        ax1.grid(True, alpha=0.3)

        # 累计 IC
        ax2 = axes[1]
        cum_ic = (1 + ic_series).cumprod() - 1
        ax2.plot(cum_ic.index, cum_ic * 100, color='purple', linewidth=2)
        ax2.axhline(y=0, color='black', linestyle='--', alpha=0.5)
        ax2.set_title(f'{title} - Cumulative IC', fontsize=12)
        ax2.set_xlabel('Date')
        ax2.set_ylabel('Cumulative Return (%)')
        ax2.grid(True, alpha=0.3)

        plt.tight_layout()

        if save_path:
            plt.savefig(save_path, dpi=150, bbox_inches='tight')
            print(f"[保存] IC图已保存: {save_path}")

        return fig

    @staticmethod
    def plot_ic_distribution(
        ic_series: pd.Series,
        title: str = 'IC Distribution',
        save_path: str = None
    ):
        """绘制 IC 分布"""
        try:
            import matplotlib.pyplot as plt
        except ImportError:
            print("[警告] matplotlib 未安装")
            return

        fig, ax = plt.subplots(figsize=(10, 6))

        # 直方图
        ax.hist(ic_series.dropna(), bins=30, color='steelblue',
               edgecolor='white', alpha=0.7)
        ax.axvline(x=0, color='red', linestyle='--', linewidth=2,
                  label='Zero')
        ax.axvline(x=ic_series.mean(), color='green', linestyle='--',
                  linewidth=2, label=f'Mean={ic_series.mean():.4f}')
        ax.axvline(x=ic_series.median(), color='orange', linestyle='--',
                  linewidth=2, label=f'Median={ic_series.median():.4f}')

        ax.set_title(f'{title} - Distribution', fontsize=12)
        ax.set_xlabel('IC')
        ax.set_ylabel('Frequency')
        ax.legend()
        ax.grid(True, alpha=0.3)

        plt.tight_layout()

        if save_path:
            plt.savefig(save_path, dpi=150, bbox_inches='tight')
            print(f"[保存] IC分布图已保存: {save_path}")

        return fig


if __name__ == "__main__":
    print("=" * 60)
    print("测试 FactorQuantileAnalysis")
    print("=" * 60)

    # 模拟数据
    np.random.seed(42)
    dates = pd.date_range('2023-01-01', '2024-03-19', freq='B')
    symbols = [f'symbol_{i:04d}' for i in range(100)]

    # 生成因子数据
    factor_data = pd.DataFrame(
        np.random.randn(len(dates), len(symbols)),
        index=dates,
        columns=symbols
    )

    # 生成收益数据（与因子部分相关）
    returns_data = pd.DataFrame(
        factor_data.values * 0.3 + np.random.randn(len(dates), len(symbols)) * 0.5,
        index=dates,
        columns=symbols
    )

    # 分层分析
    analyzer = FactorQuantileAnalysis(n_groups=5)
    results = analyzer.quantile_analysis(
        factor_data,
        returns_data,
        holding_period=20
    )

    print("\n各组收益统计:")
    for group, metrics in results['group_metrics'].items():
        print(f"  {group}: 日均={metrics['mean']*100:.4f}%, "
              f"夏普={metrics['sharpe']:.2f}, "
              f"胜率={metrics['win_rate']:.2%}")

    print(f"\n多空组合夏普: {results['metrics'].get('long_short_ir', 0):.2f}")
    print(f"Top-Bottom收益差: {results['metrics'].get('top_minus_bottom', 0)*100:.2f}%")

    # 生成报告
    report = analyzer.generate_quantile_report(results, 'Test Factor')
    print("\n" + "=" * 60)
    print(report)

    print("\n测试完成")