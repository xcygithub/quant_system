"""
因子预处理器模块
负责因子的缺失值处理、异常值处理、标准化、中性化
"""
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
import warnings
warnings.filterwarnings('ignore')


class FactorPreprocessor:
    """
    因子预处理器

    负责因子数据的预处理，包括：
    1. 缺失值处理
    2. 异常值处理（Winsorization缩尾）
    3. 标准化（Z-score / Rank / MinMax）
    4. 中性化（行业/市值）
    """

    def __init__(self, method: str = 'zscore'):
        """
        初始化预处理器

        Args:
            method: 标准化方法
                - 'zscore': Z-score标准化 (x-mean)/std
                - 'rank': 排序标准化 0-1
                - 'minmax': MinMax缩放到0-1
                - 'mad': 中位数绝对偏差标准化
        """
        self.method = method
        self._means = {}
        self._stds = {}
        self._medians = {}
        self._mads = {}
        self._factor_ranges = {}

    def preprocess(self, df: pd.DataFrame,
                   factors: List[str] = None,
                   fill_method: str = 'median',
                   winsorize: bool = True,
                   n_std: float = 3.0,
                   neutralize: str = None) -> pd.DataFrame:
        """
        预处理因子数据

        Args:
            df: 因子面板数据（index为symbol或(date, symbol)）
            factors: 要处理的因子列表，None表示全部数值列
            fill_method: 缺失值填充方法
                - 'zero': 填充0
                - 'median': 填充中位数（默认）
                - 'mean': 填充均值
                - 'industry_median': 填充行业中位数（需有industry列）
            winsorize: 是否进行Winsorization缩尾处理
            n_std: 缩尾标准差倍数（默认3倍）
            neutralize: 中性化方式
                - None: 不中性化
                - 'industry': 行业中性化
                - 'market_cap': 市值中性化

        Returns:
            处理后的DataFrame
        """
        result = df.copy()

        # 确定要处理的因子列
        if factors is None:
            factors = result.select_dtypes(include=[np.number]).columns.tolist()
            # 排除非因子列
            exclude_cols = ['date', 'trade_date', 'symbol', 'industry', 'market_cap']
            factors = [f for f in factors if f not in exclude_cols]

        print(f"[预处理器] 处理 {len(factors)} 个因子")

        # Step 1: 缺失值处理
        result = self._handle_missing(result, factors, fill_method)

        # Step 2: 异常值处理
        if winsorize:
            result = self._handle_outliers(result, factors, n_std)
            print(f"[预处理器] Winsorization 完成 (n_std={n_std})")

        # Step 3: 标准化
        result[factors] = self._normalize(result[factors], factors)
        print(f"[预处理器] {self.method} 标准化完成")

        # Step 4: 中性化
        if neutralize:
            result = self._neutralize(result, factors, neutralize)
            print(f"[预处理器] {neutralize} 中性化完成")

        return result

    def _handle_missing(self, df: pd.DataFrame,
                        factors: List[str],
                        method: str) -> pd.DataFrame:
        """缺失值处理"""
        result = df.copy()

        for factor in factors:
            if factor not in result.columns:
                continue

            missing_count = result[factor].isna().sum()
            if missing_count == 0:
                continue

            print(f"[缺失值] {factor}: {missing_count} 个缺失值")

            if method == 'zero':
                result[factor] = result[factor].fillna(0)
            elif method == 'median':
                median_val = result[factor].median()
                result[factor] = result[factor].fillna(median_val)
            elif method == 'mean':
                result[factor] = result[factor].fillna(result[factor].mean())
            elif method == 'industry_median' and 'industry' in result.columns:
                result[factor] = result.groupby('industry')[factor].transform(
                    lambda x: x.fillna(x.median())
                )
                # 如果行业均值仍是NaN，用总体中位数填充
                result[factor] = result[factor].fillna(result[factor].median())

        return result

    def _handle_outliers(self, df: pd.DataFrame,
                         factors: List[str],
                         n_std: float) -> pd.DataFrame:
        """
        异常值处理 - Winsorization（缩尾处理）

        将超出 [mean - n_std*std, mean + n_std*std] 范围的值截断
        """
        result = df.copy()

        for factor in factors:
            if factor not in result.columns:
                continue

            mean = result[factor].mean()
            std = result[factor].std()

            if std == 0 or np.isnan(std):
                continue

            lower = mean - n_std * std
            upper = mean + n_std * std

            # 统计被截断的数量
            n_clipped = ((result[factor] < lower) | (result[factor] > upper)).sum()
            if n_clipped > 0:
                print(f"[异常值] {factor}: 截断 {n_clipped} 个异常值")

            result[factor] = result[factor].clip(lower, upper)

        return result

    def _normalize(self, df: pd.DataFrame,
                  factors: List[str]) -> pd.DataFrame:
        """
        因子标准化

        Args:
            df: DataFrame
            factors: 因子列表

        Returns:
            标准化后的DataFrame
        """
        result = df.copy()

        if self.method == 'zscore':
            for factor in factors:
                if factor not in result.columns:
                    continue
                self._means[factor] = result[factor].mean()
                self._stds[factor] = result[factor].std()
                if self._stds[factor] > 0:
                    result[factor] = (result[factor] - self._means[factor]) / self._stds[factor]
                else:
                    result[factor] = 0

        elif self.method == 'rank':
            for factor in factors:
                if factor not in result.columns:
                    continue
                # 排序后转为百分位
                result[factor] = result[factor].rank(pct=True)

        elif self.method == 'minmax':
            for factor in factors:
                if factor not in result.columns:
                    continue
                min_val = result[factor].min()
                max_val = result[factor].max()
                self._factor_ranges[factor] = (min_val, max_val)
                if max_val > min_val:
                    result[factor] = (result[factor] - min_val) / (max_val - min_val)
                else:
                    result[factor] = 0.5

        elif self.method == 'mad':
            for factor in factors:
                if factor not in result.columns:
                    continue
                median = result[factor].median()
                self._medians[factor] = median
                mad = np.abs(result[factor] - median).median()
                self._mads[factor] = mad
                if mad > 0:
                    result[factor] = (result[factor] - median) / (mad * 1.4826)  # 1.4826使MAD与std一致
                else:
                    result[factor] = 0

        return result

    def _neutralize(self, df: pd.DataFrame,
                    factors: List[str],
                    by: str) -> pd.DataFrame:
        """
        因子中性化

        Args:
            df: DataFrame
            factors: 因子列表
            by: 中性化方式
                - 'industry': 行业中性化（减去行业均值）
                - 'market_cap': 市值中性化（回归残差）

        Returns:
            中性化后的DataFrame
        """
        result = df.copy()

        if by == 'industry' and 'industry' in result.columns:
            for factor in factors:
                if factor not in result.columns:
                    continue
                # 行业中性化：减去行业均值
                result[factor] = result.groupby('industry')[factor].transform(
                    lambda x: x - x.mean()
                )

        elif by == 'market_cap' and 'market_cap' in result.columns:
            for factor in factors:
                if factor not in result.columns:
                    continue
                # 市值中性化：回归掉市值影响
                result[factor] = self._regress_out_market_cap(
                    result[factor], result['market_cap']
                )

        return result

    def _regress_out_market_cap(self, factor: pd.Series,
                                 market_cap: pd.Series) -> pd.Series:
        """
        回归掉市值因子

        使用线性回归：factor = a * log(market_cap) + b + residual
        返回 residual
        """
        try:
            # 取对数市值
            log_mcap = np.log(market_cap.clip(lower=1))  # 避免log(0)

            # 去除NaN
            mask = ~(factor.isna() | log_mcap.isna())
            if mask.sum() < 10:
                return factor

            X = log_mcap[mask].values.reshape(-1, 1)
            y = factor[mask].values

            # 简单线性回归
            from sklearn.linear_model import LinearRegression
            model = LinearRegression()
            model.fit(X, y)

            # 预测并计算残差
            residual = factor.copy()
            residual[mask] = y - model.predict(X)

            return residual

        except Exception as e:
            print(f"[中性化] 市值回归失败: {e}")
            return factor

    def get_stats(self) -> Dict:
        """获取预处理统计信息"""
        return {
            'method': self.method,
            'means': self._means.copy(),
            'stds': self._stds.copy(),
            'factor_ranges': self._factor_ranges.copy()
        }


