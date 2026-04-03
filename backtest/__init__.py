"""
回测模块 - 提供事件驱动和向量化回测引擎
"""
from .engine import BacktestEngine, VectorizedBacktest
from .performance import PerformanceAnalyzer

__all__ = ['BacktestEngine', 'VectorizedBacktest', 'PerformanceAnalyzer']
