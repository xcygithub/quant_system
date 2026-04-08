"""
选股模块
根据多维度对股票进行打分和排序
"""
import pandas as pd
import numpy as np
from typing import List, Dict, Optional, Callable
from dataclasses import dataclass
from enum import Enum


class ScoringMethod(Enum):
    """选股打分方法"""
    MOMENTUM = "momentum"           # 动量打分
    SIGNAL_STRENGTH = "signal"     # 信号强度打分
    COMPOSITE = "composite"         # 综合打分
    VOLATILITY = "volatility"       # 低波动打分
    LIQUIDITY = "liquidity"         # 流动性打分


@dataclass
class StockScore:
    """股票评分结果"""
    symbol: str
    name: str = ""
    score: float = 0.0
    momentum_score: float = 0.0     # 动量得分
    signal_score: float = 0.0       # 信号强度得分
    volatility_score: float = 0.0    # 波动率得分
    liquidity_score: float = 0.0    # 流动性得分
    composite_score: float = 0.0    # 综合得分
    signal_type: str = "hold"           # 当前信号类型 (buy/sell/hold)
    signal_strength: float = 0.0    # 信号强度 (0-1)

    @property
    def rank(self) -> int:
        """排名（由排序算法设置）"""
        return getattr(self, '_rank', 0)

    @rank.setter
    def rank(self, value: int):
        self._rank = value


