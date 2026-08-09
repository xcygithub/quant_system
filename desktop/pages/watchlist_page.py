"""
自选股管理页 (WatchlistPage) — 阶段3迁移（原 Tab1 / web/app.py）

替代 web/app.py 的「自选股管理」标签页。原实现通过 st.session_state 维护
watchlist_view_mode（list / detail）、selected_stock、分页状态，并依赖
st.rerun 做整页重渲染。桌面版改用：

- 页面内 view_container 切换「列表视图 / 详情视图」（不再 rerun）
- AppState.watchlist_changed 信号驱动列表刷新（其他页面增删自选股时联动）
- 行情读取在子线程执行（CacheOnlyProvider 自建连接，避免跨线程 SQLite）

功能：
- 列表视图：添加自选股、分组/排序/关键字筛选、分页、行情总览、删除、导出本组
- 详情视图：多周期 K 线、核心行情指标、数据表、刷新数据
"""
import logging
from datetime import datetime, timedelta

import pandas as pd

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QGroupBox,
    QPushButton, QComboBox, QLineEdit, QCheckBox, QFormLayout,
    QScrollArea,
)
from PySide6.QtCore import Qt

logger = logging.getLogger(__name__)

from desktop.pages.base_page import BasePage
from desktop.widgets.stock_selector import StockSelector
from desktop.widgets.pandas_table import PandasTableView, make_change_color_rule
from desktop.widgets.metric_card import MetricCard
from desktop.widgets.message_bar import MessageBar
from desktop.widgets.chart_container import ChartContainer
from desktop.widgets.async_worker import AsyncWorker, run_with_progress
from desktop.models.managers import Managers
from desktop.models.app_state import AppState

from data.data_provider import CacheOnlyProvider


GROUP_CHOICES = ["默认", "持仓股", "银行", "消费", "科技", "医药", "新能源", "自定义"]
SORT_CHOICES = ["涨跌幅从高到低", "涨跌幅从低到高", "成交量从高到低", "代码升序"]
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
    """批量从 Baostock 在线获取最近 K 线数据并写入本地缓存。

    在子线程中执行（通过 ProgressWorker），自建 DataManager 连接，
    避免跨线程 SQLite 复用主线程实例。

    Args:
        db_path: 数据库路径
        symbols: 股票代码列表
        progress_callback: (percent, message) -> bool；返回 False 表示取消

    Returns:
        {"success": int, "failed": list} 统计
    """
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
        # 最后一帧
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


# 阶段4：原 plotly 版 _make_kline_figure 已迁移到
# desktop/charts/kline_chart.py 的 build_kline_widget（pyqtgraph 原生）


