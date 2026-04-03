"""
风险管理器 - 仓位管理和风险控制
"""
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from enum import Enum


class PositionSizingMethod(Enum):
    """仓位计算方法"""
    FIXED = "fixed"              # 固定金额
    FIXED_PERCENT = "fixed_pct"  # 固定比例
    VOLATILITY = "volatility"    # 波动率调整
    KELLY = "kelly"              # 凯利公式
    RISK_PARITY = "risk_parity"  # 风险平价


@dataclass
class RiskLimits:
    """风险控制参数"""
    max_position_pct: float = 0.95      # 最大持仓比例
    max_single_position_pct: float = 0.3  # 单个标的最大持仓
    max_sector_pct: float = 0.5         # 单个行业最大持仓
    max_drawdown_limit: float = 0.2     # 最大回撤限制
    daily_loss_limit: float = 0.05      # 日亏损限制
    max_leverage: float = 1.0           # 最大杠杆


class PositionSizer:
    """
    仓位计算器
    
    根据不同的方法计算合适的仓位大小
    """
    
    def __init__(self, method: PositionSizingMethod = PositionSizingMethod.FIXED_PERCENT,
                 params: Dict[str, Any] = None):
        """
        初始化
        
        Args:
            method: 仓位计算方法
            params: 参数字典
        """
        self.method = method
        self.params = params or {}
    
    def calculate_position_size(
        self,
        capital: float,
        price: float,
        volatility: Optional[float] = None,
        win_rate: Optional[float] = None,
        avg_win: Optional[float] = None,
        avg_loss: Optional[float] = None,
        risk_per_trade: Optional[float] = None
    ) -> int:
        """
        计算仓位大小
        
        Args:
            capital: 可用资金
            price: 当前价格
            volatility: 波动率（用于波动率调整法）
            win_rate: 胜率（用于凯利公式）
            avg_win: 平均盈利（用于凯利公式）
            avg_loss: 平均亏损（用于凯利公式）
            risk_per_trade: 单笔风险金额
            
        Returns:
            建议持仓股数
        """
        if self.method == PositionSizingMethod.FIXED:
            # 固定金额
            fixed_amount = self.params.get('fixed_amount', 100000)
            shares = int(fixed_amount / price)
            
        elif self.method == PositionSizingMethod.FIXED_PERCENT:
            # 固定比例
            position_pct = self.params.get('position_pct', 0.1)
            position_value = capital * position_pct
            shares = int(position_value / price)
            
        elif self.method == PositionSizingMethod.VOLATILITY:
            # 波动率调整
            if volatility is None or volatility == 0:
                volatility = 0.02  # 默认2%日波动
            target_volatility = self.params.get('target_volatility', 0.15)  # 目标年化波动15%
            position_value = capital * (target_volatility / (volatility * np.sqrt(252)))
            max_position_pct = self.params.get('max_position_pct', 0.3)
            position_value = min(position_value, capital * max_position_pct)
            shares = int(position_value / price)
            
        elif self.method == PositionSizingMethod.KELLY:
            # 凯利公式: f* = (p*b - q) / b
            # p: 胜率, q: 败率, b: 盈亏比
            if win_rate is None or avg_win is None or avg_loss is None or avg_loss == 0:
                # 使用默认参数
                win_rate = self.params.get('default_win_rate', 0.5)
                avg_win = self.params.get('default_avg_win', 0.05)
                avg_loss = self.params.get('default_avg_loss', 0.03)
            
            loss_rate = 1 - win_rate
            b = avg_win / avg_loss  # 盈亏比
            kelly_fraction = (win_rate * b - loss_rate) / b
            
            # 使用半凯利（更保守）
            kelly_fraction = max(0, kelly_fraction * 0.5)
            
            position_value = capital * kelly_fraction
            shares = int(position_value / price)
            
        elif self.method == PositionSizingMethod.RISK_PARITY:
            # 风险平价
            if risk_per_trade is None:
                risk_per_trade = capital * self.params.get('risk_per_trade_pct', 0.01)
            
            if volatility and volatility > 0:
                # 根据波动率调整仓位，使每个头寸的风险贡献相等
                position_value = risk_per_trade / (volatility * np.sqrt(252))
                shares = int(position_value / price)
            else:
                shares = 0
        else:
            shares = 0
        
        return max(0, shares)


