"""
因子暴露度跟踪器
跟踪组合在各因子上的暴露度，计算因子收益贡献
"""
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Any, Tuple
from collections import defaultdict
from datetime import datetime


class FactorExposureTracker:
    """
    因子暴露度跟踪器

    功能：
    - 每日记录组合因子暴露度
    - 计算因子收益率
    - 归因分析因子贡献
    """

    def __init__(
        self,
        factor_names: List[str],
        db_path: str = None
    ):
        """
        初始化

        Args:
            factor_names: 要跟踪的因子列表
            db_path: 数据库路径（可选，用于持久化）
        """
        self.factor_names = factor_names
        self.db_path = db_path

        # 暴露度记录
        self.exposure_history: List[Dict] = []

        # 每日因子暴露度 DataFrame
        self.exposure_df: pd.DataFrame = None

        # 因子收益 DataFrame
        self.factor_returns_df: pd.DataFrame = None

        # 初始化
        self._init_storage()

    def _init_storage(self):
        """初始化存储"""
        self.exposure_records = []
        self.factor_returns_records = []

    def record_exposure(
        self,
        date: Any,
        positions: Dict[str, float],  # {symbol: market_value}
        factor_values: Dict[str, Dict[str, float]],  # {symbol: {factor: value}}
        percentile_scores: Dict[str, Dict[str, float]] = None  # {symbol: {factor: percentile}}
    ):
        """
        记录每日暴露度

        Args:
            date: 日期
            positions: 持仓市值 {symbol: market_value}
            factor_values: 因子值 {symbol: {factor: value}}
            percentile_scores: 百分位得分（可选）
        """
        if not positions:
            return

        total_value = sum(positions.values())
        if total_value <= 0:
            return

        # 计算各因子暴露度
        for factor in self.factor_names:
            weighted_exposure = 0.0

            for symbol, value in positions.items():
                weight = value / total_value  # 市值权重

                # 使用百分位得分或原始因子值
                if percentile_scores and symbol in percentile_scores:
                    factor_score = percentile_scores[symbol].get(factor, 50.0) / 100.0
                elif symbol in factor_values and factor in factor_values[symbol]:
                    # 原始因子值标准化
                    raw_value = factor_values[symbol][factor]
                    # 简单标准化：假设均值 0，标准差 1
                    factor_score = raw_value / 10.0  # 缩放到 0-1 范围
                else:
                    factor_score = 0.5  # 默认中性

                weighted_exposure += weight * factor_score

            # 记录
            self.exposure_records.append({
                'date': date,
                'factor': factor,
                'exposure': weighted_exposure,
                'portfolio_value': total_value
            })

    def calculate_exposure_summary(self) -> pd.DataFrame:
        """
        计算暴露度摘要

        Returns:
            DataFrame(columns=[因子, 平均暴露度, 暴露度标准差, 最大暴露度, 最小暴露度])
        """
        if not self.exposure_records:
            return pd.DataFrame()

        df = pd.DataFrame(self.exposure_records)

        summary = df.groupby('factor')['exposure'].agg([
            ('平均暴露度', 'mean'),
            ('暴露度标准差', 'std'),
            ('最大暴露度', 'max'),
            ('最小暴露度', 'min')
        ]).round(4)

        return summary

    def calculate_factor_returns(
        self,
        returns_data: pd.DataFrame,  # index=date, columns=symbol, values=returns
        factor_data: pd.DataFrame  # index=date, columns=symbol, values=factor_value
    ) -> pd.DataFrame:
        """
        计算因子收益率（横截面回归法）

        使用横截面回归：return_i = alpha + beta_f * factor_i + epsilon_i
        beta_f 即为因子 f 的收益率

        Args:
            returns_data: 收益率数据
            factor_data: 因子数据

        Returns:
            DataFrame(index=date, columns=factor_names, values=factor_return)
        """
        factor_returns = {}

        for date in returns_data.index:
            date_str = date if isinstance(date, str) else pd.to_datetime(date).strftime('%Y-%m-%d')

            # 获取当日横截面数据
            if date not in returns_data.index:
                continue

            returns_row = returns_data.loc[date].dropna()
            factor_row = factor_data.loc[date] if date in factor_data.index else None

            if factor_row is None or len(returns_row) < 10:
                continue

            # 对每个因子进行回归
            for factor in self.factor_names:
                if factor not in factor_row.index:
                    continue

                factor_values = factor_row[factor].dropna()
                common_symbols = returns_row.index.intersection(factor_values.index)

                if len(common_symbols) < 10:
                    continue

                # 标准化因子值
                fv = factor_values[common_symbols]
                fv_std = (fv - fv.mean()) / (fv.std() + 1e-8)

                # 计算因子收益率（因子值与收益率的相关系数）
                r = returns_row[common_symbols]
                corr = r.corr(fv_std)

                # 使用相关系数作为因子收益率的近似
                factor_returns.setdefault(factor, []).append({
                    'date': date_str,
                    'factor_return': corr
                })

        # 转换为 DataFrame
        result_frames = {}
        for factor, records in factor_returns.items():
            result_frames[factor] = pd.DataFrame(records).set_index('date')['factor_return']

        if result_frames:
            self.factor_returns_df = pd.DataFrame(result_frames)
            return self.factor_returns_df

        return pd.DataFrame()

    def calculate_exposure_returns(
        self,
        portfolio_returns: pd.Series  # index=date, values=daily_return
    ) -> pd.DataFrame:
        """
        计算暴露度调整后的因子收益贡献

        attribution = exposure_{t-1} * factor_return_t

        Args:
            portfolio_returns: 组合收益率

        Returns:
            DataFrame(index=date, columns=[factor, attribution])
        """
        if self.exposure_df is None or self.factor_returns_df is None:
            return pd.DataFrame()

        # 对齐日期
        common_dates = portfolio_returns.index.intersection(self.exposure_df.index)
        common_dates = common_dates.intersection(self.factor_returns_df.index)

        if len(common_dates) == 0:
            return pd.DataFrame()

        # 计算归因
        attribution_records = []

        for i, date in enumerate(common_dates):
            if i == 0:
                continue

            prev_date = common_dates[i - 1]
            curr_date = date

            # 获取前一期暴露度
            prev_exposure = self.exposure_df.loc[prev_date] if prev_date in self.exposure_df.index else None
            # 获取本期因子收益
            curr_returns = self.factor_returns_df.loc[curr_date] if curr_date in self.factor_returns_df.index else None

            if prev_exposure is None or curr_returns is None:
                continue

            for factor in self.factor_names:
                exposure = prev_exposure.get(factor, 0.0)
                factor_ret = curr_returns.get(factor, 0.0)
                attr = exposure * factor_ret

                attribution_records.append({
                    'date': curr_date,
                    'factor': factor,
                    'factor_return': factor_ret,
                    'exposure': exposure,
                    'attribution': attr
                })

        return pd.DataFrame(attribution_records)

    def attribute_returns(
        self,
        portfolio_returns: pd.Series,
        factor_returns: pd.DataFrame = None,
        method: str = 'regression'
    ) -> Dict[str, float]:
        """
        收益归因

        Args:
            portfolio_returns: 组合收益率
            factor_returns: 因子收益率（可选）
            method: 归因方法 ('regression', 'exposure')

        Returns:
            {factor_name: contribution}
        """
        if method == 'exposure' and factor_returns is not None:
            # 暴露度加权法
            attr_df = self.calculate_exposure_returns(portfolio_returns)
            if attr_df.empty:
                return {}

            attribution = attr_df.groupby('factor')['attribution'].sum()
            total_attribution = attribution.sum()

            # 归一化
            if total_attribution != 0:
                normalized = (attribution / total_attribution * portfolio_returns.sum()).to_dict()
            else:
                normalized = attribution.to_dict()

            return normalized

        elif method == 'regression':
            # 回归法
            if factor_returns is None or factor_returns.empty:
                return {}

            # 计算各因子对组合收益的解释度
            explained = {}
            total_explained = 0.0

            for factor in self.factor_names:
                if factor not in factor_returns.columns:
                    continue

                # 计算因子收益与组合收益的相关系数
                corr = portfolio_returns.corr(factor_returns[factor].dropna())

                # 因子收益标准差
                factor_std = factor_returns[factor].std()

                # 组合收益标准差
                portfolio_std = portfolio_returns.std()

                # 贡献度 = 相关系数 * 因子波动率 / 组合波动率
                if portfolio_std > 0:
                    contribution = corr * factor_std / portfolio_std
                    explained[factor] = contribution
                    total_explained += abs(contribution)

            # 归一化
            if total_explained > 0:
                for factor in explained:
                    explained[factor] = explained[factor] / total_explained * portfolio_returns.sum()

            return explained

        return {}

    def get_exposure_timeseries(self, factor: str = None) -> pd.DataFrame:
        """
        获取暴露度时序数据

        Args:
            factor: 指定因子（None 表示所有因子）

        Returns:
            DataFrame(index=date, columns=[factors])
        """
        if not self.exposure_records:
            return pd.DataFrame()

        df = pd.DataFrame(self.exposure_records)

        if factor:
            df = df[df['factor'] == factor]

        pivot_df = df.pivot(index='date', columns='factor', values='exposure')
        self.exposure_df = pivot_df

        return pivot_df

    def get_exposure_correlation(self) -> pd.DataFrame:
        """
        获取因子暴露度之间的相关性

        用于检查因子是否过于集中
        """
        if self.exposure_df is None:
            self.get_exposure_timeseries()

        if self.exposure_df is None or self.exposure_df.empty:
            return pd.DataFrame()

        return self.exposure_df.corr().round(3)

    def save_to_db(self, conn=None):
        """
        保存到数据库

        Args:
            conn: 数据库连接（可选）
        """
        if not self.db_path:
            return

        if conn is None:
            import sqlite3
            conn = sqlite3.connect(self.db_path)

        # 保存暴露度记录
        if self.exposure_records:
            df = pd.DataFrame(self.exposure_records)
            df.to_sql('factor_exposure', conn, if_exists='append', index=False)

        if conn is not None and self.db_path:
            conn.close()

    def load_from_db(self, conn=None, start_date: str = None, end_date: str = None):
        """
        从数据库加载

        Args:
            conn: 数据库连接
            start_date: 开始日期
            end_date: 结束日期
        """
        if not self.db_path:
            return

        if conn is None:
            import sqlite3
            conn = sqlite3.connect(self.db_path)

        # 加载暴露度记录
        query = "SELECT * FROM factor_exposure WHERE 1=1"
        params = []

        if start_date:
            query += " AND date >= ?"
            params.append(start_date)
        if end_date:
            query += " AND date <= ?"
            params.append(end_date)

        df = pd.read_sql_query(query, conn, params=params)

        if not df.empty:
            self.exposure_records = df.to_dict('records')

        if conn is not None and self.db_path:
            conn.close()