class FactorNeutralizer:
    """
    因子中性化处理（独立类）

    提供行业中性化、市值中性化、风格中性化等功能
    """

    def neutralize(self, df: pd.DataFrame,
                   factors: List[str],
                   by: str = 'industry',
                   style_factors: List[str] = None) -> pd.DataFrame:
        """
        因子中性化

        Args:
            df: 因子数据（需包含industry或market_cap列）
            factors: 要中性化的因子列表
            by: 中性化方式
                - 'industry': 行业中性化
                - 'market_cap': 市值中性化
                - 'style': 风格中性化（Beta、Size等）
            style_factors: 风格因子列表（用于风格中性化）

        Returns:
            中性化后的因子
        """
        result = df.copy()

        if by == 'industry' and 'industry' in result.columns:
            result = self._neutralize_by_industry(result, factors)
        elif by == 'market_cap' and 'market_cap' in result.columns:
            result = self._neutralize_by_market_cap(result, factors)
        elif by == 'style' and style_factors:
            result = self._neutralize_by_style(result, factors, style_factors)

        return result

    def _neutralize_by_industry(self, df: pd.DataFrame,
                                factors: List[str]) -> pd.DataFrame:
        """行业中性化 - 减去行业均值"""
        result = df.copy()

        for factor in factors:
            if factor not in result.columns:
                continue

            # 减去行业均值
            result[factor] = result.groupby('industry')[factor].transform(
                lambda x: x - x.median()
            )

        return result

    def _neutralize_by_market_cap(self, df: pd.DataFrame,
                                   factors: List[str]) -> pd.DataFrame:
        """市值中性化 - 回归残差"""
        result = df.copy()

        for factor in factors:
            if factor not in result.columns:
                continue

            log_mcap = np.log(result['market_cap'].clip(lower=1))

            # 分位数回归（更稳健）
            try:
                from sklearn.linear_model import QuantileRegressor
                model = QuantileRegressor(quantile=0.5, solver='highs')
                X = log_mcap.values.reshape(-1, 1)
                y = result[factor].values

                mask = ~(np.isnan(y) | np.isnan(X.flatten()))
                if mask.sum() > 10:
                    model.fit(X[mask], y[mask])
                    result.loc[mask, factor] = y[mask] - model.predict(X[mask])
            except Exception as e:
                # 如果分位数回归失败，使用普通线性回归
                try:
                    from sklearn.linear_model import LinearRegression
                    model = LinearRegression()
                    model.fit(X[mask], y[mask])
                    result.loc[mask, factor] = y[mask] - model.predict(X[mask])
                except:
                    pass

        return result

    def _neutralize_by_style(self, df: pd.DataFrame,
                            factors: List[str],
                            style_factors: List[str]) -> pd.DataFrame:
        """
        风格中性化 - 回归掉风格因子

        常见风格因子：BETA、SIZE、VALUE、MOMENTUM、QUALITY等
        """
        result = df.copy()

        # 获取有效的风格因子列
        valid_styles = [s for s in style_factors if s in result.columns]
        if not valid_styles:
            return result

        X = result[valid_styles].values
        mask = ~np.isnan(X).any(axis=1)

        for factor in factors:
            if factor not in result.columns:
                continue

            y = result[factor].values
            if mask.sum() > len(valid_styles) + 5:
                try:
                    from sklearn.linear_model import LinearRegression
                    model = LinearRegression()
                    model.fit(X[mask], y[mask])
                    result.loc[mask.values, factor] = y[mask] - model.predict(X[mask])
                except:
                    pass

        return result


