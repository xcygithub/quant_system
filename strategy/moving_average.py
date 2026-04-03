"""
移动平均线策略
"""
import pandas as pd
import numpy as np
from typing import List, Dict, Any
from .base import Strategy, Signal, SignalType


class MovingAverageCrossStrategy(Strategy):
    """
    均线交叉策略
    
    当短期均线上穿长期均线时买入，下穿时卖出
    """
    
    def __init__(self, params: Dict[str, Any] = None):
        """
        初始化
        
        Args:
            params: 参数字典
                - fast_period: 短期均线周期，默认20
                - slow_period: 长期均线周期，默认60
                - position_size: 仓位比例，默认1.0
        """
        default_params = {
            'fast_period': 20,
            'slow_period': 60,
            'position_size': 1.0
        }
        if params:
            default_params.update(params)
        super().__init__("MovingAverageCross", default_params)
        
    def on_bar(self, bar: pd.Series):
        """处理K线数据"""
        # 这里需要维护历史数据才能计算均线
        # 实际使用时需要在回测引擎中维护
        pass
    
    def generate_signals(self, data: pd.DataFrame) -> List[Signal]:
        """
        生成交易信号
        
        Args:
            data: 包含OHLCV数据的DataFrame
            
        Returns:
            信号列表
        """
        signals = []
        
        fast_period = self.params['fast_period']
        slow_period = self.params['slow_period']
        
        # 计算均线
        data['fast_ma'] = data['close'].rolling(window=fast_period).mean()
        data['slow_ma'] = data['close'].rolling(window=slow_period).mean()
        
        # 计算均线差值和信号
        data['ma_diff'] = data['fast_ma'] - data['slow_ma']
        data['signal'] = np.where(data['ma_diff'] > 0, 1, -1)
        data['signal_change'] = data['signal'].diff()
        
        # 生成交易信号
        for idx, row in data.iterrows():
            if pd.isna(row['signal_change']) or row['signal_change'] == 0:
                continue
                
            symbol = row.get('symbol', 'unknown')
            
            if row['signal_change'] == 2:  # -1 -> 1，金叉
                signals.append(Signal(
                    symbol=symbol,
                    signal_type=SignalType.BUY,
                    strength=1.0,
                    price=row['close'],
                    timestamp=idx if isinstance(idx, pd.Timestamp) else pd.to_datetime(row.get('date', idx))
                ))
            elif row['signal_change'] == -2:  # 1 -> -1，死叉
                signals.append(Signal(
                    symbol=symbol,
                    signal_type=SignalType.SELL,
                    strength=1.0,
                    price=row['close'],
                    timestamp=idx if isinstance(idx, pd.Timestamp) else pd.to_datetime(row.get('date', idx))
                ))
        
        return signals
    
    def get_signal_series(self, data: pd.DataFrame) -> pd.Series:
        """
        获取信号序列（用于向量化回测）
        
        Returns:
            信号序列 (-1, 0, 1)
        """
        fast_period = self.params['fast_period']
        slow_period = self.params['slow_period']
        
        data['fast_ma'] = data['close'].rolling(window=fast_period).mean()
        data['slow_ma'] = data['close'].rolling(window=slow_period).mean()
        
        signal = np.where(data['fast_ma'] > data['slow_ma'], 1, -1)
        return pd.Series(signal, index=data.index).fillna(0)


class MACDStrategy(Strategy):
    """
    MACD策略
    
    MACD柱状图由负转正买入，由正转负卖出
    """
    
    def __init__(self, params: Dict[str, Any] = None):
        """
        初始化
        
        Args:
            params: 参数字典
                - fast: 快线周期，默认12
                - slow: 慢线周期，默认26
                - signal: 信号线周期，默认9
        """
        default_params = {
            'fast': 12,
            'slow': 26,
            'signal': 9
        }
        if params:
            default_params.update(params)
        super().__init__("MACD", default_params)
    
    def on_bar(self, bar: pd.Series):
        pass
    
    def generate_signals(self, data: pd.DataFrame) -> List[Signal]:
        """生成MACD信号"""
        signals = []
        
        fast = self.params['fast']
        slow = self.params['slow']
        signal_period = self.params['signal']
        
        # 计算MACD
        ema_fast = data['close'].ewm(span=fast, adjust=False).mean()
        ema_slow = data['close'].ewm(span=slow, adjust=False).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal_period, adjust=False).mean()
        histogram = macd_line - signal_line
        
        # 生成信号
        prev_hist = histogram.shift(1)
        
        for idx, row in data.iterrows():
            hist = histogram.loc[idx]
            prev = prev_hist.loc[idx]
            
            if pd.isna(hist) or pd.isna(prev):
                continue
            
            symbol = row.get('symbol', 'unknown')
            
            # 柱状图由负转正
            if prev < 0 and hist > 0:
                signals.append(Signal(
                    symbol=symbol,
                    signal_type=SignalType.BUY,
                    strength=min(abs(hist) / abs(prev) if prev != 0 else 1, 2) / 2,
                    price=row['close'],
                    timestamp=idx if isinstance(idx, pd.Timestamp) else pd.to_datetime(row.get('date', idx))
                ))
            # 柱状图由正转负
            elif prev > 0 and hist < 0:
                signals.append(Signal(
                    symbol=symbol,
                    signal_type=SignalType.SELL,
                    strength=min(abs(hist) / abs(prev) if prev != 0 else 1, 2) / 2,
                    price=row['close'],
                    timestamp=idx if isinstance(idx, pd.Timestamp) else pd.to_datetime(row.get('date', idx))
                ))
        
        return signals
    
    def get_signal_series(self, data: pd.DataFrame) -> pd.Series:
        """获取信号序列"""
        fast = self.params['fast']
        slow = self.params['slow']
        signal_period = self.params['signal']
        
        ema_fast = data['close'].ewm(span=fast, adjust=False).mean()
        ema_slow = data['close'].ewm(span=slow, adjust=False).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal_period, adjust=False).mean()
        histogram = macd_line - signal_line
        
        signal = np.where(histogram > 0, 1, -1)
        return pd.Series(signal, index=data.index).fillna(0)


