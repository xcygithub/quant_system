"""
策略基类 - 定义策略接口
"""
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from enum import Enum
import pandas as pd

class SignalType(Enum):
    """信号类型"""
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"
    CLOSE = "close"

@dataclass
class Signal:
    """交易信号"""
    symbol: str
    signal_type: SignalType
    strength: float = 1.0  # 信号强度 0-1
    price: Optional[float] = None
    quantity: Optional[float] = None
    metadata: Dict[str, Any] = None
    timestamp: Optional[pd.Timestamp] = None

class Strategy(ABC):
    """
    策略基类
    
    所有策略都需要继承此类并实现相应方法
    """
    
    def __init__(self, name: str = "BaseStrategy", params: Dict[str, Any] = None):
        """
        初始化策略
        
        Args:
            name: 策略名称
            params: 策略参数字典
        """
        self.name = name
        self.params = params or {}
        self.engine = None
        self.symbols: List[str] = []
        self.signals: List[Signal] = []
        
    def set_engine(self, engine):
        """设置回测引擎"""
        self.engine = engine
        
    def set_symbols(self, symbols: List[str]):
        """设置交易标的"""
        self.symbols = symbols
    
    @abstractmethod
    def on_bar(self, bar: pd.Series):
        """
        处理每个K线数据
        
        Args:
            bar: 当前K线数据
        """
        pass
    
    @abstractmethod
    def generate_signals(self, data: pd.DataFrame) -> List[Signal]:
        """
        生成交易信号
        
        Args:
            data: 历史数据
            
        Returns:
            信号列表
        """
        pass
    
    def on_start(self):
        """回测开始时的回调"""
        pass
    
    def on_stop(self):
        """回测结束时的回调"""
        pass
    
    def get_parameters(self) -> Dict[str, Any]:
        """获取策略参数"""
        return self.params.copy()
    
    def set_parameters(self, params: Dict[str, Any]):
        """设置策略参数"""
        self.params.update(params)
    
    def buy(self, symbol: str, quantity: float, **kwargs):
        """买入"""
        if self.engine:
            return self.engine.buy(symbol, quantity, **kwargs)
        return None
    
    def sell(self, symbol: str, quantity: float, **kwargs):
        """卖出"""
        if self.engine:
            return self.engine.sell(symbol, quantity, **kwargs)
        return None
    
    def close_position(self, symbol: str):
        """平仓"""
        if self.engine:
            self.engine.close_position(symbol)
    
    def get_position(self, symbol: str) -> Optional[Any]:
        """获取持仓"""
        if self.engine:
            return self.engine.get_position(symbol)
        return None
    
    def get_equity(self) -> float:
        """获取当前权益"""
        if self.engine:
            return self.engine.get_total_equity()
        return 0.0


class PortfolioStrategy(Strategy):
    """
    组合策略基类
    
    用于管理多个子策略的组合
    """
    
    def __init__(self, name: str = "PortfolioStrategy", params: Dict[str, Any] = None):
        super().__init__(name, params)
        self.strategies: List[Strategy] = []
        self.weights: Dict[str, float] = {}
        
    def add_strategy(self, strategy: Strategy, weight: float = 1.0):
        """
        添加子策略
        
        Args:
            strategy: 子策略实例
            weight: 权重
        """
        self.strategies.append(strategy)
        self.weights[strategy.name] = weight
        
        # 归一化权重
        total_weight = sum(self.weights.values())
        if total_weight > 0:
            for name in self.weights:
                self.weights[name] /= total_weight
    
    def on_bar(self, bar: pd.Series):
        """处理K线数据"""
        for strategy in self.strategies:
            strategy.on_bar(bar)
    
    def generate_signals(self, data: pd.DataFrame) -> List[Signal]:
        """生成组合信号"""
        all_signals = []
        
        for strategy in self.strategies:
            signals = strategy.generate_signals(data)
            weight = self.weights.get(strategy.name, 1.0 / len(self.strategies))
            
            # 调整信号强度
            for signal in signals:
                signal.strength *= weight
                all_signals.append(signal)
        
        return all_signals


if __name__ == "__main__":
    # 测试基类
    print("策略基类定义完成")
    print(f"信号类型: {[s.value for s in SignalType]}")
