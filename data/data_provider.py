"""
数据提供者 - 分离数据获取策略

核心思想：
- 回测时使用 CacheOnlyProvider，只读数据库，不触发网络请求
- 更新数据时使用 OnlineProvider，走在线数据源
- 数据获取逻辑与回测引擎解耦
"""
import pandas as pd
from abc import ABC, abstractmethod
from typing import Dict, Optional
import sqlite3
from pathlib import Path


class DataProvider(ABC):
    """
    数据提供者抽象基类

    定义统一的数据获取接口，使回测引擎不关心数据来源（缓存/网络）
    """

    @abstractmethod
    def get_stock_data(self, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
        """
        获取股票数据

        Args:
            symbol: 股票代码
            start_date: 开始日期 (YYYY-MM-DD)
            end_date: 结束日期 (YYYY-MM-DD)

        Returns:
            DataFrame 包含 OHLCV 数据，或空 DataFrame
        """
        pass

    @abstractmethod
    def get_name(self) -> str:
        """获取提供者名称，用于日志和调试"""
        pass


class CacheOnlyProvider(DataProvider):
    """
    仅缓存数据提供者（回测专用）

    特点：
    - 只从本地 SQLite 数据库读取数据
    - 完全不触发网络请求
    - 适合回测场景，避免网络延迟和失败
    """

    def __init__(self, db_path: str):
        """
        初始化仅缓存提供者

        Args:
            db_path: SQLite 数据库路径
        """
        self.db_path = db_path

    def get_stock_data(self, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
        """
        从数据库读取 K 线数据

        Args:
            symbol: 股票代码
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            DataFrame 或空 DataFrame
        """
        conn = sqlite3.connect(self.db_path)
        query = """
            SELECT symbol, date, open, high, low, close, volume, amount,
                   turnover, amplitude, pct_change, change_amount
            FROM daily_kline
            WHERE symbol = ? AND date BETWEEN ? AND ?
            ORDER BY date
        """
        try:
            df = pd.read_sql_query(query, conn, params=(symbol, start_date, end_date))
            return df
        except Exception as e:
            print(f"[CacheOnlyProvider] 读取 {symbol} 数据失败: {e}")
            return pd.DataFrame()
        finally:
            conn.close()

    def get_name(self) -> str:
        return "CacheOnly"


class OnlineProvider(DataProvider):
    """
    在线数据提供者（数据更新专用）

    特点：
    - 优先从数据库读取，数据库数据不完整时从在线源获取
    - 会触发网络请求
    - 适合数据更新场景
    """

    def __init__(self, data_manager):
        """
        初始化在线提供者

        Args:
            data_manager: DataManager 实例
        """
        self.dm = data_manager

    def get_stock_data(self, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
        """
        从在线源获取数据（通过 DataManager）

        Args:
            symbol: 股票代码
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            DataFrame 或空 DataFrame
        """
        # 使用 DataManager 的 get_daily_kline，会触发在线获取
        df = self.dm.get_daily_kline(symbol, start_date, end_date)
        return df

    def get_name(self) -> str:
        return "Online"


class BacktestDataProvider:
    """
    回测数据提供者管理器

    封装数据获取逻辑，提供便捷的接口给回测引擎使用。
    支持两种模式：
    1. cache_only: 只读缓存（默认，推荐用于回测）
    2. online: 允许在线获取（用于数据更新）
    """

    def __init__(self, db_path: str, mode: str = "cache_only"):
        """
        初始化回测数据提供者

        Args:
            db_path: 数据库路径
            mode: "cache_only" 或 "online"
        """
        self.db_path = db_path
        self.mode = mode

        if mode == "cache_only":
            self._provider = CacheOnlyProvider(db_path)
        else:
            # online 模式需要 DataManager，先设置为 None
            self._provider = None
            self._dm = None

    def set_data_manager(self, dm):
        """设置 DataManager（用于 online 模式）"""
        self._dm = dm
        if self._provider is None and self._dm is not None:
            self._provider = OnlineProvider(self._dm)

    def get_stock_data(self, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
        """
        获取股票数据

        Args:
            symbol: 股票代码
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            DataFrame
        """
        return self._provider.get_stock_data(symbol, start_date, end_date)

    def get_multi_stock_data(
        self,
        symbols: list,
        start_date: str,
        end_date: str
    ) -> Dict[str, pd.DataFrame]:
        """
        批量获取多只股票数据

        Args:
            symbols: 股票代码列表
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            {symbol: dataframe} 字典
        """
        result = {}
        for symbol in symbols:
            df = self.get_stock_data(symbol, start_date, end_date)
            if not df.empty:
                result[symbol] = df
        return result

    @property
    def provider_name(self) -> str:
        """获取当前提供者名称"""
        return self._provider.get_name() if self._provider else "None"


# =============================================================================
# 便捷函数
# =============================================================================

def create_backtest_data_provider(
    db_path: str,
    mode: str = "cache_only",
    data_manager=None
) -> BacktestDataProvider:
    """
    创建回测数据提供者

    Args:
        db_path: 数据库路径
        mode: "cache_only" 或 "online"
        data_manager: DataManager 实例（online 模式需要）

    Returns:
        BacktestDataProvider 实例
    """
    provider = BacktestDataProvider(db_path, mode)
    if data_manager is not None:
        provider.set_data_manager(data_manager)
    return provider


if __name__ == "__main__":
    # 测试
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from config import DATABASE_PATH

    db_path = str(DATABASE_PATH)
    provider = create_backtest_data_provider(db_path, mode="cache_only")

    print(f"Provider: {provider.provider_name}")

    # 测试获取数据
    df = provider.get_stock_data("000001.SZ", "2024-01-01", "2024-03-19")
    print(f"获取到 {len(df)} 条数据" if not df.empty else "无数据")
