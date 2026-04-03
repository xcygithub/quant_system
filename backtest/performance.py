"""
绩效分析模块 - 计算回测的各项绩效指标
"""
import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional
from datetime import datetime
import matplotlib.pyplot as plt
import warnings
warnings.filterwarnings('ignore')


class PerformanceAnalyzer:
    """
    绩效分析器
    
    计算各类风险调整收益指标
    """
    
    def __init__(self, equity_curve: pd.DataFrame, trades: List[Any] = None, 
                 risk_free_rate: float = 0.03):
        """
        初始化
        
        Args:
            equity_curve: 权益曲线DataFrame，包含equity列
            trades: 成交记录列表
            risk_free_rate: 无风险利率（年化）
        """
        self.equity_curve = equity_curve.copy()
        self.trades = trades or []
        self.risk_free_rate = risk_free_rate
        
        # 计算收益率序列
        if 'return' not in self.equity_curve.columns:
            self.equity_curve['return'] = self.equity_curve['equity'].pct_change()
        
        self.returns = self.equity_curve['return'].dropna()
        self.total_days = len(self.equity_curve)
    
    def calculate_all_metrics(self) -> Dict[str, Any]:
        """计算所有绩效指标"""
        return {
            'returns': self.calculate_return_metrics(),
            'risk': self.calculate_risk_metrics(),
            'ratios': self.calculate_ratio_metrics(),
            'drawdown': self.calculate_drawdown_metrics(),
            'trades': self.calculate_trade_metrics()
        }
    
    def calculate_return_metrics(self) -> Dict[str, float]:
        """计算收益指标"""
        initial_equity = self.equity_curve['equity'].iloc[0]
        final_equity = self.equity_curve['equity'].iloc[-1]
        
        # 总收益率
        total_return = (final_equity - initial_equity) / initial_equity
        
        # 年化收益率
        years = self.total_days / 252
        annual_return = (1 + total_return) ** (1 / years) - 1 if years > 0 else 0
        
        # 月收益率
        monthly_returns = self._calc_monthly_returns()
        
        # 日收益率统计
        daily_mean = self.returns.mean()
        daily_std = self.returns.std()
        
        return {
            'total_return': total_return,
            'annual_return': annual_return,
            'daily_mean_return': daily_mean,
            'daily_std_return': daily_std,
            'monthly_returns': monthly_returns,
            'positive_days': (self.returns > 0).sum(),
            'negative_days': (self.returns < 0).sum()
        }
    
    def calculate_risk_metrics(self) -> Dict[str, float]:
        """计算风险指标"""
        # 年化波动率
        volatility = self.returns.std() * np.sqrt(252)
        
        # 下行波动率（只计算负收益的标准差）
        downside_returns = self.returns[self.returns < 0]
        downside_volatility = downside_returns.std() * np.sqrt(252) if len(downside_returns) > 0 else 0
        
        # 偏度（收益分布的不对称性）
        skewness = self.returns.skew()
        
        # 峰度（收益分布的尾部厚度）
        kurtosis = self.returns.kurtosis()
        
        # 在险价值VaR (95%置信度)
        var_95 = np.percentile(self.returns, 5)
        
        # 条件在险价值CVaR
        cvar_95 = self.returns[self.returns <= var_95].mean() if len(self.returns[self.returns <= var_95]) > 0 else var_95
        
        return {
            'volatility': volatility,
            'downside_volatility': downside_volatility,
            'skewness': skewness,
            'kurtosis': kurtosis,
            'var_95': var_95,
            'cvar_95': cvar_95
        }
    
    def calculate_ratio_metrics(self) -> Dict[str, float]:
        """计算风险调整收益比率"""
        annual_return = self.calculate_return_metrics()['annual_return']
        volatility = self.calculate_risk_metrics()['volatility']
        downside_volatility = self.calculate_risk_metrics()['downside_volatility']
        
        # 夏普比率
        sharpe_ratio = (annual_return - self.risk_free_rate) / volatility if volatility > 0 else 0
        
        # 索提诺比率（使用下行波动率）
        sortino_ratio = (annual_return - self.risk_free_rate) / downside_volatility if downside_volatility > 0 else 0
        
        # 卡玛比率（年化收益/最大回撤）
        max_dd = self.calculate_drawdown_metrics()['max_drawdown']
        calmar_ratio = annual_return / abs(max_dd) if max_dd != 0 else 0
        
        # 信息比率（相对于无风险利率的超额收益/跟踪误差）
        excess_returns = self.returns - self.risk_free_rate / 252
        tracking_error = excess_returns.std() * np.sqrt(252)
        information_ratio = excess_returns.mean() * 252 / tracking_error if tracking_error > 0 else 0
        
        # 特雷诺比率（需要市场组合数据，这里简化计算）
        treynor_ratio = annual_return / volatility if volatility > 0 else 0
        
        # Omega比率
        positive_returns = self.returns[self.returns > 0].sum()
        negative_returns = abs(self.returns[self.returns < 0].sum())
        omega_ratio = positive_returns / negative_returns if negative_returns > 0 else 0
        
        return {
            'sharpe_ratio': sharpe_ratio,
            'sortino_ratio': sortino_ratio,
            'calmar_ratio': calmar_ratio,
            'information_ratio': information_ratio,
            'treynor_ratio': treynor_ratio,
            'omega_ratio': omega_ratio
        }
    
    def calculate_drawdown_metrics(self) -> Dict[str, float]:
        """计算回撤指标"""
        # 计算回撤序列
        cummax = self.equity_curve['equity'].cummax()
        drawdown = (self.equity_curve['equity'] - cummax) / cummax
        
        # 最大回撤
        max_drawdown = drawdown.min()
        
        # 最大回撤持续时间
        max_dd_end_idx = drawdown.idxmin()
        max_dd_start_idx = cummax.loc[:max_dd_end_idx].idxmax()
        max_dd_duration = (max_dd_end_idx - max_dd_start_idx).days if hasattr(max_dd_end_idx, 'days') else 0
        
        # 平均回撤
        avg_drawdown = drawdown[drawdown < 0].mean()
        
        # 回撤恢复时间
        recovery_times = self._calc_recovery_times(drawdown)
        
        return {
            'max_drawdown': max_drawdown,
            'max_dd_start': max_dd_start_idx,
            'max_dd_end': max_dd_end_idx,
            'max_dd_duration': max_dd_duration,
            'avg_drawdown': avg_drawdown,
            'recovery_times': recovery_times,
            'drawdown_series': drawdown
        }
    
    def calculate_trade_metrics(self) -> Dict[str, Any]:
        """计算交易统计指标"""
        if not self.trades:
            return {'total_trades': 0}
        
        # 总交易次数
        total_trades = len(self.trades)
        
        # 盈利和亏损交易
        winning_trades = [t for t in self.trades if getattr(t, 'pnl', 0) > 0]
        losing_trades = [t for t in self.trades if getattr(t, 'pnl', 0) <= 0]
        
        # 胜率
        win_rate = len(winning_trades) / total_trades if total_trades > 0 else 0
        
        # 盈亏比
        avg_profit = np.mean([t.pnl for t in winning_trades]) if winning_trades else 0
        avg_loss = abs(np.mean([t.pnl for t in losing_trades])) if losing_trades else 1
        profit_factor = avg_profit / avg_loss if avg_loss > 0 else 0
        
        # 平均盈亏
        avg_trade_pnl = np.mean([t.pnl for t in self.trades])
        
        # 最大单笔盈利/亏损
        max_profit = max([t.pnl for t in winning_trades]) if winning_trades else 0
        max_loss = min([t.pnl for t in losing_trades]) if losing_trades else 0
        
        # 连续盈亏次数
        consecutive_wins, consecutive_losses = self._calc_consecutive_trades()
        
        return {
            'total_trades': total_trades,
            'winning_trades': len(winning_trades),
            'losing_trades': len(losing_trades),
            'win_rate': win_rate,
            'profit_factor': profit_factor,
            'avg_trade_pnl': avg_trade_pnl,
            'avg_profit': avg_profit,
            'avg_loss': avg_loss,
            'max_profit': max_profit,
            'max_loss': max_loss,
            'consecutive_wins': consecutive_wins,
            'consecutive_losses': consecutive_losses
        }
    
    def _calc_monthly_returns(self) -> pd.Series:
        """计算月收益率"""
        if 'date' not in self.equity_curve.columns:
            self.equity_curve['date'] = self.equity_curve.index
        
        self.equity_curve['date'] = pd.to_datetime(self.equity_curve['date'])
        self.equity_curve['year_month'] = self.equity_curve['date'].dt.to_period('M')
        
        monthly = self.equity_curve.groupby('year_month').agg({
            'equity': ['first', 'last']
        })
        monthly.columns = ['first', 'last']
        monthly['return'] = (monthly['last'] - monthly['first']) / monthly['first']
        
        return monthly['return']
    
    def _calc_recovery_times(self, drawdown: pd.Series) -> List[int]:
        """计算回撤恢复时间"""
        recovery_times = []
        in_drawdown = False
        dd_start = 0
        
        for i, dd in enumerate(drawdown):
            if dd < 0 and not in_drawdown:
                in_drawdown = True
                dd_start = i
            elif dd == 0 and in_drawdown:
                in_drawdown = False
                recovery_times.append(i - dd_start)
        
        return recovery_times
    
    def _calc_consecutive_trades(self) -> tuple:
        """计算最大连续盈亏次数"""
        if not self.trades:
            return 0, 0
        
        max_consecutive_wins = 0
        max_consecutive_losses = 0
        current_wins = 0
        current_losses = 0
        
        for trade in self.trades:
            pnl = getattr(trade, 'pnl', 0)
            if pnl > 0:
                current_wins += 1
                current_losses = 0
                max_consecutive_wins = max(max_consecutive_wins, current_wins)
            else:
                current_losses += 1
                current_wins = 0
                max_consecutive_losses = max(max_consecutive_losses, current_losses)
        
        return max_consecutive_wins, max_consecutive_losses
    
    def generate_report(self) -> str:
        """生成文字报告"""
        metrics = self.calculate_all_metrics()
        
        report = []
        report.append("=" * 60)
        report.append("策略回测绩效报告")
        report.append("=" * 60)
        
        # 收益指标
        returns = metrics['returns']
        report.append("\n【收益指标】")
        report.append(f"总收益率: {returns['total_return']:.2%}")
        report.append(f"年化收益率: {returns['annual_return']:.2%}")
        report.append(f"盈利天数: {returns['positive_days']}")
        report.append(f"亏损天数: {returns['negative_days']}")
        
        # 风险指标
        risk = metrics['risk']
        report.append("\n【风险指标】")
        report.append(f"年化波动率: {risk['volatility']:.2%}")
        report.append(f"下行波动率: {risk['downside_volatility']:.2%}")
        report.append(f"VaR (95%): {risk['var_95']:.2%}")
        report.append(f"CVaR (95%): {risk['cvar_95']:.2%}")
        
        # 比率指标
        ratios = metrics['ratios']
        report.append("\n【风险调整收益】")
        report.append(f"夏普比率: {ratios['sharpe_ratio']:.2f}")
        report.append(f"索提诺比率: {ratios['sortino_ratio']:.2f}")
        report.append(f"卡玛比率: {ratios['calmar_ratio']:.2f}")
        report.append(f"信息比率: {ratios['information_ratio']:.2f}")
        report.append(f"Omega比率: {ratios['omega_ratio']:.2f}")
        
        # 回撤指标
        drawdown = metrics['drawdown']
        report.append("\n【回撤分析】")
        report.append(f"最大回撤: {drawdown['max_drawdown']:.2%}")
        report.append(f"最大回撤持续时间: {drawdown['max_dd_duration']}天")
        report.append(f"平均回撤: {drawdown['avg_drawdown']:.2%}")
        
        # 交易统计
        trades = metrics['trades']
        report.append("\n【交易统计】")
        report.append(f"总交易次数: {trades['total_trades']}")
        if trades['total_trades'] > 0:
            report.append(f"胜率: {trades['win_rate']:.2%}")
            report.append(f"盈亏比: {trades['profit_factor']:.2f}")
            report.append(f"平均单笔盈亏: {trades['avg_trade_pnl']:.2f}")
            report.append(f"最大单笔盈利: {trades['max_profit']:.2f}")
            report.append(f"最大单笔亏损: {trades['max_loss']:.2f}")
        
        report.append("\n" + "=" * 60)
        
        return "\n".join(report)
    
    def plot_performance(self, save_path: str = None):
        """绘制绩效图表"""
        fig, axes = plt.subplots(3, 1, figsize=(12, 10))
        
        # 权益曲线
        ax1 = axes[0]
        ax1.plot(self.equity_curve.index, self.equity_curve['equity'], label='Strategy', linewidth=1.5)
        ax1.set_title('Equity Curve')
        ax1.set_ylabel('Equity')
        ax1.legend()
        ax1.grid(True, alpha=0.3)
        
        # 回撤曲线
        ax2 = axes[1]
        cummax = self.equity_curve['equity'].cummax()
        drawdown = (self.equity_curve['equity'] - cummax) / cummax
        ax2.fill_between(self.equity_curve.index, drawdown, 0, color='red', alpha=0.3)
        ax2.plot(self.equity_curve.index, drawdown, color='red', linewidth=1)
        ax2.set_title('Drawdown')
        ax2.set_ylabel('Drawdown')
        ax2.grid(True, alpha=0.3)
        
        # 收益分布
        ax3 = axes[2]
        ax3.hist(self.returns, bins=50, alpha=0.7, edgecolor='black')
        ax3.axvline(self.returns.mean(), color='red', linestyle='--', label=f'Mean: {self.returns.mean():.4f}')
        ax3.set_title('Return Distribution')
        ax3.set_xlabel('Daily Return')
        ax3.set_ylabel('Frequency')
        ax3.legend()
        ax3.grid(True, alpha=0.3)
        
        plt.tight_layout()
        
        if save_path:
            plt.savefig(save_path, dpi=150, bbox_inches='tight')
        else:
            plt.show()


if __name__ == "__main__":
    # 测试绩效分析
    # 创建模拟权益曲线
    dates = pd.date_range('2024-01-01', '2024-12-31', freq='D')
    np.random.seed(42)
    returns = np.random.normal(0.001, 0.02, len(dates))
    equity = 1000000 * (1 + returns).cumprod()
    
    equity_curve = pd.DataFrame({
        'date': dates,
        'equity': equity
    })
    
    analyzer = PerformanceAnalyzer(equity_curve)
    print(analyzer.generate_report())
