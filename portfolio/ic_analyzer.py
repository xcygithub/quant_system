"""
因子 IC 分析模块
计算因子 IC（信息系数）和 IR（信息比率）
"""
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple, Union
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

try:
    from scipy import stats
    _has_scipy = True
except ImportError:
    stats = None
    _has_scipy = False

try:
    from data import DataManager
except ImportError:
    from quant_system.data import DataManager
from config import DATABASE_PATH


class ICAnalyzer:
    """
    因子 IC 分析器

    IC (Information Coefficient) = 因子的排序与下期收益的相关系数
    IR (Information Ratio) = IC均值 / IC标准差

    功能：
    - 计算单因子 IC（Pearson / Spearman）
    - 计算因子 IR
    - IC 时间序列分析
    - 因子有效性判断
    """

    def __init__(self, db_path: str = None):
        """
        初始化 IC 分析器

        Args:
            db_path: 数据库路径
        """
        self.db_path = db_path or str(DATABASE_PATH)
        self.dm = DataManager(db_path=self.db_path)

    def calculate_ic(
        self,
        factor_data: Union[pd.Series, np.ndarray],
        forward_returns: Union[pd.Series, np.ndarray],
        method: str = 'spearman'
    ) -> float:
        """
        计算因子 IC

        IC = 因子的排序与下期收益的相关系数

        Args:
            factor_data: 因子值（横截面）
            forward_returns: 未来收益率
            method: 相关系数方法 ('spearman' / 'pearson')

        Returns:
            IC 值 (-1 ~ 1)
        """
        # 转换为 numpy 数组
        if isinstance(factor_data, pd.Series):
            factor_data = factor_data.values
        if isinstance(forward_returns, pd.Series):
            forward_returns = forward_returns.values

        # 去除 NaN
        mask = ~(np.isnan(factor_data) | np.isnan(forward_returns))
        factor_data = factor_data[mask]
        forward_returns = forward_returns[mask]

        if len(factor_data) < 10:
            return 0.0

        try:
            if method == 'spearman' and _has_scipy:
                ic, _ = stats.spearmanr(factor_data, forward_returns)
            elif method == 'pearson' and _has_scipy:
                ic, _ = stats.pearsonr(factor_data, forward_returns)
            else:
                # Fallback using pandas
                if method == 'spearman':
                    ic = pd.Series(factor_data).corr(pd.Series(forward_returns), method='spearman')
                else:
                    ic = pd.Series(factor_data).corr(pd.Series(forward_returns), method='pearson')

            if np.isnan(ic):
                return 0.0

            return float(ic)

        except Exception as e:
            return 0.0

    def calculate_ic_series(
        self,
        factor_name: str,
        start_date: str,
        end_date: str,
        factor_data_dict: Dict[str, pd.DataFrame] = None,
        returns_data_dict: Dict[str, pd.DataFrame] = None,
        window: int = 20,
        method: str = 'spearman'
    ) -> pd.Series:
        """
        计算 IC 时间序列

        Args:
            factor_name: 因子名称
            start_date: 开始日期
            end_date: 结束日期
            factor_data_dict: {date: {symbol: factor_value}} 因子数据
            returns_data_dict: {date: {symbol: return}} 收益数据
            window: 滚动窗口大小
            method: 相关系数方法

        Returns:
            Series(index=date, values=ic)
        """
        ic_series = pd.Series(dtype=float)

        # 生成日期序列（交易日）
        dates = pd.date_range(start=start_date, end=end_date, freq='B')  # 工作日

        for i, date in enumerate(dates):
            if i < window:
                continue  # 需要足够的历史数据

            # 获取窗口内的因子和收益数据
            window_dates = dates[i-window:i]

            ic_values = []
            for d in window_dates:
                d_str = d.strftime('%Y-%m-%d')

                # 从数据字典获取
                if factor_data_dict and d_str in factor_data_dict:
                    factors = factor_data_dict[d_str]
                else:
                    continue

                if returns_data_dict and d_str in returns_data_dict:
                    returns = returns_data_dict[d_str]
                else:
                    continue

                # 获取该日期的因子值和收益
                common_symbols = set(factors.keys()) & set(returns.keys())
                if len(common_symbols) < 10:
                    continue

                factor_vals = [factors[s] for s in common_symbols if not np.isnan(factors.get(s, np.nan))]
                return_vals = [returns[s] for s in common_symbols if not np.isnan(returns.get(s, np.nan))]

                if len(factor_vals) >= 10:
                    ic = self.calculate_ic(factor_vals, return_vals, method)
                    ic_values.append(ic)

            if ic_values:
                ic_series[date] = np.mean(ic_values)

        return ic_series

    def calculate_ir(
        self,
        ic_series: Union[pd.Series, np.ndarray]
    ) -> float:
        """
        计算 IR (Information Ratio)

        IR = mean(IC) / std(IC)

        Args:
            ic_series: IC 时间序列

        Returns:
            IR 值
        """
        if isinstance(ic_series, pd.Series):
            ic_series = ic_series.values

        ic_series = ic_series[~np.isnan(ic_series)]

        if len(ic_series) < 3:
            return 0.0

        ic_mean = np.mean(ic_series)
        ic_std = np.std(ic_series)

        if ic_std == 0:
            return 0.0

        return float(ic_mean / ic_std)

    def calculate_factor_ic_from_panel(
        self,
        factor_panel: pd.DataFrame,
        returns_panel: pd.DataFrame,
        method: str = 'spearman'
    ) -> Dict[str, float]:
        """
        从因子面板和收益面板计算各因子的 IC

        Args:
            factor_panel: DataFrame(index=date, columns=symbol) 因子值
            returns_panel: DataFrame(index=date, columns=symbol) 收益率
            method: 相关系数方法

        Returns:
            {因子名: ic值}
        """
        if factor_panel.empty or returns_panel.empty:
            return {}

        results = {}

        for col in factor_panel.columns:
            if col in ['symbol', 'date', 'trade_date']:
                continue

            ic_values = []

            # 按日期计算横截面 IC
            for date in factor_panel.index:
                if date not in returns_panel.index:
                    continue

                factor_col = factor_panel.loc[date]
                return_col = returns_panel.loc[date]

                # 去除 NaN
                mask = ~(factor_col.isna() | return_col.isna())
                factor_vals = factor_col[mask].values
                return_vals = return_col[mask].values

                if len(factor_vals) >= 10:
                    ic = self.calculate_ic(factor_vals, return_vals, method)
                    ic_values.append(ic)

            if ic_values:
                results[col] = {
                    'ic_mean': np.mean(ic_values),
                    'ic_std': np.std(ic_values),
                    'ic_ir': np.mean(ic_values) / np.std(ic_values) if np.std(ic_values) > 0 else 0,
                    'ic_positive_ratio': np.mean([1 if ic > 0 else 0 for ic in ic_values]),
                    'sample_count': len(ic_values)
                }

        return results

    def generate_ic_report(
        self,
        factor_names: List[str],
        start_date: str,
        end_date: str,
        factor_data: Dict[str, pd.DataFrame] = None,
        returns_data: Dict[str, pd.DataFrame] = None,
        output_path: str = None,
        method: str = 'spearman'
    ) -> Dict:
        """
        生成 IC 分析报告

        Args:
            factor_names: 要分析的因子列表
            start_date: 开始日期
            end_date: 结束日期
            factor_data: {因子名: DataFrame(index=date, columns=symbol)}
            returns_data: {date: {symbol: return}}
            output_path: 结果保存路径
            method: 相关系数方法

        Returns:
            IC 分析报告字典
        """
        report = {
            'factor_stats': {},
            'best_factor': None,
            'worst_factor': None,
            'recommendations': [],
            'analysis_period': {'start': start_date, 'end': end_date}
        }

        if factor_data is None:
            factor_data = {}

        # 计算每个因子的 IC
        for factor_name in factor_names:
            if factor_name not in factor_data or factor_data[factor_name].empty:
                continue

            factor_panel = factor_data[factor_name]

            # 计算 IC 统计
            ic_values = []
            for date in factor_panel.index:
                if date not in returns_data:
                    continue

                factor_col = factor_panel.loc[date]
                return_col = returns_data[date]

                mask = ~(factor_col.isna() | return_col.isna())
                factor_vals = factor_col[mask].values
                return_vals = return_col[mask].values

                if len(factor_vals) >= 10:
                    ic = self.calculate_ic(factor_vals, return_vals, method)
                    ic_values.append(ic)

            if ic_values:
                ic_mean = np.mean(ic_values)
                ic_std = np.std(ic_values)
                ir = ic_mean / ic_std if ic_std > 0 else 0
                positive_ratio = np.mean([1 if ic > 0 else 0 for ic in ic_values])

                report['factor_stats'][factor_name] = {
                    'ic_mean': ic_mean,
                    'ic_std': ic_std,
                    'ir': ir,
                    'ic_positive_ratio': positive_ratio,
                    'sample_count': len(ic_values)
                }

        # 找出最佳和最差因子
        if report['factor_stats']:
            valid_factors = {k: v['ir'] for k, v in report['factor_stats'].items() if v['ir'] > 0}

            if valid_factors:
                report['best_factor'] = max(valid_factors, key=valid_factors.get)
                report['worst_factor'] = min(valid_factors, key=valid_factors.get)

            # 生成建议
            for factor, stats in report['factor_stats'].items():
                ir = stats['ir']
                ic_mean = stats['ic_mean']

                if ir > 0.5 and ic_mean > 0.03:
                    report['recommendations'].append({
                        'factor': factor,
                        'level': 'strong',
                        'suggestion': f'因子 {factor} IR={ir:.2f}，强有效，建议高权重'
                    })
                elif ir > 0.3 and ic_mean > 0.02:
                    report['recommendations'].append({
                        'factor': factor,
                        'level': 'moderate',
                        'suggestion': f'因子 {factor} IR={ir:.2f}，有效，建议正常权重'
                    })
                elif ir > 0.2 and ic_mean > 0.01:
                    report['recommendations'].append({
                        'factor': factor,
                        'level': 'weak',
                        'suggestion': f'因子 {factor} IR={ir:.2f}，弱有效，可观察使用'
                    })
                else:
                    report['recommendations'].append({
                        'factor': factor,
                        'level': 'invalid',
                        'suggestion': f'因子 {factor} IR={ir:.2f}，无效，不建议使用'
                    })

        # 保存报告
        if output_path:
            import json
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(report, f, ensure_ascii=False, indent=2, default=str)

        return report

    def save_ic_statistics(
        self,
        ic_stats: Dict[str, Dict],
        trade_date: str = None
    ) -> int:
        """
        保存 IC 统计到数据库

        Args:
            ic_stats: {因子名: {ic_mean, ic_std, ir, ...}}
            trade_date: 日期

        Returns:
            保存记录数
        """
        if trade_date is None:
            trade_date = datetime.now().strftime('%Y-%m-%d')

        conn = self.dm.get_db_connection()
        cursor = conn.cursor()

        records = 0
        for factor_name, stats in ic_stats.items():
            try:
                cursor.execute('''
                    INSERT OR REPLACE INTO ic_statistics
                    (factor_name, ic_mean, ic_std, ir, ic_positive_ratio, latest_ic, update_date)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (
                    factor_name,
                    stats.get('ic_mean', 0),
                    stats.get('ic_std', 0),
                    stats.get('ir', 0),
                    stats.get('ic_positive_ratio', 0),
                    stats.get('ic_mean', 0),  # 最新 IC
                    trade_date
                ))
                records += 1
            except Exception as e:
                continue

        conn.commit()
        return records

    def get_ic_statistics(
        self,
        factor_names: List[str] = None
    ) -> pd.DataFrame:
        """
        从数据库获取 IC 统计

        Returns:
            DataFrame
        """
        conn = self.dm.get_db_connection()

        query = 'SELECT * FROM ic_statistics WHERE 1=1'
        params = []

        if factor_names:
            placeholders = ','.join(['?' for _ in factor_names])
            query += f' AND factor_name IN ({placeholders})'
            params.extend(factor_names)

        try:
            df = pd.read_sql_query(query, conn, params=params)
        except Exception as e:
            df = pd.DataFrame()

        conn.close()
        return df

    def close(self):
        """关闭连接"""
        try:
            self.dm.close()
        except:
            pass

    def __del__(self):
        try:
            self.close()
        except:
            pass


# ========== 便捷函数 ==========

def calculate_factor_ic(
    factor_values: List[float],
    returns: List[float],
    method: str = 'spearman'
) -> float:
    """
    计算单个截面的 IC

    Args:
        factor_values: 因子值列表
        returns: 收益率列表
        method: 相关系数方法

    Returns:
        IC 值
    """
    analyzer = ICAnalyzer()
    ic = analyzer.calculate_ic(factor_values, returns, method)
    analyzer.close()
    return ic


def get_ic_report(
    factor_names: List[str],
    start_date: str,
    end_date: str
) -> Dict:
    """
    获取 IC 分析报告

    Args:
        factor_names: 因子列表
        start_date: 开始日期
        end_date: 结束日期

    Returns:
        IC 报告
    """
    analyzer = ICAnalyzer()
    report = analyzer.generate_ic_report(factor_names, start_date, end_date)
    analyzer.close()
    return report


if __name__ == "__main__":
    print("=" * 60)
    print("测试 ICAnalyzer")
    print("=" * 60)

    analyzer = ICAnalyzer()

    # 模拟数据测试
    np.random.seed(42)
    n = 100

    # 模拟因子值（与收益正相关）
    factor_data = np.random.randn(n) + np.random.randn(n) * 0.5
    returns = factor_data * 0.3 + np.random.randn(n) * 0.5

    ic_spearman = analyzer.calculate_ic(factor_data, returns, 'spearman')
    ic_pearson = analyzer.calculate_ic(factor_data, returns, 'pearson')

    print(f"Spearman IC: {ic_spearman:.4f}")
    print(f"Pearson IC: {ic_pearson:.4f}")

    # 模拟 IC 时间序列
    dates = pd.date_range('2023-01-01', '2024-03-19', freq='B')
    ic_series = pd.Series(np.random.randn(len(dates)) * 0.1 + 0.05, index=dates)

    ir = analyzer.calculate_ir(ic_series)
    print(f"\n模拟 IR: {ir:.4f}")
    print(f"IC Mean: {ic_series.mean():.4f}")
    print(f"IC Std: {ic_series.std():.4f}")
    print(f"IC > 0 Ratio: {(ic_series > 0).mean():.2%}")

    analyzer.close()
    print("\n测试完成")