class StockSelector:
    """
    多股票选股器

    功能：
    - 对候选股票进行多维度打分
    - 根据打分结果排序
    - 筛选Top N股票
    - 支持自定义打分权重
    """

    def __init__(
        self,
        method: ScoringMethod = ScoringMethod.COMPOSITE,
        weights: Dict[str, float] = None,
        top_n: int = 10,
        min_score: float = 0.0
    ):
        """
        初始化选股器

        Args:
            method: 选股方法
            weights: 各维度权重 (默认等权重)
            top_n: 选取前N只股票
            min_score: 最低得分门槛
        """
        self.method = method
        self.weights = weights or {
            'momentum': 0.3,
            'signal': 0.3,
            'volatility': 0.2,
            'liquidity': 0.2
        }
        self.top_n = top_n
        self.min_score = min_score

    def score_stocks(
        self,
        stock_data: Dict[str, pd.DataFrame],
        signals: Dict[str, pd.Series] = None,
        prices: Dict[str, pd.Series] = None
    ) -> List[StockScore]:
        """
        对多只股票进行打分

        Args:
            stock_data: 股票数据字典 {symbol: dataframe}
                        DataFrame需要包含 close, volume 列
            signals: 信号字典 {symbol: signal_series}
                     signal为 1(买入), 0(持有), -1(卖出)
            prices: 价格字典 {symbol: price_series}

        Returns:
            排序后的股票评分列表
        """
        scores = []

        for symbol, df in stock_data.items():
            if df.empty or len(df) < 10:
                continue

            score = self._calculate_stock_score(
                symbol=symbol,
                df=df,
                signal=signals.get(symbol) if signals else None,
                price=prices.get(symbol) if prices else None
            )
            scores.append(score)

        # 计算综合得分
        for score in scores:
            score.composite_score = (
                score.momentum_score * self.weights.get('momentum', 0.25) +
                score.signal_score * self.weights.get('signal', 0.25) +
                score.volatility_score * self.weights.get('volatility', 0.25) +
                score.liquidity_score * self.weights.get('liquidity', 0.25)
            )

        # 按综合得分排序
        scores.sort(key=lambda x: x.composite_score, reverse=True)

        # 设置排名
        for i, score in enumerate(scores):
            score.rank = i + 1

        return scores

    def _calculate_stock_score(
        self,
        symbol: str,
        df: pd.DataFrame,
        signal: pd.Series = None,
        price: pd.Series = None
    ) -> StockScore:
        """计算单只股票的各维度得分"""

        score = StockScore(symbol=symbol)

        # 获取最新数据
        close = df['close'].iloc[-1]
        volume = df['volume'].iloc[-1]

        # 1. 动量得分 (基于近期收益率)
        momentum = self._calculate_momentum(df)
        score.momentum_score = momentum

        # 2. 信号强度得分
        if signal is not None and len(signal) > 0:
            signal_score, signal_type = self._calculate_signal_score(signal)
            score.signal_score = signal_score
            score.signal_type = signal_type
            score.signal_strength = abs(signal.iloc[-1]) if len(signal) > 0 else 0

        # 3. 波动率得分 (波动率越低得分越高)
        volatility = self._calculate_volatility(df)
        score.volatility_score = 1.0 / (1.0 + volatility)  # 低波动得高分

        # 4. 流动性得分 (成交额越高得分越高)
        liquidity = self._calculate_liquidity(df)
        score.liquidity_score = liquidity

        return score

    def _calculate_momentum(self, df: pd.DataFrame, periods: List[int] = None) -> float:
        """
        计算动量得分

        基于不同周期的收益率加权计算动量
        """
        if periods is None:
            periods = [5, 10, 20]  # 短、中、长期

        close = df['close']

        scores = []
        weights = [0.5, 0.3, 0.2]  # 短期权重更高

        for period, weight in zip(periods, weights):
            if len(close) >= period:
                ret = (close.iloc[-1] / close.iloc[-period] - 1) * 100
                # 标准化到0-100 (假设收益率范围-20%到+20%)
                normalized = max(0, min(100, (ret + 20) / 40 * 100))
                scores.append(normalized * weight)

        return sum(scores) if scores else 50.0

    def _calculate_signal_score(
        self,
        signal: pd.Series
    ) -> tuple:
        """
        计算信号强度得分

        Returns:
            (score, signal_type)
        """
        if len(signal) < 2:
            return 50.0, "hold"

        latest = signal.iloc[-1]
        prev = signal.iloc[-1] if len(signal) > 1 else 0

        # 计算信号一致性（最近N天信号相同的比例）
        window = min(5, len(signal))
        recent_signals = signal.iloc[-window:]
        signal_consistency = (recent_signals == latest).sum() / window

        if latest > 0:
            signal_type = "buy"
            score = signal_consistency * 50 + 50  # 买入信号50-100分
        elif latest < 0:
            signal_type = "sell"
            score = (1 - signal_consistency) * 50  # 卖出信号0-50分
        else:
            signal_type = "hold"
            score = 50.0

        return score, signal_type

    def _calculate_volatility(self, df: pd.DataFrame, window: int = 20) -> float:
        """计算波动率（标准差/均值）"""
        if len(df) < window:
            return 0.0

        close = df['close']
        returns = close.pct_change().dropna()

        if len(returns) == 0:
            return 0.0

        volatility = returns.std() * np.sqrt(252)  # 年化波动率
        mean_return = returns.mean() * 252

        # 调整后的波动率
        return volatility

    def _calculate_liquidity(self, df: pd.DataFrame, window: int = 5) -> float:
        """计算流动性得分（基于日均成交额）"""
        if 'amount' in df.columns:
            avg_amount = df['amount'].iloc[-window:].mean()
        elif 'volume' in df.columns:
            avg_amount = (df['volume'] * df['close']).iloc[-window:].mean()
        else:
            return 50.0

        # 标准化成交额得分 (假设1亿以上为满分)
        score = min(100, avg_amount / 100000000 * 100)
        return score

    def filter_and_rank(
        self,
        scores: List[StockScore],
        top_n: int = None,
        min_score: float = None,
        signal_type: str = None
    ) -> List[StockScore]:
        """
        筛选并排序股票

        Args:
            scores: 股票评分列表
            top_n: 选取前N只
            min_score: 最低得分门槛
            signal_type: 信号类型过滤 (buy/sell/hold)

        Returns:
            筛选后的股票评分列表
        """
        filtered = scores

        # 按信号类型过滤
        if signal_type:
            filtered = [s for s in filtered if s.signal_type == signal_type]

        # 按最低得分过滤
        min_s = min_score if min_score is not None else self.min_score
        filtered = [s for s in filtered if s.composite_score >= min_s]

        # 取Top N
        n = top_n if top_n is not None else self.top_n
        filtered = filtered[:n]

        # 重新设置排名
        for i, score in enumerate(filtered):
            score.rank = i + 1

        return filtered

    def select_buy_candidates(
        self,
        scores: List[StockScore],
        top_n: int = None,
        min_score: float = None
    ) -> List[StockScore]:
        """筛选买入候选股票"""
        # 按综合得分排序所有股票（不再只依赖 signal_type）
        # 这样有买入历史但当前 signal_type 不是 'buy' 的股票也可能被选中
        sorted_scores = sorted(scores, key=lambda x: x.composite_score, reverse=True)

        # 按最低得分过滤
        min_s = min_score if min_score is not None else self.min_score
        filtered = [s for s in sorted_scores if s.composite_score >= min_s]

        # 取 Top N
        n = top_n if top_n is not None else self.top_n
        return filtered[:n]


