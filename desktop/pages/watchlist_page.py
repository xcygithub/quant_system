"""
自选股管理页 (WatchlistPage) — UI 重设计版

基于「自选股管理 · UI 重设计方案 v1.0」全面重构。

核心改动：
1. 工具栏重构：合并「刷新行情」「批量刷新行情」为单一「刷新」按钮（走 Baostock），
   搜索框改为实时筛选，低频操作收纳到「更多 ▼」下拉菜单。
   注：原计划中的「自动刷新」ToggleSwitch 已删除（见 ISSUE-UI-04）。
2. 表格行内选中态：行首 Checkbox，选中行左侧 3px 蓝色竖线指示，
   底部浮出批量操作栏（已选 N 项 + 删除 + 导出）。
3. 删除操作改造：Checkbox 选中 → 底部批量操作栏 → 二次确认弹窗。
4. 顶部标题区改造：H1 样式左对齐，右侧仅保留全局操作入口。
5. 设计系统 token：颜色/字体/间距/圆角/阴影统一。
6. 设计原则：同样的功能只要一个地方实现（合并「导出本组回测」+ 底部「导出回测」为单一入口）。

替代 web/app.py 的「自选股管理」标签页。
"""
import logging
import os
from datetime import datetime, timedelta

import pandas as pd

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QGroupBox,
    QPushButton, QComboBox, QLineEdit, QCheckBox, QFormLayout,
    QScrollArea, QMenu, QToolButton, QSizePolicy, QAbstractItemView,
    QHeaderView, QStyledItemDelegate, QStyleOptionViewItem, QStyle,
    QMessageBox, QItemDelegate, QDialog, QDialogButtonBox,
)
from PySide6.QtCore import Qt, Signal, QTimer, QSortFilterProxyModel, QModelIndex
from PySide6.QtGui import QColor, QBrush, QAction, QPainter, QPen

logger = logging.getLogger(__name__)

from desktop.pages.base_page import BasePage
from desktop.widgets.stock_selector import StockSelector
from desktop.widgets.pandas_table import PandasTableView, make_change_color_rule
from desktop.widgets.metric_card import MetricCard
from desktop.widgets.message_bar import MessageBar, MessageHelper
from desktop.widgets.chart_container import ChartContainer
from desktop.widgets.async_worker import AsyncWorker, run_with_progress
from desktop.models.managers import Managers
from desktop.models.app_state import AppState

from data.data_provider import CacheOnlyProvider


GROUP_CHOICES = ["默认", "持仓股", "银行", "消费", "科技", "医药", "新能源", "自定义"]
SORT_CHOICES = ["涨跌幅从高到低", "涨跌幅从低到低", "成交量从高到低", "代码升序"]
PAGE_SIZES = [12, 20, 30, 50]
PERIOD_MAP = {"日K": "D", "周K": "W", "月K": "M", "年K": "Y"}


# ============ 模块级辅助函数（可在子线程执行）============

