"""
数据模块 - 负责行情数据、财务数据的获取和管理

职责划分：
- DataManager: 数据库初始化和统一入口
- KlineManager: 日线/分钟线数据管理
- FactorManager: 因子数据管理
- FinancialDataManager: 财务数据管理
- CachePolicy: 缓存策略（完整性检查）
- DataProvider: 数据提供者（分离数据获取策略）
"""
from .data_manager import DataManager
from .kline_manager import KlineManager
from .factor_manager import FactorManager
from .cache_policy import CachePolicy
from .factor_data import FactorData
from .data_sources import (
    MultiDataSource,
    AkshareDataSource,
    BaostockDataSource,
    EastmoneyDataSource,
    CSVDataSource,
    SimulatedDataSource
)
from .data_provider import (
    DataProvider,
    CacheOnlyProvider,
    OnlineProvider,
    BacktestDataProvider,
    create_backtest_data_provider
)
from .financial_data_source import FinancialDataSource
from .financial_data_saver import FinancialDataSaver
from .financial_data_manager import FinancialDataManager

__all__ = [
    # 核心类
    'DataManager',
    'KlineManager',
    'FactorManager',
    'CachePolicy',
    'FactorData',
    # 数据源
    'MultiDataSource',
    'AkshareDataSource',
    'BaostockDataSource',
    'EastmoneyDataSource',
    'CSVDataSource',
    'SimulatedDataSource',
    # 数据提供者
    'DataProvider',
    'CacheOnlyProvider',
    'OnlineProvider',
    'BacktestDataProvider',
    'create_backtest_data_provider',
    # 财务数据
    'FinancialDataSource',
    'FinancialDataSaver',
    'FinancialDataManager',
]