def create_selector(
    method: str = "composite",
    top_n: int = 10,
    momentum_weight: float = 0.3,
    signal_weight: float = 0.3,
    volatility_weight: float = 0.2,
    liquidity_weight: float = 0.2
) -> StockSelector:
    """
    创建选股器的便捷函数

    Args:
        method: 选股方法 (momentum/signal/composite/volatility/liquidity)
        top_n: 选取前N只
        momentum_weight: 动量权重
        signal_weight: 信号强度权重
        volatility_weight: 波动率权重
        liquidity_weight: 流动性权重

    Returns:
        StockSelector实例
    """
    method_map = {
        "momentum": ScoringMethod.MOMENTUM,
        "signal": ScoringMethod.SIGNAL_STRENGTH,
        "composite": ScoringMethod.COMPOSITE,
        "volatility": ScoringMethod.VOLATILITY,
        "liquidity": ScoringMethod.LIQUIDITY
    }

    weights = {
        'momentum': momentum_weight,
        'signal': signal_weight,
        'volatility': volatility_weight,
        'liquidity': liquidity_weight
    }

    return StockSelector(
        method=method_map.get(method, ScoringMethod.COMPOSITE),
        weights=weights,
        top_n=top_n
    )


if __name__ == "__main__":
    # 测试代码
    from datetime import datetime, timedelta

    # 模拟数据
    dates = pd.date_range(end=datetime.now(), periods=60, freq='D')

    stock_data = {
        "000001.SZ": pd.DataFrame({
            'date': dates,
            'close': 10 + np.random.randn(60).cumsum() + 15,
            'volume': np.random.randint(1000000, 10000000, 60),
            'amount': np.random.randint(10000000, 100000000, 60)
        }),
        "600000.SH": pd.DataFrame({
            'date': dates,
            'close': 8 + np.random.randn(60).cumsum() + 12,
            'volume': np.random.randint(2000000, 15000000, 60),
            'amount': np.random.randint(15000000, 120000000, 60)
        }),
        "600519.SH": pd.DataFrame({
            'date': dates,
            'close': 1800 + np.random.randn(60).cumsum() + 500,
            'volume': np.random.randint(500000, 3000000, 60),
            'amount': np.random.randint(50000000, 300000000, 60)
        })
    }

    # 模拟信号
    signals = {
        "000001.SZ": pd.Series([0, 0, 1, 1, 1], index=dates[-5:]),
        "600000.SH": pd.Series([0, 0, 0, 1, 1], index=dates[-5:]),
        "600519.SH": pd.Series([-1, 0, 0, 0, 1], index=dates[-5:])
    }

    # 创建选股器
    selector = create_selector(method="composite", top_n=3)

    # 评分
    scores = selector.score_stocks(stock_data, signals)

    print("=== 选股评分结果 ===")
    for s in scores:
        print(f"{s.rank}. {s.symbol}: 综合={s.composite_score:.2f}, "
              f"动量={s.momentum_score:.2f}, 信号={s.signal_score:.2f} "
              f"({s.signal_type})")

    # 筛选买入候选
    print("\n=== 买入候选 ===")
    candidates = selector.select_buy_candidates(scores, top_n=2)
    for c in candidates:
        print(f"{c.rank}. {c.symbol}: score={c.composite_score:.2f}")