class RiskManager:
    """
    风险管理器
    
    负责整体风险控制和监控
    """
    
    def __init__(self, limits: RiskLimits = None, position_sizer: PositionSizer = None):
        """
        初始化
        
        Args:
            limits: 风险控制参数
            position_sizer: 仓位计算器
        """
        self.limits = limits or RiskLimits()
        self.position_sizer = position_sizer or PositionSizer()
        
        # 状态追踪
        self.daily_pnl: Dict[str, float] = {}  # 日盈亏
        self.sector_exposure: Dict[str, float] = {}  # 行业敞口
        self.peak_equity: float = 0
        self.current_drawdown: float = 0
        
    def check_position_limit(self, symbol: str, current_position_value: float,
                            new_order_value: float, total_equity: float) -> bool:
        """
        检查单个持仓限制
        
        Returns:
            是否允许该订单
        """
        new_position_value = current_position_value + new_order_value
        position_pct = new_position_value / total_equity
        
        return position_pct <= self.limits.max_single_position_pct
    
    def check_total_position_limit(self, total_position_value: float, 
                                   total_equity: float) -> bool:
        """检查总持仓限制"""
        return (total_position_value / total_equity) <= self.limits.max_position_pct
    
    def check_sector_limit(self, sector: str, sector_value: float, 
                          new_order_value: float, total_equity: float) -> bool:
        """检查行业持仓限制"""
        new_sector_value = sector_value + new_order_value
        return (new_sector_value / total_equity) <= self.limits.max_sector_pct
    
    def check_drawdown_limit(self, current_equity: float) -> bool:
        """
        检查回撤限制
        
        Returns:
            是否触发回撤限制
        """
        if current_equity > self.peak_equity:
            self.peak_equity = current_equity
            self.current_drawdown = 0
        else:
            self.current_drawdown = (self.peak_equity - current_equity) / self.peak_equity
        
        return self.current_drawdown >= self.limits.max_drawdown_limit
    
    def check_daily_loss_limit(self, date: str, daily_pnl: float) -> bool:
        """
        检查日亏损限制
        
        Returns:
            是否触发日亏损限制
        """
        if date not in self.daily_pnl:
            self.daily_pnl[date] = 0
        
        self.daily_pnl[date] += daily_pnl
        
        # 需要传入总权益才能计算比例，这里简化处理
        return False
    
    def calculate_portfolio_risk(self, positions: Dict[str, Dict], 
                                 returns_data: pd.DataFrame) -> Dict[str, float]:
        """
        计算组合风险
        
        Args:
            positions: 持仓字典 {symbol: {quantity, price, value}}
            returns_data: 收益率数据
            
        Returns:
            风险指标字典
        """
        if not positions:
            return {'portfolio_var': 0, 'diversification_ratio': 0}
        
        symbols = list(positions.keys())
        weights = np.array([positions[s]['value'] for s in symbols])
        weights = weights / weights.sum()
        
        # 计算协方差矩阵
        cov_matrix = returns_data[symbols].cov() * 252  # 年化
        
        # 组合波动率
        portfolio_variance = np.dot(weights.T, np.dot(cov_matrix, weights))
        portfolio_volatility = np.sqrt(portfolio_variance)
        
        # 分散化比率
        individual_vols = np.array([returns_data[s].std() * np.sqrt(252) for s in symbols])
        weighted_avg_vol = np.dot(weights, individual_vols)
        diversification_ratio = weighted_avg_vol / portfolio_volatility if portfolio_volatility > 0 else 1
        
        # 组合VaR (95%)
        portfolio_var = 1.645 * portfolio_volatility
        
        return {
            'portfolio_volatility': portfolio_volatility,
            'portfolio_var': portfolio_var,
            'diversification_ratio': diversification_ratio,
            'concentration_risk': np.sum(weights ** 2)  # Herfindahl指数
        }
    
    def get_position_recommendation(self, symbol: str, current_data: pd.Series,
                                   portfolio_value: float, current_position: int = 0) -> Dict:
        """
        获取仓位建议
        
        Returns:
            包含建议仓位和风险评级的字典
        """
        price = current_data['close']
        volatility = current_data.get('volatility_20', 0.02)
        
        # 计算建议仓位
        recommended_shares = self.position_sizer.calculate_position_size(
            capital=portfolio_value,
            price=price,
            volatility=volatility
        )
        
        # 风险评估
        risk_score = self._calculate_risk_score(current_data)
        
        # 根据风险调整仓位
        if risk_score > 0.7:  # 高风险
            recommended_shares = int(recommended_shares * 0.5)
            risk_level = "High"
        elif risk_score > 0.4:  # 中等风险
            recommended_shares = int(recommended_shares * 0.8)
            risk_level = "Medium"
        else:
            risk_level = "Low"
        
        return {
            'recommended_shares': recommended_shares,
            'current_shares': current_position,
            'action': 'buy' if recommended_shares > current_position else 'hold',
            'risk_level': risk_level,
            'risk_score': risk_score
        }
    
    def _calculate_risk_score(self, data: pd.Series) -> float:
        """
        计算风险评分 (0-1)
        
        综合考虑波动率、趋势、流动性等因素
        """
        score = 0
        
        # 波动率风险 (权重30%)
        volatility = data.get('volatility_20', 0.02)
        vol_score = min(volatility * np.sqrt(252) / 0.5, 1.0)  # 年化波动50%为最高分
        score += vol_score * 0.3
        
        # 趋势风险 (权重20%)
        momentum = abs(data.get('momentum_20', 0))
        trend_score = min(momentum / 0.3, 1.0)  # 30%动量为最高分
        score += trend_score * 0.2
        
        # 流动性风险 (权重20%)
        volume_ratio = data.get('volume_ratio', 1)
        liquidity_score = max(0, 1 - volume_ratio) if volume_ratio < 1 else 0
        score += liquidity_score * 0.2
        
        # 均值回归风险 (权重30%)
        mean_reversion = abs(data.get('mean_reversion_20', 0))
        mr_score = min(mean_reversion / 0.1, 1.0)  # 偏离10%为最高分
        score += mr_score * 0.3
        
        return min(score, 1.0)
    
    def generate_risk_report(self) -> str:
        """生成风险报告"""
        report = []
        report.append("=" * 50)
        report.append("风险管理报告")
        report.append("=" * 50)
        report.append(f"\n当前回撤: {self.current_drawdown:.2%}")
        report.append(f"回撤限制: {self.limits.max_drawdown_limit:.2%}")
        report.append(f"回撤状态: {'⚠️ 已触发限制' if self.current_drawdown >= self.limits.max_drawdown_limit else '✅ 正常'}")
        
        report.append(f"\n行业敞口:")
        for sector, exposure in self.sector_exposure.items():
            report.append(f"  {sector}: {exposure:.2%}")
        
        report.append("\n" + "=" * 50)
        return "\n".join(report)


if __name__ == "__main__":
    # 测试风险管理
    rm = RiskManager()
    
    # 测试仓位计算
    sizer = PositionSizer(PositionSizingMethod.FIXED_PERCENT, {'position_pct': 0.2})
    shares = sizer.calculate_position_size(capital=1000000, price=100)
    print(f"建议仓位: {shares}股")
    
    # 测试风险检查
    can_trade = rm.check_position_limit(
        symbol='000001',
        current_position_value=200000,
        new_order_value=100000,
        total_equity=1000000
    )
    print(f"是否允许交易: {can_trade}")