def _get_latest_quotes(db_path: str, symbols: list) -> list:
    """读取最近 30 天 K 线，计算每只股票最新价与涨跌幅。

    CacheOnlyProvider 每次调用自建 sqlite 连接，线程安全。
    返回顺序与 symbols 一致，元素为 dict: {symbol, close, pct_change, volume_wan}
    """
    end = datetime.now()
    start = end - timedelta(days=30)
    provider = CacheOnlyProvider(db_path)
    rows = []
    for sym in symbols:
        df = provider.get_stock_data(sym, start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"))
        if df is None or df.empty or len(df) < 1:
            rows.append({"symbol": sym, "close": None, "pct_change": None, "volume_wan": None})
            continue
        latest = df.iloc[-1]
        prev = df.iloc[-2] if len(df) > 1 else latest
        close = float(latest["close"]) if pd.notna(latest["close"]) else None
        prev_close = float(prev["close"]) if len(df) > 1 and pd.notna(prev["close"]) else None
        pct = ((close - prev_close) / prev_close * 100) if (close is not None and prev_close) else 0.0
        vol = float(latest["volume"]) if pd.notna(latest["volume"]) else 0.0
        rows.append({"symbol": sym, "close": close, "pct_change": pct, "volume_wan": vol / 10000.0})
    return rows


def _load_kline(db_path: str, symbol: str, start: str, end: str) -> pd.DataFrame:
    """从本地缓存读取单只股票 K 线数据（无网络）。"""
    provider = CacheOnlyProvider(db_path)
    return provider.get_stock_data(symbol, start, end)


def _batch_refresh_quotes(db_path: str, symbols: list,
                          progress_callback=None) -> dict:
    """批量从 Baostock 在线获取最近 K 线数据并写入本地缓存。"""
    from data.data_manager import DataManager

    dm = DataManager(db_path)
    total = len(symbols)
    success = 0
    failed = []
    try:
        for i, sym in enumerate(symbols):
            if progress_callback and not progress_callback(
                int(i / max(total, 1) * 100),
                f"正在更新 {sym} ({i+1}/{total})..."
            ):
                break
            try:
                dm.update_recent_data([sym], days=30)
                success += 1
            except Exception:
                failed.append(sym)
        if progress_callback:
            progress_callback(100, f"完成：成功 {success}，失败 {len(failed)}")
    finally:
        try:
            dm.close()
        except Exception:
            pass
    return {"success": success, "failed": failed}


def _resample_kline(df: pd.DataFrame, period: str) -> pd.DataFrame:
    """将日 K 重采样为周/月/年 K（日 K 直接返回）。"""
    if df is None or df.empty:
        return df
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date")
    if period == "W":
        rule = "W-FRI"
    elif period == "M":
        rule = "M"
    elif period == "Y":
        rule = "Y"
    else:
        return df.reset_index()
    agg = df.resample(rule).agg({
        "open": "first", "high": "max", "low": "min", "close": "last",
        "volume": "sum", "amount": "sum",
    }).dropna()
    return agg.reset_index()


# ============ Checkbox 表格模型 ============

class CheckableTableModel(QSortFilterProxyModel):
    """带 Checkbox 列的代理模型，支持行选中态管理。

    在原始 PandasTableModel 的基础上，第一列（index 0）为 Checkbox 列。
    选中状态通过 _checked_rows 集合管理。
    """

    def __init__(self, source_model, parent=None):
        super().__init__(parent)
        self.setSourceModel(source_model)
        self._checked_rows = set()  # 存储源模型行号

    def checked_rows(self) -> set:
        return self._checked_rows.copy()

    def checked_count(self) -> int:
        return len(self._checked_rows)

    def toggle_check(self, proxy_row: int):
        """切换某行的 Checkbox 状态"""
        source_row = self.mapToSource(self.index(proxy_row, 0)).row()
        if source_row in self._checked_rows:
            self._checked_rows.discard(source_row)
        else:
            self._checked_rows.add(source_row)
        # 通知视图更新该行
        idx = self.index(proxy_row, 0)
        self.dataChanged.emit(idx, idx)

    def set_all_checked(self, checked: bool):
        """全选/全不选"""
        if checked:
            self._checked_rows = set(range(self.sourceModel().rowCount()))
        else:
            self._checked_rows.clear()
        self.dataChanged.emit(
            self.index(0, 0),
            self.index(self.rowCount() - 1, 0)
        )

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        if index.column() == 0:
            # Checkbox 列
            source_row = self.mapToSource(index).row()
            if role == Qt.CheckStateRole:
                return Qt.Checked if source_row in self._checked_rows else Qt.Unchecked
            if role == Qt.TextAlignmentRole:
                return int(Qt.AlignCenter)
            return None
        # 其他列委托给源模型（偏移 1 列）
        source_index = self.sourceModel().index(
            self.mapToSource(index).row(), index.column() - 1
        )
        return self.sourceModel().data(source_index, role)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and section == 0 and role == Qt.DisplayRole:
            return ""
        if orientation == Qt.Horizontal and section > 0:
            return self.sourceModel().headerData(section - 1, orientation, role)
        return None

    def columnCount(self, parent=QModelIndex()):
        return super().columnCount(parent) + 1

    def flags(self, index):
        if not index.isValid():
            return Qt.NoItemFlags
        if index.column() == 0:
            return Qt.ItemIsEnabled | Qt.ItemIsUserCheckable
        return super().flags(index)

    def setData(self, index, value, role=Qt.EditRole):
        if index.column() == 0 and role == Qt.CheckStateRole:
            source_row = self.mapToSource(index).row()
            if value == Qt.Checked:
                self._checked_rows.add(source_row)
            else:
                self._checked_rows.discard(source_row)
            self.dataChanged.emit(index, index)
            return True
        return False


class CheckableTableView(PandasTableView):
    """带 Checkbox 列的表格视图

    Signals:
        selection_changed(int): 选中行数变化
    """
    selection_changed = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._proxy_model = None

    def set_checkable_data(self, df, formatters=None, color_rules=None,
                           auto_resize=False):
        """设置数据（带 Checkbox 列）"""
        from desktop.widgets.pandas_table import PandasTableModel
        source_model = PandasTableModel(df, formatters, color_rules)
        self._proxy_model = CheckableTableModel(source_model, self)
        self.setModel(self._proxy_model)

        # Checkbox 列宽
        header = self.horizontalHeader()
        header.resizeSection(0, 40)
        header.setSectionResizeMode(0, QHeaderView.Fixed)

        # 设置列宽
        _COL_WIDTHS = {
            "代码": 100, "名称": 130, "最新价": 90,
            "涨跌幅(%)": 90, "成交量(万)": 110, "分组": 80,
        }
        for col_idx in range(1, self._proxy_model.columnCount()):
            col_name = self._proxy_model.headerData(col_idx, Qt.Horizontal)
            w = _COL_WIDTHS.get(col_name, 80)
            header.resizeSection(col_idx, w)

        self.setSelectionMode(QAbstractItemView.NoSelection)
        self.setSelectionBehavior(QAbstractItemView.SelectItems)

    def _on_check_clicked(self, index):
        """点击 Checkbox 列时切换选中状态"""
        if index.column() == 0 and self._proxy_model:
            self._proxy_model.toggle_check(index.row())
            self.selection_changed.emit(self._proxy_model.checked_count())

    def mousePressEvent(self, event):
        index = self.indexAt(event.pos())
        if index.isValid() and index.column() == 0:
            self._on_check_clicked(index)
            return
        super().mousePressEvent(event)

    def get_checked_symbols(self) -> list:
        """获取选中行的股票代码列表"""
        if not self._proxy_model:
            return []
        source_model = self._proxy_model.sourceModel()
        symbols = []
        for row in self._proxy_model.checked_rows():
            # 代码列在源模型中是第0列
            idx = source_model.index(row, 0)
            val = source_model.data(idx, Qt.DisplayRole)
            if val:
                symbols.append(val)
        return symbols

    def get_checked_count(self) -> int:
        if not self._proxy_model:
            return 0
        return self._proxy_model.checked_count()

    def select_all(self):
        if self._proxy_model:
            self._proxy_model.set_all_checked(True)
            self.selection_changed.emit(self._proxy_model.checked_count())

    def deselect_all(self):
        if self._proxy_model:
            self._proxy_model.set_all_checked(False)
            self.selection_changed.emit(0)

    def row_double_clicked_signal(self, row_idx):
        """双击行跳转详情（跳过 Checkbox 列）"""
        # 从 proxy model 获取源行号
        if self._proxy_model:
            source_row = self._proxy_model.mapToSource(
                self._proxy_model.index(row_idx, 1)
            ).row()
            return source_row
        return row_idx


# ============ 自选股管理页 ============

class WatchlistPage(BasePage):
    """自选股管理页（列表 + 详情双视图）— UI 重设计版"""

    def __init__(self, parent=None):
        # 在 super().__init__() 触发 _build_content() 之前，先准备好依赖与状态
        self._state = AppState.instance()
        self._wl = Managers.instance().watchlist_manager
        self._db_path = Managers.instance().data_manager.db_path

        # 列表视图筛选状态
        self._view_mode = "list"
        self._group_filter = "全部"
        self._page_size = 20
        self._sort_by = SORT_CHOICES[0]
        self._keyword = ""
        self._page = 1
        self._selected_stock = ""
        self._all_rows = []        # 当前筛选 + 行情合并后的全部行（已排序）
        self._page_rows = []       # 当前页行
        self._quotes_token = 0     # 防止过期行情结果覆盖

        # 详情视图状态
        self._detail_symbol = ""
        self._detail_df = None
        self._detail_token = 0

        self._state.watchlist_changed.connect(self._on_watchlist_changed)
        super().__init__(title="自选股管理", subtitle="行情展示与分组管理", parent=parent)

    # ============ 构建内容 ============

    def _build_content(self):
        self._msg = MessageBar()
        self.content_layout.addWidget(self._msg)

        # 用 QScrollArea 包裹视图容器
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.content_layout.addWidget(self._scroll, 1)

        self._view_container = QWidget()
        self._view_container.setObjectName("watchlistViewContainer")
        self._view_layout = QVBoxLayout(self._view_container)
        self._view_layout.setContentsMargins(24, 16, 24, 16)  # --space-6
        self._view_layout.setSpacing(12)
        self._scroll.setWidget(self._view_container)

        self._render_list()

    # ============ 视图容器管理 ============

    def _clear_view(self):
        while self._view_layout.count():
            item = self._view_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

    @staticmethod
    def _clear_layout(layout):
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

    # ============ 列表视图 ============

    def _render_list(self):
        self._quotes_token += 1
        self._detail_token += 1
        self._view_mode = "list"
        self._clear_view()

        # --- 工具栏（新设计） ---
        # 设计原则：同样的功能只要一个地方实现
        # - 【刷新】= 唯一从 Baostock 在线拉取行情的入口（替代原"批量在线刷新"）
        # - 底部【导出回测】= 唯一标记用于回测的入口（无勾选导全组，有勾选导勾选）
        # - 【自动刷新】已删除（定时重复网络请求容易制造静默流量，且与手动刷新重叠）
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)

        # 刷新按钮（唯一刷新入口，走 Baostock）
        self._refresh_btn = QPushButton("刷新")
        self._refresh_btn.setObjectName("refreshBtn")
        self._refresh_btn.setToolTip("从 Baostock 在线拉取当前分组行情数据")
        self._refresh_btn.clicked.connect(self._on_refresh_quotes)
        self._refresh_btn.setMinimumWidth(72)
        toolbar.addWidget(self._refresh_btn)

        # 分隔线
        sep1 = QFrame()
        sep1.setObjectName("toolbarSeparator")
        sep1.setFrameShape(QFrame.VLine)
        toolbar.addWidget(sep1)

        # 搜索框（实时筛选）
        self._search_edit = QLineEdit()
        self._search_edit.setObjectName("searchEdit")
        self._search_edit.setPlaceholderText("搜索股票代码/名称...")
        self._search_edit.setText(self._keyword)
        self._search_edit.setMaximumWidth(280)
        self._search_edit.textChanged.connect(self._on_search_text_changed)
        toolbar.addWidget(self._search_edit)

        # 分组筛选下拉
        self._group_combo = QComboBox()
        self._group_combo.addItem("全部")
        self._group_combo.addItems(self._wl.get_groups())
        idx = self._group_combo.findText(self._group_filter)
        if idx >= 0:
            self._group_combo.setCurrentIndex(idx)
        self._group_combo.currentTextChanged.connect(self._on_group_filter_changed)
        self._group_combo.setMinimumWidth(100)
        toolbar.addWidget(self._group_combo)

        toolbar.addStretch(1)

        # 添加股票按钮
        add_btn = QPushButton("+ 添加股票")
        add_btn.setObjectName("primaryBtn")
        add_btn.clicked.connect(self._show_add_stock_dialog)
        toolbar.addWidget(add_btn)

        # 更多操作下拉（仅保留低频操作；行情刷新和回测导出已在工具栏/底部栏实现单一入口）
        more_btn = QToolButton()
        more_btn.setText("更多")
        more_btn.setPopupMode(QToolButton.InstantPopup)
        more_btn.setMinimumWidth(72)
        more_menu = QMenu(more_btn)

        action_export_csv = more_menu.addAction("导出 CSV")
        action_export_csv.triggered.connect(self._on_export_csv)

        more_btn.setMenu(more_menu)
        toolbar.addWidget(more_btn)

        self._view_layout.addLayout(toolbar)

        # --- 排序行 ---
        sort_bar = QHBoxLayout()
        sort_bar.setSpacing(8)

        sort_label = QLabel("排序:")
        sort_label.setStyleSheet("color: #6C757D; font-size: 12px;")
        sort_bar.addWidget(sort_label)

        sort_combo = QComboBox()
        sort_combo.addItems(SORT_CHOICES)
        sort_combo.setCurrentText(self._sort_by)
        sort_combo.currentTextChanged.connect(self._on_sort_changed)
        sort_bar.addWidget(sort_combo)

        size_label = QLabel("每页:")
        size_label.setStyleSheet("color: #6C757D; font-size: 12px;")
        sort_bar.addWidget(size_label)

        size_combo = QComboBox()
        for s in PAGE_SIZES:
            size_combo.addItem(str(s))
        size_combo.setCurrentText(str(self._page_size))
        size_combo.currentTextChanged.connect(self._on_page_size_changed)
        sort_bar.addWidget(size_combo)

        sort_bar.addStretch(1)

        # 全选 Checkbox
        self._select_all_cb = QCheckBox("全选")
        self._select_all_cb.stateChanged.connect(self._on_select_all_changed)
        sort_bar.addWidget(self._select_all_cb)

        self._view_layout.addLayout(sort_bar)

        # --- 行情总览行 ---
        self._overview_container = QWidget()
        self._overview_container.setLayout(QHBoxLayout())
        self._overview_container.layout().setSpacing(12)
        self._view_layout.addWidget(self._overview_container)

        # --- 表格容器 ---
        self._table_container = QWidget()
        self._table_container.setLayout(QVBoxLayout())
        self._table_container.layout().setContentsMargins(0, 0, 0, 0)
        self._table_container.layout().setSpacing(0)
        self._view_layout.addWidget(self._table_container, 1)

        # --- 底部：分页 + 批量操作浮栏 ---
        self._bottom_bar = QHBoxLayout()
        self._bottom_bar.setSpacing(12)

        # 分页区域
        self._pagination_container = QWidget()
        self._pagination_container.setLayout(QHBoxLayout())
        self._pagination_container.layout().setContentsMargins(0, 0, 0, 0)
        self._pagination_container.layout().setSpacing(8)
        self._bottom_bar.addWidget(self._pagination_container, 2)

        # 批量操作浮栏（选中股票后显示）
        self._batch_action_bar = QFrame()
        self._batch_action_bar.setObjectName("batchActionBar")
        batch_layout = QHBoxLayout(self._batch_action_bar)
        batch_layout.setContentsMargins(12, 8, 12, 8)
        batch_layout.setSpacing(8)

        self._batch_count_label = QLabel("已选 0 项")
        self._batch_count_label.setObjectName("batchCountLabel")
        batch_layout.addWidget(self._batch_count_label)

        batch_delete_btn = QPushButton("删除选中")
        batch_delete_btn.setObjectName("dangerBtn")
        batch_delete_btn.clicked.connect(self._on_batch_delete)
        batch_layout.addWidget(batch_delete_btn)

        batch_export_btn = QPushButton("导出回测")
        batch_export_btn.clicked.connect(self._on_batch_export)
        batch_layout.addWidget(batch_export_btn)

        self._batch_action_bar.setVisible(False)
        self._bottom_bar.addWidget(self._batch_action_bar, 3)

        self._view_layout.addLayout(self._bottom_bar)

        self._schedule_quotes_load()

    # ============ 搜索 ============

    def _on_search_text_changed(self, text: str):
        """实时筛选（搜索框文本变化时立即触发）"""
        self._keyword = text
        self._page = 1
        self._schedule_quotes_load()

    # ============ 行情加载 ============

    def _compute_filtered_stocks(self):
        if self._group_filter == "全部":
            stocks = self._wl.get_all_stocks()
        else:
            stocks = self._wl.get_stocks_by_group(self._group_filter)
        kw = self._keyword.strip().lower()
        if kw:
            stocks = [s for s in stocks if kw in s.symbol.lower() or kw in s.name.lower()]
        return [(s.symbol, s.name, s.group) for s in stocks]

    def _schedule_quotes_load(self, silent: bool = False):
        self._quotes_token += 1
        token = self._quotes_token
        stocks = self._compute_filtered_stocks()
        symbols = [s[0] for s in stocks]
        if not symbols:
            self._all_rows = []
            self._render_overview(self._all_rows)
            self._render_table_section()
            self._msg.info("当前分组无自选股，请先添加或调整筛选条件")
            return
        if not silent:
            self._msg.info(f"正在加载 {len(symbols)} 只股票行情...", auto_clear_ms=0)
            self._refresh_btn.setEnabled(False)
            self._refresh_btn.setText("刷新中...")
        worker = AsyncWorker(_get_latest_quotes, self._db_path, symbols, parent=self)
        worker.finished.connect(lambda rows: self._on_quotes_loaded(rows, stocks, token, silent))
        worker.error.connect(lambda e: self._on_quotes_load_error(e, silent))
        worker.start()

    def _on_quotes_load_error(self, error, silent: bool):
        if not silent:
            self._msg.error(f"行情加载失败: {error}")
            self._refresh_btn.setEnabled(True)
            self._refresh_btn.setText("刷新")

    def _on_quotes_loaded(self, quote_rows, stocks, token, silent: bool):
        if token != self._quotes_token:
            return
        # 恢复刷新按钮状态
        if not silent:
            self._refresh_btn.setEnabled(True)
            self._refresh_btn.setText("刷新")

        meta = {sym: (name, grp) for sym, name, grp in stocks}
        rows = []
        for q in quote_rows:
            sym = q["symbol"]
            name, grp = meta.get(sym, (sym, ""))
            rows.append({
                "symbol": sym, "name": name, "group": grp,
                "close": q["close"], "pct_change": q["pct_change"],
                "volume_wan": q["volume_wan"],
            })
        self._all_rows = self._sort_rows(rows)

        total = len(self._all_rows)
        pages = max((total + self._page_size - 1) // self._page_size, 1)
        if self._page > pages:
            self._page = pages
        if self._page < 1:
            self._page = 1

        self._render_overview(self._all_rows)
        self._render_table_section()

        # 根据数据完整性给出反馈
        missing = sum(1 for r in self._all_rows if r["close"] is None)
        if not silent:
            if missing == total and total > 0:
                self._msg.warning(
                    f"当前 {total} 只自选股均无本地行情数据，"
                    f"请点击「刷新」通过 Baostock 在线获取"
                )
            elif missing > 0:
                self._msg.warning(
                    f"{missing}/{total} 只股票行情缺失，"
                    f"可点击「刷新」补齐数据",
                    auto_clear_ms=8000,
                )
            else:
                self._msg.success(f"已加载 {total} 只股票行情")

    def _sort_rows(self, rows):
        if self._sort_by == "涨跌幅从高到低":
            return sorted(rows, key=lambda r: (r["pct_change"] is None,
                            -(r["pct_change"] if r["pct_change"] is not None else -999)))
        if self._sort_by == "涨跌幅从低到低":
            return sorted(rows, key=lambda r: (r["pct_change"] is None,
                            (r["pct_change"] if r["pct_change"] is not None else 999)))
        if self._sort_by == "成交量从高到低":
            return sorted(rows, key=lambda r: (r["volume_wan"] is None,
                            -(r["volume_wan"] if r["volume_wan"] is not None else -999)))
        return sorted(rows, key=lambda r: r["symbol"])

    def _render_overview(self, rows):
        try:
            layout = self._overview_container.layout()
        except RuntimeError:
            return
        self._clear_layout(layout)
        up = sum(1 for r in rows if r["pct_change"] is not None and r["pct_change"] > 0)
        down = sum(1 for r in rows if r["pct_change"] is not None and r["pct_change"] < 0)
        flat = sum(1 for r in rows if r["pct_change"] is not None and r["pct_change"] == 0)

        for c in [
            MetricCard("股票总数", str(len(rows))),
            MetricCard("上涨", str(up), delta_color="up"),
            MetricCard("下跌", str(down), delta_color="down"),
            MetricCard("平盘", str(flat), delta_color="neutral"),
        ]:
            layout.addWidget(c)
        layout.addStretch(1)

    def _render_table_section(self):
        try:
            layout = self._table_container.layout()
        except RuntimeError:
            return
        self._clear_layout(layout)

        rows = self._all_rows
        if not rows:
            empty_label = QLabel("暂无匹配的自选股，请调整筛选条件。")
            empty_label.setAlignment(Qt.AlignCenter)
            empty_label.setStyleSheet(
                "color: #6C757D; font-size: 14px; padding: 40px;"
            )
            layout.addWidget(empty_label)
            self._render_pagination(0, 1)
            return

        total = len(rows)
        pages = max((total + self._page_size - 1) // self._page_size, 1)
        start = (self._page - 1) * self._page_size
        page_rows = rows[start:start + self._page_size]
        self._page_rows = page_rows

        df = pd.DataFrame([{
            "代码": r["symbol"], "名称": r["name"], "最新价": r["close"],
            "涨跌幅(%)": r["pct_change"], "成交量(万)": r["volume_wan"], "分组": r["group"],
        } for r in page_rows])

        table = CheckableTableView()
        table.set_checkable_data(
            df,
            formatters={"最新价": "{:.2f}", "涨跌幅(%)": "{:+.2f}", "成交量(万)": "{:.1f}"},
            color_rules={"涨跌幅(%)": make_change_color_rule()},
            auto_resize=False,
        )
        table.selection_changed.connect(self._on_table_selection_changed)
        table.doubleClicked.connect(self._on_row_double_clicked)
        self._table = table

        table.setMinimumHeight(380)
        layout.addWidget(table, 1)

        # 数据缺失提示
        missing_in_page = sum(1 for r in page_rows if r["close"] is None)
        if page_rows and missing_in_page / len(page_rows) > 0.5:
            hint = QLabel(
                f"当前页 {len(page_rows)} 只股票中 {missing_in_page} 只"
                f"行情数据缺失。请点击「刷新」通过 Baostock 在线获取。"
            )
            hint.setWordWrap(True)
            hint.setStyleSheet(
                "QLabel { background-color: #FFF7ED; color: #92400E; "
                "border: 1px solid #FCD34D; border-radius: 4px; "
                "padding: 8px 12px; font-size: 13px; }"
            )
            layout.addWidget(hint)

        # 分页
        self._render_pagination(total, pages)

    def _render_pagination(self, total: int, pages: int):
        """渲染分页控件"""
        try:
            layout = self._pagination_container.layout()
        except RuntimeError:
            return
        self._clear_layout(layout)

        prev_btn = QPushButton("上一页")
        prev_btn.setEnabled(self._page > 1)
        prev_btn.clicked.connect(self._on_prev_page)
        layout.addWidget(prev_btn)

        page_label = QLabel(f"第 {self._page}/{pages} 页 · 共 {total} 只")
        page_label.setAlignment(Qt.AlignCenter)
        page_label.setStyleSheet("color: #6C757D; font-size: 12px; padding: 0 12px;")
        layout.addWidget(page_label)

        next_btn = QPushButton("下一页")
        next_btn.setEnabled(self._page < pages)
        next_btn.clicked.connect(self._on_next_page)
        layout.addWidget(next_btn)

    # ============ 表格选中态 ============

    def _on_table_selection_changed(self, count: int):
        """表格 Checkbox 选中变化时更新底部批量操作栏"""
        self._batch_count_label.setText(f"已选 {count} 项")
        self._batch_action_bar.setVisible(count > 0)

        # 同步全选 Checkbox 状态
        if hasattr(self, '_select_all_cb'):
            self._select_all_cb.blockSignals(True)
            total = len(self._page_rows) if self._page_rows else 0
            if count == 0:
                self._select_all_cb.setCheckState(Qt.Unchecked)
            elif count == total and total > 0:
                self._select_all_cb.setCheckState(Qt.Checked)
            else:
                self._select_all_cb.setCheckState(Qt.PartiallyChecked)
            self._select_all_cb.blockSignals(False)

    def _on_select_all_changed(self, state):
        """全选 Checkbox 状态变化"""
        if not hasattr(self, '_table'):
            return
        if state == Qt.Checked:
            self._table.select_all()
        else:
            self._table.deselect_all()

    def _on_row_double_clicked(self, index):
        """双击行跳转详情"""
        if not hasattr(self, '_table') or not self._table._proxy_model:
            return
        # 跳过 Checkbox 列（column 0）
        if index.column() == 0:
            return
        source_index = self._table._proxy_model.mapToSource(
            self._table._proxy_model.index(index.row(), 1)
        )
        row_idx = source_index.row()
        page_rows = getattr(self, "_page_rows", [])
        if 0 <= row_idx < len(page_rows):
            symbol = page_rows[row_idx]["symbol"]
            self._selected_stock = symbol
            self._render_detail(symbol)

    # ============ 批量操作 ============

    def _on_batch_delete(self):
        """批量删除选中股票（二次确认弹窗）"""
        if not hasattr(self, '_table'):
            return
        symbols = self._table.get_checked_symbols()
        if not symbols:
            self._msg.warning("请先选择要删除的股票")
            return
        confirmed = MessageHelper.confirm(
            self,
            "确认删除",
            f"确定删除 {len(symbols)} 只自选股？\n此操作不可撤销。",
            yes_text="删除",
            no_text="取消",
        )
        if confirmed:
            success = 0
            failed = 0
            for sym in symbols:
                if self._wl.remove_stock(sym):
                    success += 1
                else:
                    failed += 1
            self._state.watchlist_changed.emit(self._wl.get_all_symbols())
            if failed:
                self._msg.warning(f"已删除 {success} 只，{failed} 只删除失败")
            else:
                self._msg.success(f"已删除 {success} 只自选股")

    def _on_batch_export(self):
        """导出股票用于回测（唯一入口）

        - 有勾选时：导出勾选项
        - 无勾选时：导出当前筛选全组
        """
        if not hasattr(self, '_table'):
            return
        symbols = self._table.get_checked_symbols()
        if not symbols:
            # 无勾选 → 退化为导出全组（保持「全组导出」能力）
            rows = getattr(self, "_all_rows", [])
            symbols = [r["symbol"] for r in rows]
            if not symbols:
                self._msg.warning("当前没有可导出的股票")
                return
        self._state.selected_stocks = symbols
        self._state.set("multi_stock_symbols", symbols)
        self._msg.success(f"已选择 {len(symbols)} 只股票用于回测（切换到【策略回测】即可使用）")

    # ============ 列表交互 ============

    def _on_prev_page(self):
        if self._page > 1:
            self._page -= 1
            self._render_table_section()

    def _on_next_page(self):
        total = len(self._all_rows)
        pages = max((total + self._page_size - 1) // self._page_size, 1)
        if self._page < pages:
            self._page += 1
            self._render_table_section()

    def _on_group_filter_changed(self, text):
        self._group_filter = text
        self._page = 1
        self._schedule_quotes_load()

    def _on_page_size_changed(self, text):
        try:
            self._page_size = int(text)
        except ValueError:
            return
        self._page = 1
        self._render_table_section()

    def _on_sort_changed(self, text):
        self._sort_by = text
        if hasattr(self, "_all_rows") and self._all_rows:
            self._all_rows = self._sort_rows(self._all_rows)
            self._render_table_section()
        else:
            self._schedule_quotes_load()

    def _on_refresh_quotes(self):
        """【刷新】按钮：唯一从 Baostock 在线拉取行情的入口"""
        self._on_batch_refresh_quotes()

    def _on_batch_refresh_quotes(self):
        """批量从 Baostock 在线补齐当前筛选分组的最近行情数据。

        也是工具栏【刷新】按钮背后的实现，确保只有一个网络刷新入口。
        """
        stocks = self._compute_filtered_stocks()
        symbols = [s[0] for s in stocks]
        if not symbols:
            self._msg.warning("当前分组无自选股，请先添加")
            return

        # 工具栏【刷新】按钮的 loading 反馈
        self._refresh_btn.setEnabled(False)
        self._refresh_btn.setText("刷新中...")

        def _restore_btn():
            if self._refresh_btn:
                self._refresh_btn.setEnabled(True)
                self._refresh_btn.setText("刷新")

        worker = run_with_progress(
            self,
            _batch_refresh_quotes,
            self._db_path,
            symbols,
            title="刷新行情",
            message=f"正在更新 {len(symbols)} 只股票...",
            cancelable=True,
        )

        def _on_done(result):
            _restore_btn()
            ok = result.get("success", 0) if isinstance(result, dict) else 0
            failed = result.get("failed", []) if isinstance(result, dict) else []
            if failed:
                self._msg.warning(
                    f"完成 {ok} 只，失败 {len(failed)} 只：{', '.join(failed[:5])}"
                    + ("..." if len(failed) > 5 else ""),
                    auto_clear_ms=8000,
                )
            else:
                self._msg.success(f"已更新 {ok} 只股票行情")
            self._schedule_quotes_load()

        def _on_error(err):
            _restore_btn()
            self._msg.error(f"刷新失败: {err}")

        worker.finished.connect(_on_done)
        worker.error.connect(_on_error)

    # ============ 添加股票弹窗 ============

    def _show_add_stock_dialog(self):
        """弹出添加自选股对话框"""
        dialog = AddStockDialog(self)
        if dialog.exec() == AddStockDialog.Accepted:
            data = dialog.get_stock_data()
            ok = self._wl.add_stock(data["symbol"], data["name"], data["group"])
            if ok:
                self._msg.success(f"已添加 {data['symbol']}")
                self._state.watchlist_changed.emit(self._wl.get_all_symbols())
            else:
                self._msg.error("添加失败（可能已存在）")

    # ============ 导出 ============

    def _on_export_csv(self):
        """导出当前分组为 CSV 文件"""
        rows = getattr(self, "_all_rows", [])
        if not rows:
            self._msg.warning("当前没有可导出的数据")
            return
        df = pd.DataFrame([{
            "代码": r["symbol"], "名称": r["name"], "最新价": r["close"],
            "涨跌幅(%)": r["pct_change"], "成交量(万)": r["volume_wan"], "分组": r["group"],
        } for r in rows])
        filename = f"watchlist_{self._group_filter}_{datetime.now().strftime('%Y%m%d')}.csv"
        try:
            df.to_csv(filename, index=False, encoding="utf-8-sig")
            self._msg.success(f"已导出至 {filename}")
        except Exception as e:
            self._msg.error(f"导出失败: {e}")

    def _on_watchlist_changed(self, _symbols):
        if self._view_mode == "list":
            self._schedule_quotes_load()

    # ============ 详情视图 ============

    def _render_detail(self, symbol):
        self._quotes_token += 1
        self._view_mode = "detail"
        self._detail_symbol = symbol
        self._detail_df = None
        self._clear_view()

        # 工具栏
        tb = QHBoxLayout()
        back_btn = QPushButton("返回自选股列表")
        back_btn.clicked.connect(self._render_list)
        tb.addWidget(back_btn)

        sel = StockSelector(parent=self, label="切换股票")
        all_stocks = self._wl.get_all_stocks()
        name_map = {s.symbol: s.name for s in all_stocks}
        sel.set_stocks([s.symbol for s in all_stocks], name_map)
        sel.set_selected_stock(symbol)
        sel.stock_changed.connect(self._on_detail_symbol_changed)
        tb.addWidget(sel)

        refresh_btn = QPushButton("刷新数据")
        refresh_btn.clicked.connect(self._on_refresh_detail)
        tb.addWidget(refresh_btn)
        tb.addStretch(1)
        self._view_layout.addLayout(tb)

        self._view_layout.addWidget(QLabel(f"{symbol} 行情详情"))

        # 指标卡行
        self._detail_metric_container = QWidget()
        self._detail_metric_container.setLayout(QHBoxLayout())
        self._detail_metric_container.layout().setSpacing(12)
        self._view_layout.addWidget(self._detail_metric_container)

        # 周期选择
        period_bar = QHBoxLayout()
        period_combo = QComboBox()
        period_combo.addItems(list(PERIOD_MAP.keys()))
        period_combo.setCurrentText("日K")
        period_combo.currentTextChanged.connect(self._on_period_changed)
        self._period_combo = period_combo
        period_bar.addWidget(QLabel("K线周期"))
        period_bar.addWidget(period_combo)
        period_bar.addStretch(1)
        self._view_layout.addLayout(period_bar)

        # 图表
        self._chart = ChartContainer(title=f"{symbol} K线走势")
        self._chart.setMinimumHeight(420)
        self._view_layout.addWidget(self._chart, 1)

        # 数据表
        self._detail_table_container = QWidget()
        self._detail_table_container.setLayout(QVBoxLayout())
        self._detail_table_container.layout().setContentsMargins(0, 0, 0, 0)
        self._detail_table_container.layout().setSpacing(8)
        self._view_layout.addWidget(self._detail_table_container)

        self._load_detail()

    def _load_detail(self):
        try:
            self._chart.set_message("正在加载数据...")
        except RuntimeError:
            return
        self._detail_token += 1
        token = self._detail_token
        end = datetime.now()
        start = end - timedelta(days=365 * 3)
        worker = AsyncWorker(
            _load_kline, self._db_path, self._detail_symbol,
            start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"), parent=self,
        )
        worker.finished.connect(lambda df: self._on_detail_loaded(df, token))
        worker.error.connect(lambda e: (self._msg.error(f"数据加载失败: {e}"),
                                        self._chart.set_message(f"加载失败: {e}")))
        worker.start()

    def _on_detail_loaded(self, df, token):
        if token != self._detail_token:
            return
        self._detail_df = df
        if df is None or df.empty:
            self._chart.set_message(f"无法获取 {self._detail_symbol} 的数据")
            self._clear_layout(self._detail_metric_container.layout())
            self._render_detail_table(None)
            return
        self._render_detail_metrics(df)
        self._render_detail_chart()
        self._render_detail_table(df)

    def _render_detail_metrics(self, df):
        try:
            layout = self._detail_metric_container.layout()
        except RuntimeError:
            return
        self._clear_layout(layout)
        latest = df.iloc[-1]
        prev = df.iloc[-2] if len(df) > 1 else latest
        close = float(latest["close"]) if pd.notna(latest["close"]) else 0.0
        prev_close = float(prev["close"]) if len(df) > 1 and pd.notna(prev["close"]) else close
        change = close - prev_close
        change_pct = (change / prev_close * 100) if prev_close else 0.0
        volume = float(latest["volume"]) if pd.notna(latest["volume"]) else 0.0
        amount = float(latest["amount"]) if "amount" in df.columns and pd.notna(latest["amount"]) else 0.0
        for c in [
            MetricCard("最新价", f"{close:.2f}", delta=f"{change:+.2f}", delta_color="up" if change >= 0 else "down"),
            MetricCard("涨跌额", f"{change:+.2f}", delta_color="up" if change >= 0 else "down"),
            MetricCard("涨跌幅", f"{change_pct:+.2f}%", delta_color="up" if change >= 0 else "down"),
            MetricCard("成交量", f"{volume / 10000:.0f}万"),
            MetricCard("成交额", f"{amount / 100000000:.2f}亿"),
        ]:
            layout.addWidget(c)
        layout.addStretch(1)

    def _render_detail_chart(self):
        df = self._detail_df
        if df is None or df.empty:
            return
        period = PERIOD_MAP[self._period_combo.currentText()]
        disp = _resample_kline(df, period) if period != "D" else df.copy()
        try:
            from desktop.charts.kline_chart import build_kline_widget
            self._chart.set_plot_widget(
                build_kline_widget(disp, self._detail_symbol, period)
            )
        except Exception as e:
            self._chart.set_message(f"图表渲染失败: {e}")

    def _render_detail_table(self, df):
        try:
            layout = self._detail_table_container.layout()
        except RuntimeError:
            return
        self._clear_layout(layout)
        if df is None or df.empty:
            layout.addWidget(QLabel("暂无数据"))
            return
        show = df.sort_values("date", ascending=False).head(50).copy()
        table = PandasTableView()
        table.set_dataframe(
            show,
            formatters={
                "close": "{:.2f}", "open": "{:.2f}", "high": "{:.2f}", "low": "{:.2f}",
                "volume": "{:.0f}", "amount": "{:.0f}", "pct_change": "{:+.2f}",
            },
        )
        table.setMinimumHeight(260)
        layout.addWidget(table)

    def _on_period_changed(self, _text):
        self._render_detail_chart()

    def _on_detail_symbol_changed(self, symbol):
        if symbol and symbol != self._detail_symbol:
            self._render_detail(symbol)

    def _on_refresh_detail(self):
        self._msg.info(f"正在更新 {self._detail_symbol} 行情数据...", auto_clear_ms=0)
        db_path = self._db_path
        symbol = self._detail_symbol

        def _do():
            from data.data_manager import DataManager
            dm = DataManager(db_path)
            try:
                dm.update_recent_data([symbol], days=5)
            finally:
                try:
                    dm.close()
                except Exception:
                    pass
            return True

        worker = AsyncWorker(_do, parent=self)
        worker.finished.connect(lambda _: (self._msg.success("行情已更新"), self._load_detail()))
        worker.error.connect(lambda e: self._msg.error(f"更新失败: {e}"))
        worker.start()


# ============ 添加自选股对话框 ============

class AddStockDialog(QDialog):
    """添加自选股弹窗

    替代原方案中的折叠 GroupBox，使用独立对话框更清晰。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("添加自选股")
        self.setMinimumWidth(420)
        self._result_data = None

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # 自定义内容区域
        content = QWidget()
        form = QFormLayout(content)
        form.setContentsMargins(16, 16, 16, 8)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(8)

        self._symbol_edit = QLineEdit()
        self._symbol_edit.setPlaceholderText("如: 000001.SH / SH:601899 / 紫金矿业(SH:601899)")
        self._symbol_edit.setMinimumWidth(300)

        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("如: 平安银行（留空则智能推断）")

        self._group_combo = QComboBox()
        self._group_combo.addItems(GROUP_CHOICES)

        self._custom_edit = QLineEdit()
        self._custom_edit.setPlaceholderText("自定义分组名")
        self._custom_edit.setVisible(False)
        self._group_combo.currentTextChanged.connect(
            lambda t: self._custom_edit.setVisible(t == "自定义"))

        form.addRow("股票代码", self._symbol_edit)
        form.addRow("股票名称", self._name_edit)
        form.addRow("分组", self._group_combo)
        form.addRow("自定义分组", self._custom_edit)
        layout.addWidget(content)

        # 按钮区域
        button_box = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        button_box.button(QDialogButtonBox.Ok).setText("添加")
        button_box.button(QDialogButtonBox.Cancel).setText("取消")
        button_box.accepted.connect(self._on_accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _on_accept(self):
        symbol = self._symbol_edit.text().strip()
        if not symbol:
            self._symbol_edit.setStyleSheet("border: 1px solid #E24B4A;")
            return
        self._result_data = self.get_stock_data()
        self.accept()

    def get_stock_data(self) -> dict:
        symbol = self._symbol_edit.text().strip()
        name = self._name_edit.text().strip()
        group = self._group_combo.currentText()
        if group == "自定义":
            group = self._custom_edit.text().strip() or "默认"
        return {"symbol": symbol, "name": name, "group": group}
