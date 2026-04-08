"""
仓位分配模块
根据不同策略分配每只股票的持仓比例
"""
import numpy as np
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from enum import Enum


class PositionMethod(Enum):
    """仓位分配方法"""
    EQUAL_WEIGHT = "equal"           # 等权重
    RISK_PARITY = "risk_parity"     # 风险平价
    MOMENTUM_WEIGHT = "momentum"    # 动量加权
    SCORE_WEIGHT = "score"          # 综合打分加权
    KELLY = "kelly"                # 凯利公式


@dataclass
class PositionResult:
    """仓位分配结果"""
    symbol: str
    weight: float           # 仓位权重 (0-1)
    shares: int              # 买入股数
    amount: float           # 买入金额
    score: float = 0.0       # 该股票的综合得分

    @property
    def weight_percent(self) -> str:
        return f"{self.weight * 100:.1f}%"


class PositionSizer:
    """
    仓位分配器

    功能：
    - 根据不同策略分配仓位
    - 支持等权重、风险平价、动量加权等
    - 自动调整以满足总仓位约束
    """

    def __init__(
        self,
        method: PositionMethod = PositionMethod.EQUAL_WEIGHT,
        max_total_position: float = 0.8,     # 最大总仓位 (80%)
        max_single_position: float = 0.3,     # 单只最大仓位 (30%)
        min_single_position: float = 0.05     # 单只最小仓位 (5%)
    ):
        """
        初始化仓位分配器

        Args:
            method: 分配方法
            max_total_position: 最大总仓位比例
            max_single_position: 单只股票最大仓位比例
            min_single_position: 单只股票最小仓位比例
        """
        self.method = method
        self.max_total_position = max_total_position
        self.max_single_position = max_single_position
        self.min_single_position = min_single_position

    def allocate(
        self,
        candidates: List[Tuple[str, float, float]],
        # List of (symbol, score, volatility)
        total_capital: float,
        prices: Dict[str, float] = None
    ) -> List[PositionResult]:
        """
        分配仓位

        Args:
            candidates: 候选股票列表，每个元素为 (symbol, score, volatility)
            total_capital: 总资金
            prices: 股票价格字典 {symbol: price}

        Returns:
            仓位分配结果列表
        """
        if not candidates:
            return []

        prices = prices or {}

        # 根据方法计算权重
        if self.method == PositionMethod.EQUAL_WEIGHT:
            weights = self._equal_weight(len(candidates))
        elif self.method == PositionMethod.RISK_PARITY:
            weights = self._risk_parity([c[2] for c in candidates])
        elif self.method == PositionMethod.MOMENTUM_WEIGHT:
            weights = self._momentum_weight([c[1] for c in candidates])
        elif self.method == PositionMethod.SCORE_WEIGHT:
            weights = self._score_weight([c[1] for c in candidates])
        elif self.method == PositionMethod.KELLY:
            weights = self._kelly_weight([c[1] for c in candidates])
        else:
            weights = self._equal_weight(len(candidates))

        # 应用总仓位限制
        weights = [w * self.max_total_position for w in weights]

        # 应用单只仓位限制
        weights = [min(w, self.max_single_position) for w in weights]

        # 归一化，确保总和不超过 max_total_position
        total_weight = sum(weights)
        if total_weight > self.max_total_position:
            weights = [w / total_weight * self.max_total_position for w in weights]

        # 分配资金
        results = []
        zero_share_indices = []  # 记录因金额不足而无法买入的股票索引

        for i, (symbol, score, volatility) in enumerate(candidates):
            weight = weights[i]
            amount = total_capital * weight
            price = prices.get(symbol, 0)

            # 计算股数 (A股必须是100的整数倍)
            if price > 0:
                shares = int(amount / price / 100) * 100
                shares = max(shares, 0)  # 确保非负
                # 检查是否因金额不足而无法购买100股
                if shares == 0 and amount < price * 100:
                    # 金额不足以购买100股，记录索引
                    zero_share_indices.append(i)
            else:
                shares = 0
                amount = 0

            results.append(PositionResult(
                symbol=symbol,
                weight=weight,
                shares=shares,
                amount=shares * price if price > 0 else 0,
                score=score
            ))

        # 处理因金额不足无法购买100股的股票：将她们的权重重新分配给其他股票
        if zero_share_indices and len(results) > len(zero_share_indices):
            # 计算释放的权重总和
            released_weight = sum(results[i].weight for i in zero_share_indices)
            released_amount = sum(results[i].amount for i in zero_share_indices)

            # 清零这些无法买入的股票的权重和金额
            for i in zero_share_indices:
                results[i].weight = 0
                results[i].amount = 0

            # 计算剩余可分配的股票
            remaining_indices = [i for i in range(len(results)) if i not in zero_share_indices and results[i].shares > 0]
            if remaining_indices and released_weight > 0:
                # 按权重比例将释放的权重加给其他股票
                remaining_total_weight = sum(results[i].weight for i in remaining_indices)
                for i in remaining_indices:
                    if remaining_total_weight > 0:
                        # 这只股票额外获得的权重比例
                        extra_ratio = results[i].weight / remaining_total_weight
                        extra_weight = released_weight * extra_ratio
                        results[i].weight += extra_weight
                        # 重新计算金额和股数
                        extra_amount = total_capital * extra_weight
                        results[i].amount += extra_amount
                        extra_shares = int(extra_amount / prices.get(results[i].symbol, 0) / 100) * 100
                        if extra_shares > 0:
                            results[i].shares += extra_shares

        return results

    def _equal_weight(self, n: int) -> List[float]:
        """等权重分配"""
        if n == 0:
            return []
        return [1.0 / n] * n

    def _risk_parity(self, volatilities: List[float]) -> List[float]:
        """
        风险平价分配

        波动率越低，权重越高
        """
        # 将波动率转换为风险权重（波动率越低，权重越高）
        inv_vol = [1.0 / (v + 0.01) for v in volatilities]  # 加0.01避免除零
        total = sum(inv_vol)
        return [v / total for v in inv_vol]

    def _momentum_weight(self, scores: List[float]) -> List[float]:
        """
        动量加权分配

        得分越高，权重越高
        """
        # 确保得分为正
        scores = [max(s, 0) for s in scores]
        total = sum(scores)
        if total == 0:
            return [1.0 / len(scores)] * len(scores)
        return [s / total for s in scores]

    def _score_weight(self, scores: List[float]) -> List[float]:
        """
        综合打分加权

        使用softmax风格的加权
        """
        # 使用指数加权，突出高分
        exp_scores = [np.exp(s / 50) for s in scores]  # s/50 防止数值爆炸
        total = sum(exp_scores)
        return [e / total for e in exp_scores]

    def _kelly_weight(self, returns: List[float]) -> List[float]:
        """
        凯利公式仓位分配

        f = (bp - q) / b
        其中:
        - b = 赔率（盈亏比）
        - p = 胜率
        - q = 1 - p

        Args:
            returns: 预期收益率列表（简化版，只使用正收益的均值/负收益的均值作为赔率）

        Returns:
            建议的仓位比例
        """
        n = len(returns)
        if n == 0:
            return []

        # 简化凯利：使用历史收益估算
        positive_returns = [r for r in returns if r > 0]
        negative_returns = [r for r in returns if r < 0]

        if not positive_returns or not negative_returns:
            return self._equal_weight(n)

        # 计算平均盈亏
        avg_win = np.mean(positive_returns)
        avg_loss = abs(np.mean(negative_returns))

        if avg_loss == 0:
            return self._equal_weight(n)

        # 简化胜率
        win_rate = len(positive_returns) / n

        # 凯利公式
        b = avg_win / avg_loss  # 赔率
        p = win_rate
        q = 1 - p

        kelly_fraction = (b * p - q) / b

        # 限制凯利比例（通常只用凯利的50%以降低风险）
        kelly_fraction = kelly_fraction * 0.5

        if kelly_fraction <= 0:
            return self._equal_weight(n)

        # 将凯利比例分配给所有候选（简化处理）
        return [kelly_fraction / n] * n

    def adjust_for_portfolio(
        self,
        positions: List[PositionResult],
        current_positions: Dict[str, float] = None,
        # 当前持仓 {symbol: weight}
        target_total: float = 0.8
    ) -> List[PositionResult]:
        """
        调整仓位以达到目标总仓位

        Args:
            positions: 现有仓位分配
            current_positions: 当前实际持仓
            target_total: 目标总仓位

        Returns:
            调整后的仓位
        """
        current_positions = current_positions or {}

        # 计算当前总仓位
        current_total = sum(current_positions.values())

        if current_total >= target_total:
            # 已满仓，减少新买入
            return []

        # 需要买入的总仓位
        available = target_total - current_total

        # 调整权重
        total_weight = sum(p.weight for p in positions)
        if total_weight == 0:
            return []

        adjusted = []
        for p in positions:
            new_weight = p.weight / total_weight * available
            new_weight = max(new_weight, 0)
            new_weight = min(new_weight, self.max_single_position)

            adjusted.append(PositionResult(
                symbol=p.symbol,
                weight=new_weight,
                shares=p.shares,  # 不变
                amount=p.amount,
                score=p.score
            ))

        return adjusted


