"""
信号扫描页 (SignalScanPage) — 阶段3迁移（原 Tab6）

替代 web 屄 app.py 的信号扫描 Tab。原实现用 st.columns([1,1,1]) 三栏布局 +
st.rerun 联动，桌面版改用信号槽驱动局部刷新，无 session_state / st.rerun。

布局：
- 控制面板（三栏）：策略选择 + 参数 | 扫描范围（自选股复选框）| 日期范围 + 信号过滤
- 操作栏：开始扫描 / 导出 CSV / 状态
- 统计卡：扫描股票数 / 买入 / 卖出 / 持仓
- 结果表：涨红跌绿着色（涨跌幅 + 信号类型）
- 信号详情：买入 / 卖出分组折叠面板（等价 st.expander）

长耗时操作（批量扫描）在 AsyncWorker(QThread) 中执行，避免阻塞 UI。
"""
from typing import List, Dict, Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QGroupBox,
    QPushButton, QDateEdit, QRadioButton, QButtonGroup, QFileDialog,
    QScrollArea, QAbstractItemView,
)
from PySide6.QtCore import Qt, QDate

from desktop.pages.base_page import BasePage
from desktop.widgets.strategy_params_widget import StrategyParamsWidget
from desktop.widgets.stock_selector import StockCheckboxGroup
from desktop.widgets.pandas_table import (
    PandasTableView, make_change_color_rule, COLOR_UP, COLOR_DOWN, COLOR_FLAT,
)
from desktop.widgets.metric_card import MetricCard
from desktop.widgets.message_bar import MessageBar
from desktop.widgets.async_worker import AsyncWorker
from desktop.models.app_state import AppState
from desktop.models.managers import Managers

from portfolio.signal_scanner import SignalScanner, ScanResult


# ============ 信号类型着色规则（买红卖绿，涨红跌绿惯例保留）============
def _signal_type_color(value) -> Optional[str]:
    if value == "buy":
        return "#dc3545"        # 买入 - 红
    elif value == "sell":
        return "#28a745"        # 卖出 - 绿
    return "#6b7280"            # 持仓 - 灰


# ============ 后台扫描函数（在子线程中执行）============
def _run_scan(symbols, strategy_name, params, start_date, end_date) -> ScanResult:
    """在子线程执行信号扫描。

    不复用主线程的 DataManager（SQLite 连接非线程安全），SignalScanner 内部
    会为本次扫描创建独立的 DataManager 实例。
    """
    scanner = SignalScanner()   # data_manager=None -> 线程内自建
    return scanner.scan(
        symbols=symbols,
        strategy_name=strategy_name,
        strategy_params=params,
        start_date=start_date,
        end_date=end_date,
    )


