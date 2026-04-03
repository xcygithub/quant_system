"""
多因子策略
"""
import pandas as pd
import numpy as np
from typing import List, Dict, Any
from .base import Strategy, Signal, SignalType


class MultiFactorStrategy(Strategy):
    """
    多因子选股策略
    
    综合多个因子进行选股和择时
    """
    
    def __init__(self, params: Dict[str, Any] = None):
        """
        初始化
        
        Args:
            params: 参数字典
                - factors: 因子列表及权重
                - top_n: 选股数量
                - rebalance_freq: 调仓频率（天）
                - stop_loss: 止损比例
                - take_profit: 止盈比例
        """
        default_params = {
            'factors': {
                'momentum_20': 0.3,    # 20日动量
                'mean_reversion': 0.2,  # 均值回归
                'rsi': 0.2,            # RSI
                'volume_ratio': 0.15,  # 量比
                'trend_strength': 0.15 # 趋势强度
            },
            'top_n': 10,
            'rebalance_freq': 20,
            'stop_loss': 0.08,
            'take_profit': 0.15
        }
        if params:
            default_params.update(params)
        super().__init__("MultiFactor", default_params)
        
        self.last_rebalance = None
        self.holdings = {}  # 当前持仓
    
    def on_bar(self, bar: pd.Series):
        """处理K线数据"""
        current_date = bar.get('date')
        if isinstance(current_date, str):
            current_date = pd.to_datetime(current_date)
        
        symbol = bar.get('symbol', 'unknown')
        
        # 检查是否需要调仓
        if self.last_rebalance is None or \
           (current_date - self.last_rebalance).days >= self.params['rebalance_freq']:
            self._rebalance(bar)
            self.last_rebalance = current_date
        
        # 检查止损止盈
        if symbol in self.holdings:
            entry_price = self.holdings[symbol]['entry_price']
            current_price = bar['close']
            
            # 计算盈亏比例
            pnl_pct = (current_price - entry_price) / entry_price
            
            # 止损
            if pnl_pct < -self.params['stop_loss']:
                self.close_position(symbol)
                del self.holdings[symbol]
            # 止盈
            elif pnl_pct > self.params['take_profit']:
                self.close_position(symbol)
                del self.holdings[symbol]
    
    def _rebalance(self, bar: pd.Series):
        """执行调仓"""
        # 这里需要获取全市场数据才能进行选股
        # 简化版本：根据当前bar的因子值判断
        pass
    
    def generate_signals(self, data: pd.DataFrame) -> List[Signal]:
        """
        生成多因子信号
        
        对每个交易日，计算综合因子得分，生成买卖信号
        """
        signals = []
        factors = self.params['factors']
        
        # 计算各因子
        data = self._calculate_factors(data)
        
        # 计算综合得分
        data['score'] = 0
        for factor_name, weight in factors.items():
            if factor_name in data.columns:
                # 标准化因子值
                factor_mean = data[factor_name].mean()
                factor_std = data[factor_name].std()
                if factor_std > 0:
                    normalized = (data[factor_name] - factor_mean) / factor_std
                    data['score'] += normalized * weight
        
        # 生成信号
        score_mean = data['score'].mean()
        score_std = data['score'].std()
        
        for idx, row in data.iterrows():
            if pd.isna(row['score']):
                continue
            
            symbol = row.get('symbol', 'unknown')
            score = row['score']
            
            # 得分高于均值+1个标准差，买入
            if score > score_mean + score_std:
                signals.append(Signal(
                    symbol=symbol,
                    signal_type=SignalType.BUY,
                    strength=min((score - score_mean) / score_std / 2, 1.0) if score_std > 0 else 0.5,
                    price=row['close'],
                    timestamp=idx if isinstance(idx, pd.Timestamp) else pd.to_datetime(row.get('date', idx))
                ))
            # 得分低于均值-1个标准差，卖出
            elif score < score_mean - score_std:
                signals.append(Signal(
                    symbol=symbol,
                    signal_type=SignalType.SELL,
                    strength=min((score_mean - score) / score_std / 2, 1.0) if score_std > 0 else 0.5,
                    price=row['close'],
                    timestamp=idx if isinstance(idx, pd.Timestamp) else pd.to_datetime(row.get('date', idx))
                ))
        
        return signals
    
    def _calculate_factors(self, data: pd.DataFrame) -> pd.DataFrame:
        """计算所有因子"""
        df = data.copy()
        
        # 动量因子
        df['momentum_20'] = df['close'].pct_change(20)
        df['momentum_60'] = df['close'].pct_change(60)
        
        # 均值回归因子
        sma_20 = df['close'].rolling(20).mean()
        df['mean_reversion'] = (df['close'] - sma_20) / sma_20
        
        # RSI因子
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['rsi'] = 100 - (100 / (1 + rs))
        # 转换为反向因子（低RSI买入）
        df['rsi'] = 50 - df['rsi']
        
        # 量比因子
        vol_sma = df['volume'].rolling(20).mean()
        df['volume_ratio'] = df['volume'] / vol_sma
        
        # 趋势强度因子
        returns = df['close'].pct_change()
        df['trend_strength'] = (returns > 0).rolling(20).sum() / 20
        
        # 波动率因子
        df['volatility'] = returns.rolling(20).std()
        
        return df
    
    def get_signal_series(self, data: pd.DataFrame) -> pd.Series:
        """获取信号序列"""
        data = self._calculate_factors(data)
        
        factors = self.params['factors']
        data['score'] = 0
        for factor_name, weight in factors.items():
            if factor_name in data.columns:
                factor_mean = data[factor_name].mean()
                factor_std = data[factor_name].std()
                if factor_std > 0:
                    normalized = (data[factor_name] - factor_mean) / factor_std
                    data['score'] += normalized * weight
        
        score_mean = data['score'].mean()
        score_std = data['score'].std()
        
        signal = np.where(data['score'] > score_mean + score_std, 1,
                         np.where(data['score'] < score_mean - score_std, -1, 0))
        return pd.Series(signal, index=data.index).fillna(0)


