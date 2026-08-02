"""
全局应用状态管理 (AppState)

替代 Streamlit 的 st.session_state，使用 QObject 信号槽机制实现跨页面状态共享。
设计原则：
- 每个功能域有独立的属性和信号
- 状态变化通过信号通知，View 层订阅信号自动刷新
- 替代 st.rerun() 的整页刷新，改为局部信号触发

阶段2扩展：基于 web 屄 session_state 键分析，提取跨页面共享状态：
- selected_stock: 当前选中股票（app.py 等多处引用）
- scan_result: 信号扫描结果
- multi_backtest_results: 多股票回测结果
- mfbt_results: 多因子回测结果
- backtest_running/progress: 回测运行状态与进度（替代 mfbt_running/mfbt_progress）
"""
from typing import Any, Optional, Set
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
    watchlist_changed = Signal(list)               # 自选股列表变化
    selected_stock_changed = Signal(str)           # 当前选中股票变化
    backtest_result_changed = Signal(dict)         # 回测结果变化
    backtest_params_changed = Signal(dict)         # 回测参数变化
    selected_stocks_changed = Signal(list)         # 回测选中的股票集合变化
    factor_config_changed = Signal(dict)           # 因子配置变化
    data_updated = Signal(str)                     # 数据更新通知 (symbol)

    # === 阶段2新增信号 ===
    scan_result_changed = Signal(object)           # 信号扫描结果变化
    scan_stocks_changed = Signal(list)             # 扫描选中股票变化
    multi_backtest_results_changed = Signal(dict)  # 多股票回测结果变化
    mfbt_results_changed = Signal(object)          # 多因子回测结果变化
    backtest_running_changed = Signal(bool)        # 回测运行状态变化
    backtest_progress_changed = Signal(int, str)   # 回测进度变化(pct, msg)

    def __init__(self):
        super().__init__()
        # === 自选股 ===
        self._watchlist: list = []
        self._selected_stocks: list = []

        # === 当前选中股票（跨页面共享，如行情页/回测页联动） ===
        self._selected_stock: str = ""

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

        # === 信号扫描 ===
        self._scan_result = None
        self._scan_selected_stocks: set = set()

        # === 多股票回测 ===
        self._multi_backtest_results: dict = {}
        self._is_multi_factor_backtest: bool = False

        # === 多因子回测 ===
        self._mfbt_results = None
        self._mfbt_config: dict = {}

        # === 回测运行状态（替代 mfbt_running/mfbt_progress） ===
        self._backtest_running: bool = False
        self._backtest_progress: int = 0
        self._backtest_status_msg: str = ""

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

    # === 选中股票（回测用） ===
    @property
    def selected_stocks(self) -> list:
        return self._selected_stocks

    @selected_stocks.setter
    def selected_stocks(self, stocks: list):
        self._selected_stocks = list(stocks)
        self.selected_stocks_changed.emit(self._selected_stocks)

    # === 当前选中股票（跨页面共享） ===
    @property
    def selected_stock(self) -> str:
        return self._selected_stock

    @selected_stock.setter
    def selected_stock(self, symbol: str):
        if self._selected_stock != symbol:
            self._selected_stock = symbol
            self.selected_stock_changed.emit(symbol)

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

    # === 信号扫描结果 ===
    @property
    def scan_result(self):
        return self._scan_result

    @scan_result.setter
    def scan_result(self, result):
        self._scan_result = result
        self.scan_result_changed.emit(result)

    @property
    def scan_selected_stocks(self) -> set:
        return self._scan_selected_stocks

    @scan_selected_stocks.setter
    def scan_selected_stocks(self, stocks):
        self._scan_selected_stocks = set(stocks)
        self.scan_stocks_changed.emit(list(self._scan_selected_stocks))

    # === 多股票回测结果 ===
    @property
    def multi_backtest_results(self) -> dict:
        return self._multi_backtest_results

    @multi_backtest_results.setter
    def multi_backtest_results(self, results: dict):
        self._multi_backtest_results = results
        self.multi_backtest_results_changed.emit(results)

    @property
    def is_multi_factor_backtest(self) -> bool:
        return self._is_multi_factor_backtest

    @is_multi_factor_backtest.setter
    def is_multi_factor_backtest(self, val: bool):
        self._is_multi_factor_backtest = val

    # === 多因子回测结果 ===
    @property
    def mfbt_results(self):
        return self._mfbt_results

    @mfbt_results.setter
    def mfbt_results(self, results):
        self._mfbt_results = results
        self.mfbt_results_changed.emit(results)

    @property
    def mfbt_config(self) -> dict:
        return self._mfbt_config

    @mfbt_config.setter
    def mfbt_config(self, config: dict):
        self._mfbt_config = dict(config)

    # === 回测运行状态（替代 mfbt_running/mfbt_progress） ===
    @property
    def backtest_running(self) -> bool:
        return self._backtest_running

    @backtest_running.setter
    def backtest_running(self, running: bool):
        self._backtest_running = running
        self.backtest_running_changed.emit(running)

    @property
    def backtest_progress(self) -> int:
        return self._backtest_progress

    def set_backtest_progress(self, percent: int, message: str = ""):
        """更新回测进度（替代 st.progress + st.session_state.mfbt_progress）"""
        self._backtest_progress = percent
        self._backtest_status_msg = message
        self.backtest_progress_changed.emit(percent, message)

    def cancel_backtest(self):
        """请求取消回测"""
        self._backtest_running = False
        self.backtest_running_changed.emit(False)

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
