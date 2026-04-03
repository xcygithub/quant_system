"""
策略模块 - 提供策略基类和示例策略
"""
from .base import Strategy, Signal
from .moving_average import MovingAverageCrossStrategy, MACDStrategy, BollingerBandsStrategy
from .multi_factor import MultiFactorStrategy, RSIStrategy

__all__ = ['Strategy', 'Signal', 'MovingAverageCrossStrategy', 'MACDStrategy', 
           'BollingerBandsStrategy', 'MultiFactorStrategy', 'RSIStrategy']
