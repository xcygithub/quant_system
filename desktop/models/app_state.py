"""
全局应用状态管理 (AppState)

替代 Streamlit 的 st.session_state，使用 QObject 信号槽机制实现跨页面状态共享。
设计原则：
- 每个功能域有独立的属性和信号
- 状态变化通过信号通知，View 层订阅信号自动刷新
- 替代 st.rerun() 的整页刷新，改为局部信号触发
"""
from typing import Any, Optional
from PySide6.QtCore import QObject, Signal


class AppState(QObject):
    """
    全局应用状态单例

    替代 Streamlit session_state 的全局字典。
    通过 Qt 信号实现状态变更通知，View 层连接信号后自动刷新。

    使用方式：
        state = AppState.instance()  # 获取单例
        state.watchlist = ["000001.SZ", "600000.SH"]  # 设置属性，自动触发信号
        # View 层连接信号：
        state.watchlist_changed.connect(self._refresh_list)
    """

    # === 信号定义（状态变化时触发） ===
    watchlist_changed = Signal(list)          # 自选股列表变化
    backtest_result_changed = Signal(dict)    # 回测结果变化
    backtest_params_changed = Signal(dict)    # 回测参数变化
    selected_stocks_changed = Signal(list)    # 选中股票变化
    factor_config_changed = Signal(dict)      # 因子配置变化
    data_updated = Signal(str)                # 数据更新通知 (symbol)

    def __init__(self):
        super().__init__()
        # === 自选股 ===
        self._watchlist: list = []
        self._selected_stocks: list = []

        # === 回测 ===
        self._backtest_result: dict = {}
        self._backtest_params: dict = {
            "initial_capital": 1000000,
            "commission_rate": 0.0003,
            "max_positions": 5,
            "rebalance_days": 5,
            "stop_loss": 0.0,
            "min_holding_days": 0,
        }

        # === 因子配置 ===
        self._factor_config: dict = {}

        # === 通用键值存储（兼容过渡期） ===
        self._extra: dict = {}

    # === 单例模式 ===
    _instance: Optional["AppState"] = None

    @classmethod
    def instance(cls) -> "AppState":
        """获取 AppState 单例"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """重置单例（仅用于测试）"""
        cls._instance = None

    # === 自选股 ===
    @property
    def watchlist(self) -> list:
        return self._watchlist

    @watchlist.setter
    def watchlist(self, stocks: list):
        self._watchlist = list(stocks)
        self.watchlist_changed.emit(self._watchlist)

    # === 选中股票 ===
    @property
    def selected_stocks(self) -> list:
        return self._selected_stocks

    @selected_stocks.setter
    def selected_stocks(self, stocks: list):
        self._selected_stocks = list(stocks)
        self.selected_stocks_changed.emit(self._selected_stocks)

    # === 回测结果 ===
    @property
    def backtest_result(self) -> dict:
        return self._backtest_result

    @backtest_result.setter
    def backtest_result(self, result: dict):
        self._backtest_result = result
        self.backtest_result_changed.emit(result)

    # === 回测参数 ===
    @property
    def backtest_params(self) -> dict:
        return self._backtest_params

    @backtest_params.setter
    def backtest_params(self, params: dict):
        self._backtest_params = {**self._backtest_params, **params}
        self.backtest_params_changed.emit(self._backtest_params)

    def update_backtest_param(self, key: str, value: Any):
        """更新单个回测参数"""
        self._backtest_params[key] = value
        self.backtest_params_changed.emit(self._backtest_params)

    # === 因子配置 ===
    @property
    def factor_config(self) -> dict:
        return self._factor_config

    @factor_config.setter
    def factor_config(self, config: dict):
        self._factor_config = dict(config)
        self.factor_config_changed.emit(self._factor_config)

    # === 通用键值存储 ===
    def get(self, key: str, default: Any = None) -> Any:
        """获取通用状态值（兼容 session_state 迁移过渡期）"""
        return self._extra.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """设置通用状态值"""
        self._extra[key] = value

    def has(self, key: str) -> bool:
        """检查键是否存在"""
        return key in self._extra

    def remove(self, key: str) -> None:
        """删除键"""
        self._extra.pop(key, None)

    # === 数据更新通知 ===
    def notify_data_updated(self, symbol: str):
        """通知某只股票的数据已更新"""
        self.data_updated.emit(symbol)