class BollingerBandsStrategy(Strategy):
    """
    布林带策略
    
    价格触及下轨买入，触及上轨卖出
    """
    
    def __init__(self, params: Dict[str, Any] = None):
        """
        初始化
        
        Args:
            params: 参数字典
                - period: 周期，默认20
                - std_dev: 标准差倍数，默认2.0
        """
        default_params = {
            'period': 20,
            'std_dev': 2.0
        }
        if params:
            default_params.update(params)
        super().__init__("BollingerBands", default_params)
    
    def on_bar(self, bar: pd.Series):
        pass
    
    def generate_signals(self, data: pd.DataFrame) -> List[Signal]:
        """生成布林带信号"""
        signals = []
        
        period = self.params['period']
        std_dev = self.params['std_dev']
        
        # 计算布林带
        middle = data['close'].rolling(window=period).mean()
        std = data['close'].rolling(window=period).std()
        upper = middle + std_dev * std
        lower = middle - std_dev * std
        
        # 生成信号
        for idx, row in data.iterrows():
            if pd.isna(upper.loc[idx]) or pd.isna(lower.loc[idx]):
                continue
            
            symbol = row.get('symbol', 'unknown')
            close = row['close']
            
            # 价格低于下轨
            if close < lower.loc[idx]:
                # 计算偏离程度作为信号强度
                deviation = (lower.loc[idx] - close) / std.loc[idx] if std.loc[idx] > 0 else 0
                signals.append(Signal(
                    symbol=symbol,
                    signal_type=SignalType.BUY,
                    strength=min(deviation, 1.0),
                    price=close,
                    timestamp=idx if isinstance(idx, pd.Timestamp) else pd.to_datetime(row.get('date', idx))
                ))
            # 价格高于上轨
            elif close > upper.loc[idx]:
                deviation = (close - upper.loc[idx]) / std.loc[idx] if std.loc[idx] > 0 else 0
                signals.append(Signal(
                    symbol=symbol,
                    signal_type=SignalType.SELL,
                    strength=min(deviation, 1.0),
                    price=close,
                    timestamp=idx if isinstance(idx, pd.Timestamp) else pd.to_datetime(row.get('date', idx))
                ))
        
        return signals
    
    def get_signal_series(self, data: pd.DataFrame) -> pd.Series:
        """获取信号序列"""
        period = self.params['period']
        std_dev = self.params['std_dev']
        
        middle = data['close'].rolling(window=period).mean()
        std = data['close'].rolling(window=period).std()
        upper = middle + std_dev * std
        lower = middle - std_dev * std
        
        signal = np.where(data['close'] < lower, 1, 
                         np.where(data['close'] > upper, -1, 0))
        return pd.Series(signal, index=data.index).fillna(0)


if __name__ == "__main__":
    # 测试策略
    from quant_system.data.data_manager import DataManager
    
    dm = DataManager()
    df = dm.get_daily_kline("000001", "2024-01-01", "2024-12-31")
    
    if not df.empty:
        # 测试均线策略
        ma_strategy = MovingAverageCrossStrategy({'fast_period': 10, 'slow_period': 30})
        signals = ma_strategy.generate_signals(df)
        print(f"均线策略生成 {len(signals)} 个信号")
        for sig in signals[:5]:
            print(f"  {sig.timestamp}: {sig.signal_type.value} @ {sig.price:.2f}")
        
        # 测试MACD策略
        macd_strategy = MACDStrategy()
        signals = macd_strategy.generate_signals(df)
        print(f"\nMACD策略生成 {len(signals)} 个信号")
        for sig in signals[:5]:
            print(f"  {sig.timestamp}: {sig.signal_type.value} @ {sig.price:.2f}")