class ExposureVisualizer:
    """
    暴露度可视化工具
    """

    @staticmethod
    def plot_exposure_timeseries(
        exposure_df: pd.DataFrame,
        factor: str = None,
        figsize: Tuple[int, int] = (12, 6)
    ):
        """
        绘制暴露度时序图

        Args:
            exposure_df: 暴露度 DataFrame
            factor: 指定因子
            figsize: 图形大小
        """
        import matplotlib.pyplot as plt

        if exposure_df.empty:
            return None

        fig, ax = plt.subplots(figsize=figsize)

        if factor:
            cols = [factor] if factor in exposure_df.columns else []
        else:
            cols = exposure_df.columns[:5]  # 最多显示 5 个因子

        for col in cols:
            ax.plot(exposure_df.index, exposure_df[col], label=col, linewidth=1.5)

        ax.set_xlabel('Date')
        ax.set_ylabel('Exposure')
        ax.set_title(f'Factor Exposure - {factor or "All Factors"}')
        ax.legend(loc='best')
        ax.grid(True, alpha=0.3)

        plt.tight_layout()
        return fig

    @staticmethod
    def plot_exposure_heatmap(
        exposure_df: pd.DataFrame,
        figsize: Tuple[int, int] = (12, 8)
    ):
        """
        绘制暴露度热力图

        Args:
            exposure_df: 暴露度 DataFrame (dates x factors)
            figsize: 图形大小
        """
        import matplotlib.pyplot as plt

        if exposure_df.empty:
            return None

        # 按月聚合
        exposure_df.index = pd.to_datetime(exposure_df.index)
        monthly_df = exposure_df.resample('M').mean()

        fig, ax = plt.subplots(figsize=figsize)

        im = ax.imshow(monthly_df.T.values, aspect='auto', cmap='RdYlBu_r')

        ax.set_yticks(range(len(monthly_df.columns)))
        ax.set_yticklabels(monthly_df.columns)
        ax.set_xticks(range(0, len(monthly_df.index), max(1, len(monthly_df.index) // 12)))
        ax.set_xticklabels([d.strftime('%Y-%m') for d in monthly_df.index[::max(1, len(monthly_df.index) // 12)]], rotation=45)

        ax.set_xlabel('Month')
        ax.set_ylabel('Factor')
        ax.set_title('Factor Exposure Heatmap')

        plt.colorbar(im, ax=ax, label='Exposure')
        plt.tight_layout()

        return fig


if __name__ == "__main__":
    # 测试
    import numpy as np
    from datetime import datetime, timedelta

    # 创建测试数据
    dates = pd.date_range('2023-01-01', '2023-12-31', freq='B')
    symbols = [f'{i:06d}.SH' for i in range(50)]

    # 因子暴露度数据
    np.random.seed(42)
    factor_data = pd.DataFrame(
        np.random.randn(len(dates), len(symbols)) * 0.1,
        index=dates,
        columns=symbols
    )

    # 持仓市值
    positions = {s: 1000000 / len(symbols) for s in symbols}

    # 跟踪器
    tracker = FactorExposureTracker(['roe', 'pe', 'momentum_20'])

    # 记录暴露度
    for date in dates[:20]:
        tracker.record_exposure(
            date=date,
            positions=positions,
            factor_values={s: {
                'roe': np.random.randn() * 5 + 10,
                'pe': np.random.randn() * 5 + 20,
                'momentum_20': np.random.randn() * 0.1
            } for s in symbols}
        )

    # 计算摘要
    summary = tracker.calculate_exposure_summary()
    print("暴露度摘要:")
    print(summary)

    # 获取时序
    ts = tracker.get_exposure_timeseries()
    print(f"\n暴露度时序: {ts.shape}")