def create_position_sizer(
    method: str = "equal",
    max_total: float = 0.8,
    max_single: float = 0.3
) -> PositionSizer:
    """
    创建仓位分配器的便捷函数

    Args:
        method: 分配方法 (equal/risk_parity/momentum/score/kelly)
        max_total: 最大总仓位
        max_single: 单只最大仓位

    Returns:
        PositionSizer实例
    """
    method_map = {
        "equal": PositionMethod.EQUAL_WEIGHT,
        "risk_parity": PositionMethod.RISK_PARITY,
        "momentum": PositionMethod.MOMENTUM_WEIGHT,
        "score": PositionMethod.SCORE_WEIGHT,
        "kelly": PositionMethod.KELLY
    }

    return PositionSizer(
        method=method_map.get(method, PositionMethod.EQUAL_WEIGHT),
        max_total_position=max_total,
        max_single_position=max_single
    )


# ==================== 便捷函数 ====================

def allocate_equal_weight(
    symbols: List[str],
    total_capital: float,
    prices: Dict[str, float],
    max_total: float = 0.8
) -> List[PositionResult]:
    """等权重分配"""
    sizer = create_position_sizer(method="equal", max_total=max_total)
    candidates = [(s, 1.0, 0.2) for s in symbols]  # 简化：得分=1，波动=0.2
    return sizer.allocate(candidates, total_capital, prices)


