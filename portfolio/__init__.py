"""
Portfolio - 组合管理模块
包含自选股管理、选股排序、仓位分配、多股票回测、信号扫描、全市场扫描、IC分析、多因子回测等功能
"""
from .watchlist import WatchlistManager, StockInfo, get_watchlist_manager
from .selector import StockSelector, StockScore, ScoringMethod, create_selector
from .position_sizer import PositionSizer, PositionResult, PositionMethod, create_position_sizer
from .multi_stock_backtest import MultiStockBacktest, run_multi_stock_backtest, PortfolioPosition, TradeRecord

# signal_scanner depends on strategy modules - handle circular import gracefully
try:
    from .signal_scanner import SignalScanner, ScanResult, ScanSignal, scan_watchlist
    _has_signal_scanner = True
except (ImportError, ModuleNotFoundError):
    _has_signal_scanner = False

from .stock_scanner import MarketStockScanner, scan_market
from .ic_analyzer import ICAnalyzer, calculate_factor_ic, get_ic_report
from .factor_quantile_analysis import FactorQuantileAnalysis, ICAnalysisVisualizer
from .factor_signal_generator import FactorSignalGenerator, create_signal_generator
from .factor_exposure_tracker import FactorExposureTracker, ExposureVisualizer
from .factor_ic_configurator import FactorICConfigurator, ICStatsCalculator
from .multi_factor_backtest import MultiFactorBacktest, run_multi_factor_backtest
from .backtest_report import BacktestReport, QuantileReturnsAnalyzer

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
    'TradeRecord',
    # 信号扫描 (optional - may fail if strategy modules not available)
    'SignalScanner',
    'ScanResult',
    'ScanSignal',
    'scan_watchlist',
    # 全市场扫描
    'MarketStockScanner',
    'scan_market',
    # IC分析
    'ICAnalyzer',
    'calculate_factor_ic',
    'get_ic_report',
    # 因子分层回测
    'FactorQuantileAnalysis',
    'ICAnalysisVisualizer',
    # Phase 4: 多因子回测
    'FactorSignalGenerator',
    'create_signal_generator',
    'FactorExposureTracker',
    'ExposureVisualizer',
    'FactorICConfigurator',
    'ICStatsCalculator',
    'MultiFactorBacktest',
    'run_multi_factor_backtest',
    'BacktestReport',
    'QuantileReturnsAnalyzer',
]