# ========== 便捷函数 ==========

def preprocess_factors(df: pd.DataFrame,
                       factors: List[str] = None,
                       method: str = 'zscore',
                       neutralize: str = None) -> pd.DataFrame:
    """
    便捷函数：预处理因子数据

    Args:
        df: 因子面板数据
        factors: 因子列表
        method: 标准化方法
        neutralize: 中性化方式

    Returns:
        处理后的DataFrame
    """
    preprocessor = FactorPreprocessor(method=method)
    return preprocessor.preprocess(df, factors, neutralize=neutralize)


if __name__ == "__main__":
    print("=" * 60)
    print("测试 FactorPreprocessor")
    print("=" * 60)

    import numpy as np

    # 模拟因子数据
    np.random.seed(42)
    n = 100

    # 创建包含异常值和缺失值的模拟数据
    data = {
        'symbol': [f'股票{i:03d}' for i in range(n)],
        'industry': np.random.choice(['银行', '地产', '消费', '科技'], n),
        'market_cap': np.random.lognormal(10, 1, n),  # 市值
        'pe': np.random.normal(15, 10, n),
        'roe': np.random.normal(0.12, 0.05, n),
        'revenue_growth': np.random.normal(0.2, 0.3, n),
    }

    df = pd.DataFrame(data)

    # 添加异常值
    df.loc[0:5, 'pe'] = [500, -100, 300, -50, 400, 600]
    # 添加缺失值
    df.loc[10:15, 'roe'] = np.nan

    print("原始数据统计:")
    print(df[['pe', 'roe', 'revenue_growth']].describe())

    # 预处理
    preprocessor = FactorPreprocessor(method='zscore')
    processed = preprocessor.preprocess(
        df,
        factors=['pe', 'roe', 'revenue_growth'],
        fill_method='median',
        winsorize=True,
        n_std=3.0,
        neutralize='industry'
    )

    print("\n处理后数据统计:")
    print(processed[['pe', 'roe', 'revenue_growth']].describe())

    print("\n测试完成")