class RSIStrategy(Strategy):
    """
    RSI策略
    
    RSI超卖买入，超买卖出
    """
    
    def __init__(self, params: Dict[str, Any] = None):
        """
        初始化
        
        Args:
            params: 参数字典
                - period: RSI周期，默认14
                - oversold: 超卖阈值，默认30
                - overbought: 超买阈值，默认70
        """
        default_params = {
            'period': 14,
            'oversold': 30,
            'overbought': 70
        }
        if params:
            default_params.update(params)
        super().__init__("RSI", default_params)
    
    def on_bar(self, bar: pd.Series):
        pass
    
    def generate_signals(self, data: pd.DataFrame) -> List[Signal]:
        """生成RSI信号"""
        signals = []
        
        period = self.params['period']
        oversold = self.params['oversold']
        overbought = self.params['overbought']
        
        # 计算RSI
        delta = data['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        
        # 生成信号
        prev_rsi = rsi.shift(1)
        
        for idx, row in data.iterrows():
            current_rsi = rsi.loc[idx]
            previous_rsi = prev_rsi.loc[idx]
            
            if pd.isna(current_rsi) or pd.isna(previous_rsi):
                continue
            
            symbol = row.get('symbol', 'unknown')
            
            # RSI从超卖区上穿
            if previous_rsi < oversold and current_rsi >= oversold:
                signals.append(Signal(
                    symbol=symbol,
                    signal_type=SignalType.BUY,
                    strength=(oversold - previous_rsi) / oversold if oversold > 0 else 0.5,
                    price=row['close'],
                    timestamp=idx if isinstance(idx, pd.Timestamp) else pd.to_datetime(row.get('date', idx))
                ))
            # RSI从超买区下穿
            elif previous_rsi > overbought and current_rsi <= overbought:
                signals.append(Signal(
                    symbol=symbol,
                    signal_type=SignalType.SELL,
                    strength=(previous_rsi - overbought) / (100 - overbought) if overbought < 100 else 0.5,
                    price=row['close'],
                    timestamp=idx if isinstance(idx, pd.Timestamp) else pd.to_datetime(row.get('date', idx))
                ))
        
        return signals
    
    def get_signal_series(self, data: pd.DataFrame) -> pd.Series:
        """获取信号序列"""
        period = self.params['period']
        oversold = self.params['oversold']
        overbought = self.params['overbought']
        
        delta = data['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        
        signal = np.where(rsi < oversold, 1, np.where(rsi > overbought, -1, 0))
        return pd.Series(signal, index=data.index).fillna(0)


if __name__ == "__main__":
    # 测试多因子策略
    from quant_system.data.data_manager import DataManager
    
    dm = DataManager()
    df = dm.get_daily_kline("000001", "2024-01-01", "2024-12-31")
    
    if not df.empty:
        # 测试多因子策略
        strategy = MultiFactorStrategy()
        signals = strategy.generate_signals(df)
        print(f"多因子策略生成 {len(signals)} 个信号")
        for sig in signals[:5]:
            print(f"  {sig.timestamp}: {sig.signal_type.value} 强度{sig.strength:.2f} @ {sig.price:.2f}")
        
        # 测试RSI策略
        rsi_strategy = RSIStrategy()
        signals = rsi_strategy.generate_signals(df)
        print(f"\nRSI策略生成 {len(signals)} 个信号")
        for sig in signals[:5]:
            print(f"  {sig.timestamp}: {sig.signal_type.value} @ {sig.price:.2f}")