class SignalScanPage(BasePage):
    """信号扫描页"""

    def __init__(self, parent=None):
        super().__init__(
            title="信号扫描",
            subtitle="对自选股批量应用策略，生成买卖信号",
            parent=parent,
        )
        self._state = AppState.instance()
        self._scan_result: Optional[ScanResult] = None
        self._filter = "all"
        self._all_stocks: List[tuple] = []      # [(symbol, name), ...]
        self._worker: Optional[AsyncWorker] = None

        # 跨页面联动
        self._state.scan_result_changed.connect(self._on_scan_result_changed)
        self._state.watchlist_changed.connect(self._on_watchlist_changed)

    # ========== UI 构建 ==========

    def _build_content(self):
        # ---- 控制面板：三栏 ----
        control = QHBoxLayout()
        control.setSpacing(12)

        # 栏1：策略
        strategy_box = QGroupBox("策略选择")
        strategy_box.setLayout(QVBoxLayout())
        strategy_box.layout().setContentsMargins(10, 12, 10, 10)
        self._strategy_widget = StrategyParamsWidget(include_multi_factor=True)
        strategy_box.layout().addWidget(self._strategy_widget)
        control.addWidget(strategy_box, 1)

        # 栏2：扫描范围
        range_box = QGroupBox("扫描范围（自选股）")
        range_box.setLayout(QVBoxLayout())
        range_box.layout().setContentsMargins(10, 12, 10, 10)
        self._stock_group = StockCheckboxGroup(columns=2, max_height=200)
        range_box.layout().addWidget(self._stock_group)
        control.addWidget(range_box, 1)

        # 栏3：日期 + 过滤
        opt_box = QGroupBox("日期与过滤")
        opt_layout = QVBoxLayout(opt_box)
        opt_layout.setContentsMargins(10, 12, 10, 10)
        opt_layout.setSpacing(8)

        date_layout = QHBoxLayout()
        date_layout.setSpacing(6)
        self._start_edit = QDateEdit(QDate.currentDate().addDays(-90))
        self._start_edit.setCalendarPopup(True)
        self._start_edit.setDisplayFormat("yyyy-MM-dd")
        self._end_edit = QDateEdit(QDate.currentDate())
        self._end_edit.setCalendarPopup(True)
        self._end_edit.setDisplayFormat("yyyy-MM-dd")
        date_layout.addWidget(QLabel("起"))
        date_layout.addWidget(self._start_edit)
        date_layout.addWidget(QLabel("止"))
        date_layout.addWidget(self._end_edit)
        opt_layout.addLayout(date_layout)

        # 信号过滤
        filter_label = QLabel("显示信号：")
        opt_layout.addWidget(filter_label)
        self._filter_group = QButtonGroup(self)
        self._filter_radios = {}
        for key, text in [("all", "全部"), ("buy", "仅买入"),
                          ("sell", "仅卖出"), ("hold", "仅持仓")]:
            rb = QRadioButton(text)
            if key == "all":
                rb.setChecked(True)
            self._filter_group.addButton(rb)
            self._filter_radios[key] = rb
            opt_layout.addWidget(rb)
        self._filter_group.buttonClicked.connect(self._on_filter_changed)
        opt_layout.addStretch(1)

        control.addWidget(opt_box, 1)
        self.content_layout.addLayout(control)

        # ---- 操作栏 ----
        toolbar = QHBoxLayout()
        toolbar.setSpacing(10)
        self._run_btn = QPushButton("🔍 开始扫描")
        self._run_btn.setObjectName("primaryButton")
        self._run_btn.clicked.connect(self._on_run_scan)
        self._export_btn = QPushButton("📥 导出 CSV")
        self._export_btn.setObjectName("secondaryButton")
        self._export_btn.clicked.connect(self._on_export_csv)
        self._export_btn.setEnabled(False)
        self._status_label = QLabel("")
        self._status_label.setStyleSheet("color: #6b7280; font-size: 13px;")
        toolbar.addWidget(self._run_btn)
        toolbar.addWidget(self._export_btn)
        toolbar.addWidget(self._status_label, 1)
        self.content_layout.addLayout(toolbar)

        # ---- 消息条 ----
        self._msg = MessageBar()
        self.content_layout.addWidget(self._msg)

        # ---- 统计卡 ----
        self._stat_row = QHBoxLayout()
        self._stat_row.setSpacing(12)
        self.content_layout.addLayout(self._stat_row)

        # ---- 结果表 ----
        table_frame = QFrame()
        table_frame.setObjectName("tableFrame")
        table_layout = QVBoxLayout(table_frame)
        table_layout.setContentsMargins(0, 0, 0, 0)
        self._table = PandasTableView()
        self._table.setMinimumHeight(240)
        table_layout.addWidget(self._table)
        self.content_layout.addWidget(table_frame, 1)

        # ---- 信号详情（买入/卖出分组，等价 st.expander）----
        self._buy_box = self._make_detail_group("买入信号详情", "buy")
        self._sell_box = self._make_detail_group("卖出信号详情", "sell")
        self.content_layout.addWidget(self._buy_box)
        self.content_layout.addWidget(self._sell_box)

        # 初始加载自选股
        self._refresh_stock_list()

    def _make_detail_group(self, title: str, signal_type: str) -> QGroupBox:
        """创建可折叠的信号详情分组（等价 st.expander）"""
        box = QGroupBox(title)
        box.setCheckable(True)
        box.setChecked(False)
        layout = QVBoxLayout(box)
        layout.setContentsMargins(8, 10, 8, 8)
        table = PandasTableView()
        table.setMinimumHeight(120)
        layout.addWidget(table)
        # 记录信号类型，便于刷新
        box.setProperty("signal_type", signal_type)
        box.setProperty("detail_table", table)
        return box

    # ========== 数据加载 ==========

    def _refresh_stock_list(self):
        """从 WatchlistManager 加载自选股到复选框组"""
        try:
            wl = Managers.instance().watchlist_manager
            stocks = wl.get_all_stocks()
        except Exception as e:
            self._msg.error(f"读取自选股失败: {e}")
            return

        self._all_stocks = [(s.symbol, s.name) for s in stocks]
        self._stock_group.set_stocks(self._all_stocks)
        # 默认全选
        self._stock_group.set_selected([s for s, _ in self._all_stocks])

        if not self._all_stocks:
            self._msg.warning("⚠️ 自选股为空，请先到【自选股管理】添加股票后再扫描。")

    # ========== 交互回调 ==========

    def _on_filter_changed(self, _button=None):
        # 确定当前过滤
        for key, rb in self._filter_radios.items():
            if rb.isChecked():
                self._filter = key
                break
        self._render_table()

    def _on_run_scan(self):
        symbols = self._stock_group.get_selected()
        if not symbols:
            self._msg.warning("⚠️ 请至少选择一只股票进行扫描。")
            return

        strategy = self._strategy_widget.get_strategy()
        params = self._strategy_widget.get_params()
        start_date = self._start_edit.date().toString("yyyy-MM-dd")
        end_date = self._end_edit.date().toString("yyyy-MM-dd")

        # 进入扫描中状态
        self._run_btn.setEnabled(False)
        self._export_btn.setEnabled(False)
        self._status_label.setText(f"🔍 正在扫描 {len(symbols)} 只股票（{strategy}）...")
        self._msg.info("正在执行信号扫描，请稍候（扫描在后台线程进行，界面不卡顿）。")

        self._worker = AsyncWorker(
            _run_scan, symbols, strategy, params, start_date, end_date
        )
        self._worker.finished.connect(self._on_scan_finished)
        self._worker.error.connect(self._on_scan_error)
        self._worker.start()

    def _on_scan_finished(self, result: ScanResult):
        self._run_btn.setEnabled(True)
        self._scan_result = result
        # 写入全局状态，触发跨页面联动
        self._state.scan_result = result
        self._status_label.setText(
            f"✅ 扫描完成：{result.buy_signals} 买入 / "
            f"{result.sell_signals} 卖出 / {result.hold_signals} 持仓"
        )
        self._msg.success(
            f"✅ 扫描完成，共 {result.total_stocks} 只股票，"
            f"{result.buy_signals} 个买入信号，{result.sell_signals} 个卖出信号。"
        )
        self._render_stats(result)
        self._render_table()
        self._render_details(result)
        self._export_btn.setEnabled(True)

    def _on_scan_error(self, err_msg: str):
        self._run_btn.setEnabled(True)
        self._export_btn.setEnabled(False)
        self._status_label.setText("❌ 扫描失败")
        self._msg.error(f"信号扫描失败: {err_msg}")

    def _on_export_csv(self):
        if self._scan_result is None:
            self._msg.warning("⚠️ 暂无可导出的扫描结果。")
            return
        df = self._scan_result.to_dataframe()
        if df.empty:
            self._msg.warning("⚠️ 扫描结果为空，无可导出数据。")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "导出信号扫描结果", "signal_scan.csv",
            "CSV Files (*.csv);;All Files (*)",
        )
        if not path:
            return
        try:
            df.to_csv(path, index=False, encoding="utf-8-sig")
            self._msg.success(f"✅ 已导出 {len(df)} 条信号到：{path}")
        except Exception as e:
            self._msg.error(f"导出失败: {e}")

    # ========== AppState 联动 ==========

    def _on_scan_result_changed(self, result):
        if result is self._scan_result:
            return  # 自己写入的，跳过避免重复渲染
        self._scan_result = result
        self._render_stats(result)
        self._render_table()
        self._render_details(result)
        self._export_btn.setEnabled(True)

    def _on_watchlist_changed(self, _stocks=None):
        self._refresh_stock_list()

    # ========== 渲染 ==========

    def _render_stats(self, result: ScanResult):
        # 清空旧卡
        while self._stat_row.count():
            item = self._stat_row.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        cards = [
            MetricCard("扫描股票数", str(result.total_stocks), delta="📊",
                       delta_color="neutral"),
            MetricCard("买入信号", str(result.buy_signals), delta="📈",
                       delta_color="up"),
            MetricCard("卖出信号", str(result.sell_signals), delta="📉",
                       delta_color="down"),
            MetricCard("持仓信号", str(result.hold_signals), delta="⏸️",
                       delta_color="neutral"),
        ]
        for c in cards:
            self._stat_row.addWidget(c)
        self._stat_row.addStretch(1)

    def _render_table(self):
        if self._scan_result is None:
            return
        df = self._scan_result.to_dataframe()
        if df.empty:
            self._table.set_dataframe(df)
            return

        # 按过滤条件筛选
        if self._filter != "all":
            df = df[df["信号类型"] == self._filter]

        # 选取展示列并重排
        display_cols = ["股票代码", "股票名称", "最新价", "涨跌幅",
                        "信号类型", "信号星级", "信号强度", "信号日期",
                        "策略", "信号原因"]
        display_cols = [c for c in display_cols if c in df.columns]
        df = df[display_cols]

        formatters = {
            "最新价": "{:.2f}",
            "涨跌幅": "{:+.2f}%",
            "信号强度": "{:.1f}",
        }
        color_rules = {
            "涨跌幅": make_change_color_rule(),
            "信号类型": _signal_type_color,
        }
        self._table.set_dataframe(
            df, formatters=formatters, color_rules=color_rules, auto_resize=True,
        )

    def _render_details(self, result: ScanResult):
        self._fill_detail(self._buy_box, result, "buy")
        self._fill_detail(self._sell_box, result, "sell")

    def _fill_detail(self, box: QGroupBox, result: ScanResult, signal_type: str):
        table = box.property("detail_table")
        signals = result.get_filtered_signals(signal_type)
        if not signals:
            box.setTitle(f"{box.title().split('（')[0]}（无）")
            table.set_dataframe(__import__("pandas").DataFrame())
            return

        rows = []
        for sig in signals:
            rows.append({
                "股票代码": sig.symbol,
                "股票名称": sig.name,
                "最新价": sig.price,
                "涨跌幅": sig.change_pct,
                "信号强度": sig.strength,
                "信号原因": sig.reason,
            })
        import pandas as pd
        df = pd.DataFrame(rows)

        box.setTitle(f"{'买入' if signal_type == 'buy' else '卖出'}信号详情"
                     f"（{len(rows)} 只）")
        formatters = {
            "最新价": "{:.2f}",
            "涨跌幅": "{:+.2f}%",
            "信号强度": "{:.1f}",
        }
        color_rules = {
            "涨跌幅": make_change_color_rule(),
        }
        table.set_dataframe(df, formatters=formatters, color_rules=color_rules,
                            auto_resize=True)
