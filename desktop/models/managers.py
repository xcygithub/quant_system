"""
共享服务容器 (Managers)

替代 Streamlit 的 @st.cache_resource 单例模式。在桌面应用中持有 DataManager、
WatchlistManager、FactorPresenter 等需要长连接/较重初始化的业务对象，统一 db_path，
供各页面通过 Managers.instance() 获取，避免每个页面重复 new（原 data_management 页重复 7 次）。

使用方式：
    from desktop.models.managers import Managers
    dm = Managers.instance().data_manager
    wl = Managers.instance().watchlist_manager
"""
from typing import Optional

from PySide6.QtCore import QObject


class Managers(QObject):
    """
    共享业务对象容器（单例）

    各页面通过 Managers.instance() 获取共享的 DataManager / WatchlistManager /
    FactorPresenter 等。所有对象惰性创建，首次访问时实例化。
    """

    _instance: Optional["Managers"] = None

    def __init__(self):
        super().__init__()
        self._dm = None
        self._wl = None
        self._fp = None

    @classmethod
    def instance(cls) -> "Managers":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """重置单例（仅用于测试）。会先关闭已持有的资源。"""
        if cls._instance is not None:
            cls._instance.close_all()
        cls._instance = None

    # === DataManager（行情/财务数据访问） ===
    @property
    def data_manager(self):
        if self._dm is None:
            from data.data_manager import DataManager
            self._dm = DataManager()
        return self._dm

    # === WatchlistManager（自选股） ===
    @property
    def watchlist_manager(self):
        if self._wl is None:
            from portfolio.watchlist import WatchlistManager
            self._wl = WatchlistManager()
        return self._wl

    # === FactorPresenter（因子查询/格式化） ===
    @property
    def factor_presenter(self):
        if self._fp is None:
            from web.factor_presenter import FactorPresenter
            self._fp = FactorPresenter()
        return self._fp

    def close_all(self):
        """关闭所有持有的资源（应用退出时调用）。"""
        for attr in ("_dm", "_wl", "_fp"):
            obj = getattr(self, attr, None)
            if obj is not None:
                try:
                    obj.close()
                except Exception:
                    pass
            setattr(self, attr, None)
