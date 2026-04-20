"""
回测报告生成器
生成增强回测报告，包含因子暴露度、归因分析等
"""
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
import json


class BacktestReport:
    """
    多因子回测报告生成器

    功能：
    - 生成标准回测摘要
    - 生成因子暴露度分析
    - 生成因子收益归因
    - 生成 IC 有效性回顾
    - 生成分层回测对比
    - 导出到 Excel/HTML
    """

    def __init__(self, results: Dict[str, Any], factor_report: Dict[str, Any] = None):
        """
        初始化报告生成器

        Args:
            results: 回测结果字典
            factor_report: 因子分析报告（可选）
        """
        self.results = results
        self.factor_report = factor_report or results.get('factor_report', {})

    def get_summary(self) -> Dict[str, Any]:
        """
        获取回测摘要

        Returns:
            摘要字典
        """
        return {
            '回测期间': f"{self.results.get('dates', {}).get('start', 'N/A')} ~ {self.results.get('dates', {}).get('end', 'N/A')}",
            '初始资金': self.results.get('initial_capital', 0),
            '最终权益': self.results.get('final_value', 0),
            '总收益率': f"{self.results.get('total_return', 0):.2%}",
            '年化收益率': f"{self.results.get('annual_return', 0):.2%}",
            '夏普比率': f"{self.results.get('sharpe_ratio', 0):.2f}",
            '最大回撤': f"{self.results.get('max_drawdown', 0):.2%}",
            '年化波动率': f"{self.results.get('volatility', 0):.2%}",
            '总交易次数': self.results.get('total_trades', 0),
            '买入次数': self.results.get('buy_trades', 0),
            '卖出次数': self.results.get('sell_trades', 0)
        }

    def get_equity_curve(self) -> pd.DataFrame:
        """
        获取权益曲线

        Returns:
            DataFrame with date, equity, drawdown
        """
        equity_curve = self.results.get('equity_curve', pd.DataFrame())

        if equity_curve.empty:
            return pd.DataFrame()

        df = equity_curve.copy()

        # 计算回撤
        if 'total_value' in df.columns:
            df['cummax'] = df['total_value'].cummax()
            df['drawdown'] = (df['total_value'] - df['cummax']) / df['cummax']
        elif 'equity' in df.columns:
            df['cummax'] = df['equity'].cummax()
            df['drawdown'] = (df['equity'] - df['cummax']) / df['cummax']

        return df

    def get_factor_weights_table(self) -> pd.DataFrame:
        """
        获取因子权重配置表

        Returns:
            DataFrame(columns=[因子, 基础权重, IC权重, 变化])
        """
        base_weights = self.factor_report.get('factor_weights', {})
        ic_weights = self.factor_report.get('ic_weights', {})

        if not base_weights:
            return pd.DataFrame()

        records = []
        for factor, base in base_weights.items():
            ic = ic_weights.get(factor, base)
            change = ic - base
            records.append({
                '因子': factor,
                '基础权重': f"{base:.2%}",
                'IC权重': f"{ic:.2%}",
                '变化': f"{change:+.2%}"
            })

        return pd.DataFrame(records)

    def get_factor_exposure_summary(self) -> pd.DataFrame:
        """
        获取因子暴露度摘要

        Returns:
            DataFrame with factor exposure statistics
        """
        exposure_summary = self.factor_report.get('exposure_summary')

        if exposure_summary is None:
            return pd.DataFrame()

        df = exposure_summary.copy()

        # 格式化
        for col in df.columns:
            df[col] = df[col].apply(lambda x: f"{x:.4f}" if pd.notna(x) else "N/A")

        return df

    def get_ic_validity_table(self) -> pd.DataFrame:
        """
        获取 IC 有效性判定表

        Returns:
            DataFrame with IC statistics and validity judgment
        """
        ic_report = self.factor_report.get('ic_validity_report', {})

        if not ic_report:
            return pd.DataFrame()

        validity_labels = {
            'strong': '强有效',
            'normal': '有效',
            'weak': '弱有效',
            'unstable': '不稳定',
            'invalid': '无效'
        }

        records = []
        for factor, data in ic_report.items():
            records.append({
                '因子': factor,
                'IC均值': f"{data.get('ic_mean', 0):.4f}",
                'IR': f"{data.get('ir', 0):.2f}",
                '有效性': validity_labels.get(data.get('validity', ''), data.get('validity', ''))
            })

        df = pd.DataFrame(records)

        # 按 IC 均值排序
        if 'IC均值' in df.columns:
            df = df.sort_values('IC均值', ascending=False)

        return df

    def get_attribution_table(self) -> pd.DataFrame:
        """
        获取收益归因表

        Returns:
            DataFrame with factor attribution
        """
        attribution = self.factor_report.get('attribution', {})

        if not attribution:
            return pd.DataFrame()

        records = []
        total = sum(abs(v) for v in attribution.values()) if attribution else 0

        for factor, corr in sorted(attribution.items(), key=lambda x: abs(x[1]), reverse=True):
            contribution = corr * 100 if not np.isnan(corr) else 0
            pct = abs(corr) / total * 100 if total > 0 else 0
            records.append({
                '因子': factor,
                '相关系数': f"{corr:.4f}" if not np.isnan(corr) else "N/A",
                '收益贡献': f"{contribution:.2f}%",
                '占比': f"{pct:.1f}%"
            })

        return pd.DataFrame(records)

    def get_trade_summary(self) -> pd.DataFrame:
        """
        获取交易汇总

        Returns:
            DataFrame with trade statistics
        """
        trades = self.results.get('trades', [])

        if not trades:
            return pd.DataFrame()

        # 转换为 DataFrame
        if isinstance(trades[0], dict):
            df = pd.DataFrame(trades)
        else:
            return pd.DataFrame()

        summary = {
            '总交易次数': len(df),
            '买入次数': len(df[df.get('side', df.get('direction', '')) == 'BUY']),
            '卖出次数': len(df[df.get('side', df.get('direction', '')) == 'SELL'])
        }

        return pd.DataFrame([summary])

    def generate_markdown_report(self) -> str:
        """
        生成 Markdown 格式的报告

        Returns:
            Markdown 字符串
        """
        lines = []

        # 标题
        lines.append("# 多因子策略回测报告\n")

        # 回测概况
        lines.append("## 一、回测概况\n")
        summary = self.get_summary()
        for key, value in summary.items():
            lines.append(f"| {key} | {value} |")
        lines.append("")

        # 因子权重
        lines.append("## 二、因子权重配置\n")
        weight_df = self.get_factor_weights_table()
        if not weight_df.empty:
            lines.append(weight_df.to_markdown(index=False))
        lines.append("")

        # IC 有效性
        lines.append("## 三、IC 有效性判定\n")
        ic_df = self.get_ic_validity_table()
        if not ic_df.empty:
            lines.append(ic_df.to_markdown(index=False))
        lines.append("")

        # 因子暴露度
        lines.append("## 四、因子暴露度摘要\n")
        exp_df = self.get_factor_exposure_summary()
        if not exp_df.empty:
            lines.append(exp_df.to_markdown(index=False))
        lines.append("")

        # 收益归因
        lines.append("## 五、收益归因\n")
        attr_df = self.get_attribution_table()
        if not attr_df.empty:
            lines.append(attr_df.to_markdown(index=False))
        lines.append("")

        return "\n".join(lines)

    def export_to_excel(self, path: str):
        """
        导出完整报告到 Excel

        Args:
            path: 保存路径
        """
        with pd.ExcelWriter(path, engine='openpyxl') as writer:
            # Sheet 1: 回测摘要
            summary_df = pd.DataFrame([self.get_summary()]).T
            summary_df.columns = ['值']
            summary_df.to_excel(writer, sheet_name='回测摘要')

            # Sheet 2: 因子权重
            weight_df = self.get_factor_weights_table()
            if not weight_df.empty:
                weight_df.to_excel(writer, sheet_name='因子权重', index=False)

            # Sheet 3: IC 有效性
            ic_df = self.get_ic_validity_table()
            if not ic_df.empty:
                ic_df.to_excel(writer, sheet_name='IC有效性', index=False)

            # Sheet 4: 暴露度摘要
            exp_df = self.get_factor_exposure_summary()
            if not exp_df.empty:
                exp_df.to_excel(writer, sheet_name='暴露度摘要', index=False)

            # Sheet 5: 收益归因
            attr_df = self.get_attribution_table()
            if not attr_df.empty:
                attr_df.to_excel(writer, sheet_name='收益归因', index=False)

            # Sheet 6: 权益曲线
            equity_df = self.get_equity_curve()
            if not equity_df.empty:
                equity_df.to_excel(writer, sheet_name='权益曲线', index=False)

        print(f"[导出] 报告已保存: {path}")

    def export_to_html(self, path: str):
        """
        导出报告到 HTML

        Args:
            path: 保存路径
        """
        md_content = self.generate_markdown_report()

        html = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>多因子策略回测报告</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 40px; }}
        h1 {{ color: #333; }}
        h2 {{ color: #666; border-bottom: 1px solid #ccc; padding-bottom: 10px; }}
        table {{ border-collapse: collapse; width: 100%; margin: 20px 0; }}
        th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
        th {{ background-color: #f5f5f5; }}
        tr:nth-child(even) {{ background-color: #fafafa; }}
    </style>
</head>
<body>
    <h1>多因子策略回测报告</h1>
    <p>生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
    {self._md_to_html(md_content)}
</body>
</html>
        """

        with open(path, 'w', encoding='utf-8') as f:
            f.write(html)

        print(f"[导出] HTML 报告已保存: {path}")

    def _md_to_html(self, md_content: str) -> str:
        """简单的 Markdown 到 HTML 转换"""
        import re

        # 标题
        md_content = re.sub(r'^# (.+)$', r'<h1>\1</h1>', md_content, flags=re.MULTILINE)
        md_content = re.sub(r'^## (.+)$', r'<h2>\1</h2>', md_content, flags=re.MULTILINE)
        md_content = re.sub(r'^### (.+)$', r'<h3>\1</h3>', md_content, flags=re.MULTILINE)

        # 表格
        lines = md_content.split('\n')
        in_table = False
        html_parts = []
        table_rows = []

        for line in lines:
            if '|' in line and line.strip().startswith('|'):
                if not in_table:
                    in_table = True
                    table_rows = []
                table_rows.append(line)
            else:
                if in_table and table_rows:
                    # 处理表格
                    html_parts.append(self._render_table(table_rows))
                    table_rows = []
                    in_table = False
                html_parts.append(line)

        if table_rows:
            html_parts.append(self._render_table(table_rows))

        return '\n'.join(html_parts)

    def _render_table(self, rows: List[str]) -> str:
        """渲染 HTML 表格"""
        if len(rows) < 2:
            return ''

        html = ['<table>']

        for i, row in enumerate(rows):
            cells = [c.strip() for c in row.split('|') if c.strip()]
            if i == 0:
                html.append('<thead><tr>')
                for cell in cells:
                    html.append(f'<th>{cell}</th>')
                html.append('</tr></thead><tbody>')
            else:
                html.append('<tr>')
                for cell in cells:
                    html.append(f'<td>{cell}</td>')
                html.append('</tr>')

        html.append('</tbody></table>')
        return '\n'.join(html)


class QuantileReturnsAnalyzer:
    """
    分层收益分析器
    分析各因子五分位数组合的收益差异
    """

    def __init__(self, n_groups: int = 5):
        self.n_groups = n_groups

    def analyze(
        self,
        factor_data: pd.DataFrame,
        returns_data: pd.DataFrame,
        factor_name: str
    ) -> Dict[str, Any]:
        """
        分析分层收益

        Args:
            factor_data: 因子值
            returns_data: 收益率
            factor_name: 因子名称

        Returns:
            分析结果字典
        """
        results = {
            'factor': factor_name,
            'group_returns': {},
            'long_short_return': None,
            'metrics': {}
        }

        for date in factor_data.index:
            if date not in returns_data.index:
                continue

            # 获取当日横截面数据
            factor_vals = factor_data.loc[date].dropna()
            returns_vals = returns_data.loc[date].dropna()

            common = factor_vals.index.intersection(returns_vals.index)

            if len(common) < self.n_groups * 10:
                continue

            # 分组
            try:
                groups = pd.qcut(factor_vals[common], q=self.n_groups, labels=False, duplicates='drop')
            except:
                continue

            # 计算各组收益
            for g in range(self.n_groups):
                group_symbols = groups[groups == g].index
                if len(group_symbols) > 0:
                    group_returns = returns_vals[group_symbols].mean()
                    results['group_returns'].setdefault(g, []).append(group_returns)

        # 计算平均收益
        if results['group_returns']:
            avg_returns = {}
            for g, rets in results['group_returns'].items():
                avg_returns[g] = np.mean(rets) if rets else 0

            results['group_returns'] = avg_returns

            # 多空组合收益
            if 0 in avg_returns and self.n_groups - 1 in avg_returns:
                results['long_short_return'] = avg_returns[0] - avg_returns[self.n_groups - 1]

            # 计算指标
            returns_series = list(avg_returns.values())
            if len(returns_series) == self.n_groups:
                results['metrics'] = {
                    'top_minus_bottom': avg_returns[0] - avg_returns[self.n_groups - 1],
                    'top_group_return': avg_returns.get(0, 0),
                    'bottom_group_return': avg_returns.get(self.n_groups - 1, 0),
                    'spread_std': np.std(returns_series)
                }

        return results

    def generate_report(
        self,
        analysis_results: Dict[str, Any]
    ) -> pd.DataFrame:
        """
        生成分层分析报告

        Args:
            analysis_results: 分层分析结果

        Returns:
            DataFrame with group returns
        """
        group_returns = analysis_results.get('group_returns', {})

        if not group_returns:
            return pd.DataFrame()

        records = []
        for g, ret in group_returns.items():
            records.append({
                '组别': f'G{int(g)+1}',
                '因子值范围': '高' if g == 0 else ('低' if g == self.n_groups - 1 else '中'),
                '平均收益': f"{ret:.4f}" if isinstance(ret, float) else "N/A"
            })

        df = pd.DataFrame(records)

        return df


if __name__ == "__main__":
    # 测试
    import numpy as np
    from datetime import datetime

    # 模拟回测结果
    results = {
        'dates': {'start': '2023-01-01', 'end': '2023-12-31'},
        'initial_capital': 1000000,
        'final_value': 1234567,
        'total_return': 0.2346,
        'annual_return': 0.1832,
        'sharpe_ratio': 1.45,
        'max_drawdown': -0.1234,
        'volatility': 0.1823,
        'total_trades': 50,
        'buy_trades': 25,
        'sell_trades': 25,
        'equity_curve': pd.DataFrame({
            'date': pd.date_range('2023-01-01', periods=100, freq='B'),
            'total_value': 1000000 * (1 + np.random.randn(100).cumsum() * 0.01)
        })
    }

    factor_report = {
        'factor_weights': {'roe': 0.25, 'pe': 0.15, 'momentum_20': 0.30, 'revenue_growth': 0.20, 'debt_ratio': 0.10},
        'ic_weights': {'roe': 0.35, 'pe': 0.00, 'momentum_20': 0.35, 'revenue_growth': 0.15, 'debt_ratio': 0.15},
        'ic_validity_report': {
            'roe': {'ic_mean': 0.052, 'ir': 0.68, 'validity': 'strong'},
            'pe': {'ic_mean': -0.005, 'ir': -0.06, 'validity': 'invalid'},
            'momentum_20': {'ic_mean': 0.031, 'ir': 0.42, 'validity': 'normal'},
            'revenue_growth': {'ic_mean': 0.018, 'ir': 0.25, 'validity': 'weak'},
            'debt_ratio': {'ic_mean': 0.008, 'ir': 0.12, 'validity': 'unstable'}
        },
        'exposure_summary': pd.DataFrame({
            '平均暴露度': [0.65, 0.42, 0.38, 0.25, 0.15],
            '暴露度标准差': [0.15, 0.22, 0.18, 0.12, 0.08]
        }, index=['roe', 'momentum_20', 'revenue_growth', 'debt_ratio', 'pe']),
        'attribution': {
            'roe': 0.45,
            'momentum_20': 0.32,
            'revenue_growth': 0.15,
            'debt_ratio': 0.05,
            'pe': 0.03
        }
    }

    # 生成报告
    report = BacktestReport(results, factor_report)

    print("回测摘要:")
    for k, v in report.get_summary().items():
        print(f"  {k}: {v}")

    print("\n因子权重表:")
    print(report.get_factor_weights_table())

    print("\nIC有效性表:")
    print(report.get_ic_validity_table())
