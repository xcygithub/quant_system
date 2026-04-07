"""
Portfolio - 组合管理模块
包含自选股管理、选股排序、仓位分配、多股票回测等功能
"""
from .watchlist import WatchlistManager, StockInfo, get_watchlist_manager
from .selector import StockSelector, StockScore, ScoringMethod, create_selector
from .position_sizer import PositionSizer, PositionResult, PositionMethod, create_position_sizer
from .multi_stock_backtest import MultiStockBacktest, run_multi_stock_backtest, PortfolioPosition, TradeRecord

__all__ = [
    # 自选股管理
    'WatchlistManager',
    'StockInfo',
    'get_watchlist_manager',
    # 选股模块
    'StockSelector',
    'StockScore',
    'ScoringMethod',
    'create_selector',
    # 仓位分配
    'PositionSizer',
    'PositionResult',
    'PositionMethod',
    'create_position_sizer',
    # 多股票回测
    'MultiStockBacktest',
    'run_multi_stock_backtest',
    'PortfolioPosition',
    'TradeRecord'
]