class WatchlistPage(BasePage):
    """自选股管理页（列表 + 详情双视图）"""

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

        # 用 QScrollArea 包裹视图容器，避免窗口缩小时控件被截断/重叠
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.content_layout.addWidget(self._scroll, 1)

        self._view_container = QWidget()
        self._view_container.setObjectName("watchlistViewContainer")
        self._view_layout = QVBoxLayout(self._view_container)
        self._view_layout.setContentsMargins(8, 8, 8, 8)
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
        # 自增 token：让仍在运行的行情/K线 worker 完成后直接 return，
        # 避免其回调访问已被 _clear_view 删除的列表/详情控件（竞态崩溃）
        self._quotes_token += 1
        self._detail_token += 1
        self._view_mode = "list"
        self._clear_view()

        # --- 添加自选股（默认折叠，避免占用过多垂直空间）---
        add_box = QGroupBox("➕ 添加自选股")
        add_box.setCheckable(True)
        add_box.setChecked(False)
        add_box_layout = QVBoxLayout(add_box)
        add_box_layout.setContentsMargins(12, 8, 12, 12)
        add_box_layout.setSpacing(6)

        # 表单容器（折叠/展开受 add_box.toggled 控制，
        # 解决 PySide6 上 setChecked(False) 在某些版本不会自动折叠内容的问题）
        self._add_form_widget = QWidget()
        add_form = QFormLayout(self._add_form_widget)
        add_form.setContentsMargins(0, 0, 0, 0)
        add_form.setHorizontalSpacing(12)
        add_form.setVerticalSpacing(6)
        add_form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self._add_symbol_edit = QLineEdit()
        self._add_symbol_edit.setPlaceholderText("如: 000001.SH / SH:601899 / 紫金矿业(SH:601899)")
        self._add_symbol_edit.setMaximumWidth(280)
        self._add_name_edit = QLineEdit()
        self._add_name_edit.setPlaceholderText("如: 平安银行（留空则智能推断）")
        self._add_name_edit.setMaximumWidth(280)
        self._add_group_combo = QComboBox()
        self._add_group_combo.addItems(GROUP_CHOICES)
        self._add_group_combo.setMaximumWidth(180)
        self._add_custom_edit = QLineEdit()
        self._add_custom_edit.setPlaceholderText("自定义分组名")
        self._add_custom_edit.setMaximumWidth(180)
        self._add_custom_edit.setVisible(False)
        self._add_group_combo.currentTextChanged.connect(
            lambda t: self._add_custom_edit.setVisible(t == "自定义"))
        add_btn = QPushButton("添加")
        add_btn.clicked.connect(self._on_add_stock)
        add_form.addRow("股票代码", self._add_symbol_edit)
        add_form.addRow("股票名称", self._add_name_edit)
        add_form.addRow("分组", self._add_group_combo)
        add_form.addRow("自定义分组", self._add_custom_edit)
        add_form.addRow(add_btn)
        add_box_layout.addWidget(self._add_form_widget)

        # 显式同步折叠状态（避免依赖 Qt 自动行为）
        def _on_add_box_toggled(checked: bool):
            self._add_form_widget.setVisible(checked)
        add_box.toggled.connect(_on_add_box_toggled)
        _on_add_box_toggled(False)  # 初始隐藏表单
        self._view_layout.addWidget(add_box)

        # --- 筛选工具栏 ---
        filter_bar = QHBoxLayout()
        filter_bar.setSpacing(10)

        self._group_combo = QComboBox()
        self._group_combo.addItem("全部")
        self._group_combo.addItems(self._wl.get_groups())
        idx = self._group_combo.findText(self._group_filter)
        if idx >= 0:
            self._group_combo.setCurrentIndex(idx)
        self._group_combo.currentTextChanged.connect(self._on_group_filter_changed)

        size_combo = QComboBox()
        for s in PAGE_SIZES:
            size_combo.addItem(str(s))
        size_combo.setCurrentText(str(self._page_size))
        size_combo.currentTextChanged.connect(self._on_page_size_changed)

        sort_combo = QComboBox()
        sort_combo.addItems(SORT_CHOICES)
        sort_combo.setCurrentText(self._sort_by)
        sort_combo.currentTextChanged.connect(self._on_sort_changed)

        self._keyword_edit = QLineEdit()
        self._keyword_edit.setPlaceholderText("搜索代码/名称")
        self._keyword_edit.setText(self._keyword)
        self._keyword_edit.editingFinished.connect(self._on_keyword_changed)

        filter_bar.addLayout(self._labeled(self._group_combo, "筛选分组"))
        filter_bar.addLayout(self._labeled(size_combo, "每页条数"))
        filter_bar.addLayout(self._labeled(sort_combo, "排序方式"))
        filter_bar.addLayout(self._labeled(self._keyword_edit, "搜索"))
        filter_bar.addStretch(1)
        self._view_layout.addLayout(filter_bar)

        # --- 行情总览行 ---
        self._overview_container = QWidget()
        self._overview_container.setLayout(QHBoxLayout())
        self._overview_container.layout().setSpacing(12)
        self._view_layout.addWidget(self._overview_container)

        # --- 操作按钮 ---
        op_bar = QHBoxLayout()
        refresh_btn = QPushButton("🔄 刷新行情")
        refresh_btn.clicked.connect(self._on_refresh_quotes)
        refresh_btn.setToolTip("重新读取本地缓存的最新行情")
        batch_btn = QPushButton("📡 批量刷新行情")
        batch_btn.clicked.connect(self._on_batch_refresh_quotes)
        batch_btn.setToolTip("通过 Baostock 在线获取当前筛选分组的最近行情数据")
        export_btn = QPushButton("导出本组用于回测")
        export_btn.clicked.connect(self._on_export_group)
        op_bar.addWidget(refresh_btn)
        op_bar.addWidget(batch_btn)
        op_bar.addWidget(export_btn)
        op_bar.addStretch(1)
        self._view_layout.addLayout(op_bar)

        # --- 表格容器（动态填充） ---
        self._table_container = QWidget()
        self._table_container.setLayout(QVBoxLayout())
        self._table_container.layout().setContentsMargins(0, 0, 0, 0)
        self._table_container.layout().setSpacing(8)
        self._view_layout.addWidget(self._table_container, 1)

        self._schedule_quotes_load()

    @staticmethod
    def _labeled(widget, text):
        h = QHBoxLayout()
        h.addWidget(QLabel(text))
        h.addWidget(widget)
        return h

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

    def _schedule_quotes_load(self):
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
        # 持续显示加载状态，等 _on_quotes_loaded 用结果替换
        self._msg.info(f"⏳ 正在加载 {len(symbols)} 只股票行情...", auto_clear_ms=0)
        worker = AsyncWorker(_get_latest_quotes, self._db_path, symbols, parent=self)
        worker.finished.connect(lambda rows: self._on_quotes_loaded(rows, stocks, token))
        worker.error.connect(lambda e: self._msg.error(f"行情加载失败: {e}"))
        worker.start()

    def _on_quotes_loaded(self, quote_rows, stocks, token):
        if token != self._quotes_token:
            return  # 已有更新的请求，丢弃过期结果
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
        if missing == total and total > 0:
            self._msg.warning(
                f"⚠️ 当前 {total} 只自选股均无本地行情数据，"
                f"请点击「🔄 批量刷新行情」通过 Baostock 在线获取"
            )
        elif missing > 0:
            self._msg.warning(
                f"⚠️ {missing}/{total} 只股票行情缺失，"
                f"可点击「🔄 批量刷新行情」补齐数据",
                auto_clear_ms=8000,
            )
        else:
            self._msg.success(f"✅ 已加载 {total} 只股票行情")

    def _sort_rows(self, rows):
        if self._sort_by == "涨跌幅从高到低":
            return sorted(rows, key=lambda r: (r["pct_change"] is None,
                            -(r["pct_change"] if r["pct_change"] is not None else -999)))
        if self._sort_by == "涨跌幅从低到高":
            return sorted(rows, key=lambda r: (r["pct_change"] is None,
                            (r["pct_change"] if r["pct_change"] is not None else 999)))
        if self._sort_by == "成交量从高到低":
            return sorted(rows, key=lambda r: (r["volume_wan"] is None,
                            -(r["volume_wan"] if r["volume_wan"] is not None else -999)))
        return sorted(rows, key=lambda r: r["symbol"])

    def _render_overview(self, rows):
        # 防御：视图已切换（_clear_view 删除过本容器）时静默返回，避免 UI 卡死
        try:
            layout = self._overview_container.layout()
        except RuntimeError:
            logger.debug("_render_overview: 容器已被删除，跳过（旧 worker 回调）")
            return
        self._clear_layout(layout)
        up = sum(1 for r in rows if r["pct_change"] is not None and r["pct_change"] > 0)
        down = sum(1 for r in rows if r["pct_change"] is not None and r["pct_change"] < 0)
        flat = sum(1 for r in rows if r["pct_change"] is not None and r["pct_change"] == 0)
        for c in [
            MetricCard("股票总数", str(len(rows))),
            MetricCard("上涨", str(up)),
            MetricCard("下跌", str(down)),
            MetricCard("平盘", str(flat)),
        ]:
            layout.addWidget(c)
        layout.addStretch(1)

    def _render_table_section(self):
        # 防御：视图已切换（_clear_view 删除过本容器）时静默返回，避免 UI 卡死
        try:
            layout = self._table_container.layout()
        except RuntimeError:
            logger.debug("_render_table_section: 容器已被删除，跳过（旧 worker 回调）")
            return
        self._clear_layout(layout)

        rows = self._all_rows
        if not rows:
            layout.addWidget(QLabel("暂无匹配的自选股，请调整筛选条件。"))
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

        table = PandasTableView()
        table.set_dataframe(
            df,
            formatters={"最新价": "{:.2f}", "涨跌幅(%)": "{:+.2f}", "成交量(万)": "{:.1f}"},
            color_rules={"涨跌幅(%)": make_change_color_rule()},
            auto_resize=False,   # 关掉默认按内容拉伸，避免列宽飘移
        )
        table.row_double_clicked.connect(self._on_row_activated)

        # 显式列宽：合计约 630px，留余量给滚动条
        _COL_WIDTHS = {
            "代码": 100,
            "名称": 130,
            "最新价": 90,
            "涨跌幅(%)": 90,
            "成交量(万)": 110,
            "分组": 80,
        }
        header = table.horizontalHeader()
        for col_idx, col_name in enumerate(df.columns):
            w = _COL_WIDTHS.get(col_name, 80)
            header.resizeSection(col_idx, w)

        table.setMinimumHeight(380)
        layout.addWidget(table, 1)

        # 数据缺失提示（仅当本页 close 列缺失比例 > 50% 时显示）
        missing_in_page = sum(1 for r in page_rows if r["close"] is None)
        if page_rows and missing_in_page / len(page_rows) > 0.5:
            hint = QLabel(
                f"⚠️ 当前页 {len(page_rows)} 只股票中 {missing_in_page} 只"
                f"行情数据缺失。请点击「📡 批量刷新行情」按钮通过 Baostock 在线获取。"
            )
            hint.setWordWrap(True)
            hint.setStyleSheet(
                "QLabel { background-color: #fef3c7; color: #92400e; "
                "border: 1px solid #fcd34d; border-radius: 4px; "
                "padding: 8px 12px; font-size: 13px; }"
            )
            layout.addWidget(hint)

        # 分页 + 删除：并排两个 QGroupBox，避免挤压重叠
        bottom_bar = QHBoxLayout()
        bottom_bar.setSpacing(12)

        # 分页 GroupBox
        page_box = QGroupBox("📄 分页")
        page_box_layout = QHBoxLayout(page_box)
        page_box_layout.setContentsMargins(12, 8, 12, 8)
        prev_btn = QPushButton("◀ 上一页")
        prev_btn.setEnabled(self._page > 1)
        prev_btn.clicked.connect(self._on_prev_page)
        next_btn = QPushButton("下一页 ▶")
        next_btn.setEnabled(self._page < pages)
        next_btn.clicked.connect(self._on_next_page)
        page_label = QLabel(f"第 {self._page}/{pages} 页 · 共 {total} 只")
        page_label.setAlignment(Qt.AlignCenter)
        page_box_layout.addWidget(prev_btn)
        page_box_layout.addWidget(page_label, 1)
        page_box_layout.addWidget(next_btn)
        bottom_bar.addWidget(page_box, 2)

        # 删除 GroupBox
        del_box = QGroupBox("🗑️ 删除自选股")
        del_layout = QHBoxLayout(del_box)
        del_layout.setContentsMargins(12, 8, 12, 8)
        del_layout.setSpacing(8)
        del_combo = QComboBox()
        del_combo.setMinimumWidth(200)
        for r in rows:
            del_combo.addItem(f"{r['symbol']} {r['name']}", r["symbol"])
        if self._selected_stock:
            didx = del_combo.findData(self._selected_stock)
            if didx >= 0:
                del_combo.setCurrentIndex(didx)
        self._del_combo = del_combo
        del_combo.currentIndexChanged.connect(
            lambda i: setattr(self, "_selected_stock", del_combo.itemData(i)))
        confirm = QCheckBox("确认删除")
        self._del_confirm = confirm
        del_btn = QPushButton("删除")
        del_btn.setEnabled(False)

        def _update_enabled(_=None):
            del_btn.setEnabled(confirm.isChecked())

        confirm.stateChanged.connect(_update_enabled)
        del_btn.clicked.connect(self._on_delete_stock)
        del_layout.addWidget(QLabel("目标:"))
        del_layout.addWidget(del_combo, 1)
        del_layout.addWidget(confirm)
        del_layout.addWidget(del_btn)
        bottom_bar.addWidget(del_box, 3)

        layout.addLayout(bottom_bar)

    # ============ 列表交互 ============

    def _on_row_activated(self, row_idx):
        page_rows = getattr(self, "_page_rows", [])
        if 0 <= row_idx < len(page_rows):
            symbol = page_rows[row_idx]["symbol"]
            self._selected_stock = symbol
            self._render_detail(symbol)

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
        self._render_list()

    def _on_page_size_changed(self, text):
        try:
            self._page_size = int(text)
        except ValueError:
            return
        self._page = 1
        self._render_list()

    def _on_keyword_changed(self):
        self._keyword = self._keyword_edit.text()
        self._page = 1
        self._render_list()

    def _on_sort_changed(self, text):
        self._sort_by = text
        if hasattr(self, "_all_rows") and self._all_rows:
            self._all_rows = self._sort_rows(self._all_rows)
            self._render_table_section()
        else:
            self._schedule_quotes_load()

    def _on_refresh_quotes(self):
        # _schedule_quotes_load 内部已显示加载状态消息
        self._schedule_quotes_load()

    def _on_batch_refresh_quotes(self):
        """批量从 Baostock 在线补齐当前筛选分组的最近行情数据。"""
        stocks = self._compute_filtered_stocks()
        symbols = [s[0] for s in stocks]
        if not symbols:
            self._msg.warning("当前分组无自选股，请先添加")
            return

        self._msg.info(
            f"⏳ 正在通过 Baostock 在线获取 {len(symbols)} 只股票行情，请稍候...",
            auto_clear_ms=0,
        )

        worker = run_with_progress(
            self,
            _batch_refresh_quotes,
            self._db_path,
            symbols,
            title="批量刷新行情",
            message=f"正在更新 {len(symbols)} 只股票...",
            cancelable=True,
        )

        def _on_done(result):
            ok = result.get("success", 0) if isinstance(result, dict) else 0
            failed = result.get("failed", []) if isinstance(result, dict) else []
            if failed:
                self._msg.warning(
                    f"⚠️ 完成 {ok} 只，失败 {len(failed)} 只：{', '.join(failed[:5])}"
                    + ("..." if len(failed) > 5 else ""),
                    auto_clear_ms=8000,
                )
            else:
                self._msg.success(f"✅ 已批量更新 {ok} 只股票行情")
            # 刷新表格显示新数据
            self._schedule_quotes_load()

        def _on_error(err):
            self._msg.error(f"批量刷新失败: {err}")

        worker.finished.connect(_on_done)
        worker.error.connect(_on_error)

    def _on_add_stock(self):
        symbol = self._add_symbol_edit.text().strip()
        if not symbol:
            self._msg.warning("请输入股票代码")
            return
        name = self._add_name_edit.text().strip()
        group = self._add_group_combo.currentText()
        if group == "自定义":
            group = self._add_custom_edit.text().strip() or "默认"
        ok = self._wl.add_stock(symbol, name, group)
        if ok:
            self._msg.success(f"✅ 已添加 {symbol}")
            self._state.watchlist_changed.emit(self._wl.get_all_symbols())
        else:
            self._msg.error("添加失败")

    def _on_delete_stock(self):
        symbol = self._selected_stock
        if not symbol or not self._del_confirm.isChecked():
            return
        ok = self._wl.remove_stock(symbol)
        if ok:
            self._msg.success(f"已删除 {symbol}")
            self._state.watchlist_changed.emit(self._wl.get_all_symbols())
        else:
            self._msg.error("删除失败")

    def _on_export_group(self):
        rows = getattr(self, "_all_rows", [])
        symbols = [r["symbol"] for r in rows]
        if not symbols:
            self._msg.warning("当前没有可导出的股票")
            return
        self._state.selected_stocks = symbols
        self._state.set("multi_stock_symbols", symbols)
        self._msg.success(f"已选择 {len(symbols)} 只股票用于回测（切换到【策略回测】即可使用）")

    def _on_watchlist_changed(self, _symbols):
        if self._view_mode == "list":
            self._render_list()

    # ============ 详情视图 ============

    def _render_detail(self, symbol):
        # 自增 token：让列表视图启动的行情 worker 完成后直接 return，
        # 避免其回调访问已被 _clear_view 删除的列表控件（竞态崩溃）
        self._quotes_token += 1
        self._view_mode = "detail"
        self._detail_symbol = symbol
        self._detail_df = None
        self._clear_view()

        # 工具栏
        tb = QHBoxLayout()
        back_btn = QPushButton("← 返回自选股列表")
        back_btn.clicked.connect(self._render_list)
        tb.addWidget(back_btn)

        sel = StockSelector(parent=self, label="切换股票")
        all_stocks = self._wl.get_all_stocks()
        name_map = {s.symbol: s.name for s in all_stocks}
        sel.set_stocks([s.symbol for s in all_stocks], name_map)
        sel.set_selected_stock(symbol)
        sel.stock_changed.connect(self._on_detail_symbol_changed)
        tb.addWidget(sel)

        refresh_btn = QPushButton("🔄 刷新数据")
        refresh_btn.clicked.connect(self._on_refresh_detail)
        tb.addWidget(refresh_btn)
        tb.addStretch(1)
        self._view_layout.addLayout(tb)

        self._view_layout.addWidget(QLabel(f"📊 {symbol} 行情详情"))

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
        # 防御：视图已切换（_chart 已被 _clear_view 删除）时静默返回
        try:
            self._chart.set_message("正在加载数据...")
        except RuntimeError:
            logger.debug("_load_detail: 图表容器已被删除，跳过（视图已切换）")
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
        # 防御：视图已切换（_clear_view 删除过本容器）时静默返回
        try:
            layout = self._detail_metric_container.layout()
        except RuntimeError:
            logger.debug("_render_detail_metrics: 容器已被删除，跳过（旧 worker 回调）")
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
        color = "#dc2626" if change >= 0 else "#16a34a"
        delta_color = "#dc2626" if change >= 0 else "#16a34a"
        for c in [
            MetricCard("最新价", f"{close:.2f}", delta=f"{change:+.2f}", delta_color=delta_color),
            MetricCard("涨跌额", f"{change:+.2f}"),
            MetricCard("涨跌幅", f"{change_pct:+.2f}%"),
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
        # 防御：视图已切换（_clear_view 删除过本容器）时静默返回
        try:
            layout = self._detail_table_container.layout()
        except RuntimeError:
            logger.debug("_render_detail_table: 容器已被删除，跳过（旧 worker 回调）")
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
        self._msg.info(f"⏳ 正在更新 {self._detail_symbol} 行情数据...", auto_clear_ms=0)
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
        worker.finished.connect(lambda _: (self._msg.success("✅ 行情已更新"), self._load_detail()))
        worker.error.connect(lambda e: self._msg.error(f"更新失败: {e}"))
        worker.start()
