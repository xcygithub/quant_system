"""
数据模块 - 负责行情数据、财务数据的获取和管理
"""
from .data_manager import DataManager
from .factor_data import FactorData
from .data_sources import (
    MultiDataSource,
    AkshareDataSource,
    BaostockDataSource,
    EastmoneyDataSource,
    CSVDataSource,
    SimulatedDataSource
)
from .financial_data_source import FinancialDataSource
from .financial_data_saver import FinancialDataSaver
from .financial_data_manager import FinancialDataManager

__all__ = [
    'DataManager',
    'FactorData',
    'MultiDataSource',
    'AkshareDataSource',
    'BaostockDataSource',
    'EastmoneyDataSource',
    'CSVDataSource',
    'SimulatedDataSource',
    'FinancialDataSource',
    'FinancialDataSaver',
    'FinancialDataManager',
]
