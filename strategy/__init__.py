"""
策略模块 - 提供策略基类和示例策略
"""
from .base import Strategy, Signal
from .moving_average import MovingAverageCrossStrategy, MACDStrategy, BollingerBandsStrategy
from .multi_factor import MultiFactorStrategy, RSIStrategy
from .fundamental_factors import FundamentalFactors, calculate_factors, get_factor_panel
from .factor_preprocessor import FactorPreprocessor, FactorNeutralizer, preprocess_factors

__all__ = [
    'Strategy', 'Signal',
    'MovingAverageCrossStrategy', 'MACDStrategy', 'BollingerBandsStrategy',
    'MultiFactorStrategy', 'RSIStrategy',
    'FundamentalFactors', 'calculate_factors', 'get_factor_panel',
    'FactorPreprocessor', 'FactorNeutralizer', 'preprocess_factors',
]