def allocate_by_score(
    scores: List[Tuple[str, float]],
    total_capital: float,
    prices: Dict[str, float],
    max_total: float = 0.8
) -> List[PositionResult]:
    """
    按综合得分分配仓位

    Args:
        scores: 股票得分列表 [(symbol, score), ...]
        total_capital: 总资金
        prices: 价格字典
        max_total: 最大仓位

    Returns:
        仓位分配结果
    """
    sizer = create_position_sizer(method="score", max_total=max_total)
    candidates = [(s, sc, 0.2) for s, sc in scores]  # 简化：波动=0.2
    return sizer.allocate(candidates, total_capital, prices)


if __name__ == "__main__":
    # 测试代码

    # 候选股票：(symbol, score, volatility)
    candidates = [
        ("000001.SZ", 80, 0.25),
        ("600000.SH", 70, 0.20),
        ("600519.SH", 90, 0.18),
        ("000858.SZ", 65, 0.22)
    ]

    prices = {
        "000001.SZ": 12.50,
        "600000.SH": 8.30,
        "600519.SH": 1750.00,
        "000858.SZ": 165.00
    }

    total_capital = 1000000

    print("=== 不同分配方法对比 ===\n")

    methods = ["equal", "risk_parity", "momentum", "score", "kelly"]

    for method in methods:
        sizer = create_position_sizer(method=method, max_total=0.8)
        positions = sizer.allocate(candidates, total_capital, prices)

        total_weight = sum(p.weight for p in positions)
        print(f"【{method}】总仓位: {total_weight:.2%}")
        for p in positions:
            print(f"  {p.symbol}: {p.weight_percent}, {p.shares}股, ¥{p.amount:,.0f}")
        print()
