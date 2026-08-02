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
from datetime import datetime, timedelta

import pandas as pd

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QGroupBox,
    QPushButton, QComboBox, QLineEdit, QCheckBox, QFormLayout,
)
from PySide6.QtCore import Qt

from desktop.pages.base_page import BasePage
from desktop.widgets.stock_selector import StockSelector
from desktop.widgets.pandas_table import PandasTableView, make_change_color_rule
from desktop.widgets.metric_card import MetricCard
from desktop.widgets.message_bar import MessageBar
from desktop.widgets.chart_container import ChartContainer
from desktop.widgets.async_worker import AsyncWorker
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


def _make_kline_figure(df: pd.DataFrame, symbol: str, period: str = "D"):
    """绘制专业 K 线图（中国配色：红涨绿跌）。"""
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    df = df.copy()
    df["color"] = ["rise" if c >= o else "fall" for c, o in zip(df["close"], df["open"])]

    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.08,
        row_heights=[0.7, 0.3], subplot_titles=("", "成交量"),
    )
    fig.add_trace(go.Candlestick(
        x=df["date"], open=df["open"], high=df["high"], low=df["low"], close=df["close"],
        name="K线",
        increasing_line_color="#FF0000", decreasing_line_color="#00A000",
        increasing_fillcolor="#FF0000", decreasing_fillcolor="#00A000",
    ), row=1, col=1)

    if period == "D":
        ma_periods, ma_labels = [5, 10, 20, 60], ["MA5", "MA10", "MA20", "MA60"]
    elif period == "W":
        ma_periods, ma_labels = [5, 10, 20], ["MA5", "MA10", "MA20"]
    elif period == "M":
        ma_periods, ma_labels = [3, 6, 12], ["MA3", "MA6", "MA12"]
    else:
        ma_periods, ma_labels = [3, 5], ["MA3", "MA5"]
    ma_color_map = {
        "MA3": "#6366f1", "MA5": "#2563eb", "MA6": "#0ea5e9", "MA10": "#ef4444",
        "MA12": "#f59e0b", "MA20": "#10b981", "MA60": "#14b8a6",
    }
    for mp, ml in zip(ma_periods, ma_labels):
        if len(df) >= mp:
            df[f"ma{mp}"] = df["close"].rolling(mp).mean()
            fig.add_trace(go.Scatter(
                x=df["date"], y=df[f"ma{mp}"], name=ml,
                line=dict(width=1.6, color=ma_color_map.get(ml, "#64748b")),
            ), row=1, col=1)

    colors = ["#FF0000" if c >= o else "#00A000" for c, o in zip(df["close"], df["open"])]
    fig.add_trace(go.Bar(
        x=df["date"], y=df["volume"], marker_color=colors, name="成交量", opacity=0.7,
    ), row=2, col=1)

    period_names = {"D": "日K", "W": "周K", "M": "月K", "Y": "年K"}
    fig.update_layout(
        title=dict(text=f"<b>{symbol}</b> {period_names.get(period, 'K线')}走势", x=0.5, font=dict(size=18)),
        height=820, showlegend=True, template="plotly_white",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        hovermode="x unified", dragmode="pan",
        xaxis=dict(rangeslider=dict(visible=False), type="category", tickangle=45,
                   showgrid=True, gridcolor="rgba(148,163,184,0.18)", showspikes=True,
                   spikemode="across", spikesnap="cursor", spikethickness=1),
        yaxis=dict(showgrid=True, gridcolor="rgba(148,163,184,0.18)", showspikes=True,
                   spikethickness=1, tickformat=".2f"),
        yaxis2=dict(tickformat=".0f", showgrid=True, gridcolor="rgba(148,163,184,0.18)"),
        plot_bgcolor="#ffffff", paper_bgcolor="white",
        margin=dict(t=80, l=60, r=40, b=70),
    )
    if period == "D":
        fig.update_xaxes(
            rangebreaks=[dict(bounds=["sat", "mon"])],
            rangeselector=dict(buttons=list([
                dict(count=1, label="1M", step="month", stepmode="backward"),
                dict(count=3, label="3M", step="month", stepmode="backward"),
                dict(count=6, label="6M", step="month", stepmode="backward"),
                dict(count=1, label="1Y", step="year", stepmode="backward"),
                dict(step="all", label="ALL")])))
    return fig


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

        self._view_container = QWidget()
        self._view_layout = QVBoxLayout(self._view_container)
        self._view_layout.setContentsMargins(0, 0, 0, 0)
        self._view_layout.setSpacing(12)
        self.content_layout.addWidget(self._view_container, 1)

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
        self._view_mode = "list"
        self._clear_view()

        # --- 添加自选股 ---
        add_box = QGroupBox("➕ 添加自选股")
        add_box.setCheckable(True)
        add_box.setChecked(False)
        add_form = QFormLayout(add_box)
        self._add_symbol_edit = QLineEdit()
        self._add_symbol_edit.setPlaceholderText("如: 000001.SH / SH:601899 / 紫金矿业(SH:601899)")
        self._add_name_edit = QLineEdit()
        self._add_name_edit.setPlaceholderText("如: 平安银行（留空则智能推断）")
        self._add_group_combo = QComboBox()
        self._add_group_combo.addItems(GROUP_CHOICES)
        self._add_custom_edit = QLineEdit()
        self._add_custom_edit.setPlaceholderText("自定义分组名")
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
        export_btn = QPushButton("导出本组用于回测")
        export_btn.clicked.connect(self._on_export_group)
        op_bar.addWidget(refresh_btn)
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
        layout = self._overview_container.layout()
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
        layout = self._table_container.layout()
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
        )
        table.row_double_clicked.connect(self._on_row_activated)
        table.setMinimumHeight(380)
        layout.addWidget(table, 1)

        # 分页
        pg = QHBoxLayout()
        prev_btn = QPushButton("◀ 上一页")
        prev_btn.setEnabled(self._page > 1)
        prev_btn.clicked.connect(self._on_prev_page)
        next_btn = QPushButton("下一页 ▶")
        next_btn.setEnabled(self._page < pages)
        next_btn.clicked.connect(self._on_next_page)
        label = QLabel(f"第 {self._page}/{pages} 页 · 共 {total} 只")
        label.setAlignment(Qt.AlignCenter)
        pg.addWidget(prev_btn)
        pg.addWidget(label, 1)
        pg.addWidget(next_btn)
        layout.addLayout(pg)

        # 删除控制
        del_layout = QHBoxLayout()
        del_combo = QComboBox()
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
        del_layout.addWidget(QLabel("删除目标:"))
        del_layout.addWidget(del_combo)
        del_layout.addWidget(confirm)
        del_layout.addWidget(del_btn)
        del_layout.addStretch(1)
        layout.addLayout(del_layout)

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
        self._msg.info("正在刷新行情...")
        self._schedule_quotes_load()

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
        self._view_mode = "detail"
        self._detail_symbol = symbol
        self._detail_df = None
        self._clear_view()

        # 工具栏
        tb = QHBoxLayout()
        back_btn = QPushButton("← 返回自选股列表")
        back_btn.clicked.connect(self._render_list)
        tb.addWidget(back_btn)

        sel = StockSelector("切换股票")
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
        self._chart.set_message("正在加载数据...")
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
        layout = self._detail_metric_container.layout()
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
            fig = _make_kline_figure(disp, self._detail_symbol, period)
            self._chart.set_figure(fig)
        except Exception as e:
            self._chart.set_message(f"图表渲染失败: {e}")

    def _render_detail_table(self, df):
        layout = self._detail_table_container.layout()
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
        self._msg.info("正在更新行情数据...")
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
