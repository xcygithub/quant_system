"""
因子信号生成器
根据因子 IC 加权得分生成交易信号
"""
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Any

try:
    from scipy.stats import rankdata
except ImportError:
    rankdata = None


class FactorSignalGenerator:
    """
    因子信号生成器

    功能：
    - 读取因子值
    - 计算因子得分（横截面百分位）
    - 结合 IC 权重生成加权得分
    - 生成买卖信号
    """

    def __init__(
        self,
        factor_weights: Dict[str, float] = None,
        ic_weights: Dict[str, float] = None,
        use_ic_weighted: bool = True,
        buy_threshold: float = 80.0,  # 百分位 > 80 买入
        sell_threshold: float = 20.0  # 百分位 < 20 卖出
    ):
        """
        初始化

        Args:
            factor_weights: 基础因子权重
            ic_weights: IC 调整后权重
            use_ic_weighted: 是否使用 IC 加权
            buy_threshold: 买入阈值（百分位）
            sell_threshold: 卖出阈值（百分位）
        """
        self.base_weights = factor_weights or {}
        self.ic_weights = ic_weights or {}
        self.use_ic_weighted = use_ic_weighted
        self.buy_threshold = buy_threshold
        self.sell_threshold = sell_threshold

    def generate_signals(
        self,
        factor_data: pd.DataFrame,
        prices: Dict[str, float],
        current_positions: Dict[str, float] = None
    ) -> Dict[str, int]:
        """
        生成交易信号

        Args:
            factor_data: DataFrame(index=symbol, columns=factor_values)
            prices: 当前价格 {symbol: price}
            current_positions: 当前持仓市值 {symbol: market_value}

        Returns:
            {symbol: signal}
            signal: 1=买入, 0=持有/不操作, -1=卖出
        """
        if factor_data.empty:
            return {}

        signals = {}

        # 1. 计算横截面百分位得分
        percentile_scores = self._calculate_percentile_scores(factor_data)

        # 2. 计算综合得分
        combined_scores = self._calculate_combined_scores(percentile_scores)

        # 3. 生成信号
        for symbol in factor_data.index:
            score = combined_scores.get(symbol, 50.0)  # 默认 50 分

            if score >= self.buy_threshold:
                signals[symbol] = 1  # 买入信号
            elif score <= self.sell_threshold:
                # 检查是否持有
                if current_positions and symbol in current_positions:
                    signals[symbol] = -1  # 卖出信号
                else:
                    signals[symbol] = 0  # 无持仓，不操作
            else:
                signals[symbol] = 0  # 持有/不操作

        return signals

    def generate_ranking_signals(
        self,
        factor_data: pd.DataFrame,
        top_n: int = 10
    ) -> Dict[str, int]:
        """
        生成排序信号（用于选股）

        Args:
            factor_data: DataFrame(index=symbol, columns=factor_values)
            top_n: 选前 N 只

        Returns:
            {symbol: signal}
            signal: 1=买入, 0=不持有
        """
        if factor_data.empty:
            return {}

        # 计算综合得分
        percentile_scores = self._calculate_percentile_scores(factor_data)
        combined_scores = self._calculate_combined_scores(percentile_scores)

        # 排序选前 N
        sorted_symbols = sorted(
            combined_scores.items(),
            key=lambda x: x[1],
            reverse=True
        )

        signals = {}
        for i, (symbol, score) in enumerate(sorted_symbols):
            if i < top_n:
                signals[symbol] = 1  # 买入
            else:
                signals[symbol] = 0  # 不持有

        return signals

    def get_combined_scores(
        self,
        factor_data: pd.DataFrame
    ) -> pd.Series:
        """
        获取综合得分（不生成信号）

        Args:
            factor_data: DataFrame(index=symbol, columns=factor_values)

        Returns:
            Series(index=symbol, values=combined_score)
        """
        if factor_data.empty:
            return pd.Series(dtype=float)

        percentile_scores = self._calculate_percentile_scores(factor_data)
        return self._calculate_combined_scores(percentile_scores)

    def _calculate_percentile_scores(
        self,
        factor_data: pd.DataFrame
    ) -> Dict[str, Dict[str, float]]:
        """
        计算横截面百分位得分

        Args:
            factor_data: DataFrame(index=symbol, columns=factor_values)

        Returns:
            {symbol: {factor_name: percentile_score}}
        """
        percentile_scores = {}

        for symbol in factor_data.index:
            percentile_scores[symbol] = {}

            for factor_name in factor_data.columns:
                factor_values = factor_data[factor_name].dropna()

                if len(factor_values) < 2:
                    percentile_scores[symbol][factor_name] = 50.0
                    continue

                # 该股票在此因子上若缺失，使用中性分，避免索引越界
                if symbol not in factor_values.index:
                    percentile_scores[symbol][factor_name] = 50.0
                    continue

                # 使用带索引的 rank，确保 symbol 与 rank 一一对应
                rank = factor_values.rank(method="average").loc[symbol]
                percentile = (rank - 1) / (len(factor_values) - 1) * 100
                percentile_scores[symbol][factor_name] = percentile

        return percentile_scores

    def _calculate_combined_scores(
        self,
        percentile_scores: Dict[str, Dict[str, float]]
    ) -> Dict[str, float]:
        """
        计算 IC 加权综合得分

        Args:
            percentile_scores: {symbol: {factor: percentile}}

        Returns:
            {symbol: combined_score}
        """
        # 获取最终权重
        weights = self._get_final_weights()

        combined_scores = {}

        for symbol, factor_scores in percentile_scores.items():
            weighted_sum = 0.0
            total_weight = 0.0

            for factor_name, percentile in factor_scores.items():
                weight = weights.get(factor_name, 0.0)
                if weight > 0:
                    # 百分位转换为得分（越高越好，所以直接用）
                    weighted_sum += percentile * weight
                    total_weight += weight

            if total_weight > 0:
                combined_scores[symbol] = weighted_sum / total_weight
            else:
                combined_scores[symbol] = 50.0  # 默认得分

        return combined_scores

    def _get_final_weights(self) -> Dict[str, float]:
        """
        获取最终权重

        如果 use_ic_weighted=True 且有 IC 权重，使用 IC 权重
        否则使用基础权重
        """
        if self.use_ic_weighted and self.ic_weights:
            return self.ic_weights
        return self.base_weights

    def update_weights(
        self,
        factor_weights: Dict[str, float] = None,
        ic_weights: Dict[str, float] = None
    ):
        """
        更新权重配置

        Args:
            factor_weights: 新的基础权重
            ic_weights: 新的 IC 权重
        """
        if factor_weights is not None:
            self.base_weights = factor_weights
        if ic_weights is not None:
            self.ic_weights = ic_weights


class FactorSignalConfig:
    """
    因子信号配置

    封装因子信号生成器的配置参数
    """

    # 因子方向定义（因子值越高越好还是越低越好）
    POSITIVE_FACTORS = {
        'roe', 'roa', 'roic', 'gross_margin', 'net_margin',
        'revenue_growth', 'profit_growth', 'equity_growth',
        'momentum_5', 'momentum_20', 'momentum_60',
        'cash_to_profit', 'fcf', 'cash_yield',
        'pb_roe', 'pe_growth', 'altman_z',
        'current_ratio', 'quick_ratio'
    }

    NEGATIVE_FACTORS = {
        'pe', 'pe_ttm', 'pb', 'ps', 'pcf',
        'debt_ratio', 'equity_multiplier'
    }

    def __init__(
        self,
        factor_weights: Dict[str, float] = None,
        factor_directions: Dict[str, int] = None
    ):
        """
        初始化配置

        Args:
            factor_weights: 因子权重
            factor_directions: 因子方向 {factor: 1(正相关)/-1(负相关)}
        """
        self.factor_weights = factor_weights or {}
        self.factor_directions = factor_directions or self._infer_directions()

    def _infer_directions(self) -> Dict[str, int]:
        """推断因子方向"""
        directions = {}
        for factor in self.factor_weights.keys():
            if factor in self.POSITIVE_FACTORS:
                directions[factor] = 1
            elif factor in self.NEGATIVE_FACTORS:
                directions[factor] = -1
            else:
                directions[factor] = 1  # 默认正相关
        return directions

    def get_weight(self, factor: str) -> float:
        """获取因子权重"""
        return self.factor_weights.get(factor, 0.0)

    def get_direction(self, factor: str) -> int:
        """获取因子方向"""
        return self.factor_directions.get(factor, 1)


def create_signal_generator(
    factor_config: Dict[str, Any] = None,
    ic_weights: Dict[str, float] = None,
    use_ic_weighted: bool = True
) -> FactorSignalGenerator:
    """
    创建因子信号生成器的便捷函数

    Args:
        factor_config: 因子配置
        ic_weights: IC 权重
        use_ic_weighted: 是否使用 IC 加权

    Returns:
        FactorSignalGenerator 实例
    """
    config = factor_config or {}

    # 默认因子配置
    default_config = {
        'roe': 0.20,
        'pe': 0.10,
        'pb': 0.10,
        'momentum_20': 0.20,
        'revenue_growth': 0.15,
        'debt_ratio': 0.10,
        'liquidity': 0.15
    }

    # 合并配置
    weights = config.get('weights', default_config)

    return FactorSignalGenerator(
        factor_weights=weights,
        ic_weights=ic_weights,
        use_ic_weighted=use_ic_weighted,
        buy_threshold=config.get('buy_threshold', 80.0),
        sell_threshold=config.get('sell_threshold', 20.0)
    )


if __name__ == "__main__":
    # 测试
    import numpy as np

    # 生成测试数据
    symbols = [f'{i:06d}.SH' for i in range(100)]
    np.random.seed(42)

    factor_data = pd.DataFrame({
        'roe': np.random.randn(100) * 5 + 10,
        'pe': np.random.randn(100) * 5 + 20,
        'momentum_20': np.random.randn(100) * 0.1,
        'revenue_growth': np.random.randn(100) * 0.2
    }, index=symbols)

    # 创建生成器
    generator = FactorSignalGenerator(
        factor_weights={
            'roe': 0.30,
            'pe': 0.20,
            'momentum_20': 0.30,
            'revenue_growth': 0.20
        },
        use_ic_weighted=False
    )

    # 生成信号
    prices = {s: 10 + np.random.randn() * 2 for s in symbols}
    signals = generator.generate_signals(factor_data, prices)

    buy_count = sum(1 for v in signals.values() if v == 1)
    sell_count = sum(1 for v in signals.values() if v == -1)

    print(f"买入信号: {buy_count}")
    print(f"卖出信号: {sell_count}")

    # 测试排名信号
    ranking_signals = generator.generate_ranking_signals(factor_data, top_n=10)
    print(f"排名选股买入: {sum(1 for v in ranking_signals.values() if v == 1)}")
