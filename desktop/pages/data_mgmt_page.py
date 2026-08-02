"""
财务数据管理页 (DataMgmtPage) — 阶段3迁移（原 Tab3 / web/pages/data_management.py）

替代 web/pages/data_management.py 的「财务数据管理」页面。原实现用 st.radio +
st.multiselect + st.button + st.progress + st.rerun 联动；桌面版改用：

- 统一的滚动容器承载长页面（状态总览 / 获取 / 批量操作 / 披露日历 / 说明）
- 耗时网络操作（batch_update 约 15-30 分钟、估值拉取）全部经 ProgressWorker
  在子线程执行，并通过 run_with_progress 显示进度对话框，避免界面卡死
- 数据库只读/清理操作在模块级函数执行（自建 sqlite 连接，线程安全）
- 删除确认用 QMessageBox 替代 st.session_state 标志位
"""
import sqlite3
from datetime import datetime, timedelta

import pandas as pd

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QGroupBox,
    QPushButton, QComboBox, QLineEdit, QCheckBox, QSpinBox, QScrollArea,
    QMessageBox, QFormLayout,
)
from PySide6.QtCore import Qt

from desktop.pages.base_page import BasePage
from desktop.widgets.section_title import SectionTitle
from desktop.widgets.metric_card import MetricCard
from desktop.widgets.message_bar import MessageBar
from desktop.widgets.pandas_table import PandasTableView
from desktop.widgets.async_worker import run_with_progress
from desktop.models.managers import Managers


DATA_TYPE_OPTIONS = {
    "利润表": "profit",
    "资产负债表": "balance",
    "现金流量表": "cash",
    "杜邦分析": "dupont",
    "成长能力": "growth",
    "营运能力": "operation",
    "偿债能力": "debtpaying",
}

# (表名, 描述, 最新日期字段)
TABLE_STATUS = [
    ("valuation_data", "实时估值（PE/PB/PS/PCF）", "trade_date"),
    ("profit_data", "利润表", "report_date"),
    ("balance_data", "资产负债表", "report_date"),
    ("cash_flow_data", "现金流量表", "report_date"),
    ("dupont_data", "杜邦分析", "report_date"),
    ("growth_data", "成长能力", "report_date"),
    ("operation_data", "营运能力", "report_date"),
    ("debtpaying_data", "偿债能力", "report_date"),
    ("daily_kline", "日线行情", "date"),
    ("financial_data_raw", "财务原始数据(JSON)", "update_time"),
]

CLEAR_TABLES = [
    "profit_data", "balance_data", "cash_flow_data", "dupont_data", "growth_data",
    "operation_data", "debtpaying_data", "valuation_data", "history_valuation_data",
    "financial_data_raw",
]


# ============ 模块级辅助函数 ============

def _get_data_status(db_path: str) -> dict:
    """读取各数据表记录数与最新日期。"""
    status = {}
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        for table, desc, date_field in TABLE_STATUS:
            try:
                cur.execute(f"SELECT COUNT(*), MAX({date_field}) FROM {table}")
                row = cur.fetchone()
                status[table] = {
                    "count": row[0] or 0,
                    "latest_date": row[1] or "无",
                    "desc": desc,
                }
            except Exception:
                status[table] = {"count": 0, "latest_date": "无", "desc": desc}
        conn.close()
    except Exception:
        pass
    return status


def _clear_financial_data(db_path: str) -> list:
    """清空财务与估值相关表，返回成功清除的表名列表。"""
    cleared = []
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        for table in CLEAR_TABLES:
            try:
                cur.execute(f"DELETE FROM {table}")
                cleared.append(table)
            except Exception:
                pass
        conn.commit()
        conn.close()
    except Exception:
        pass
    return cleared


def _get_table_structures(db_path: str) -> list:
    """读取所有表结构，返回 [(表名, [(列名, 类型, 是否主键), ...]), ...]。"""
    result = []
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        tables = [r[0] for r in cur.fetchall()]
        for t in tables:
            cur.execute(f"PRAGMA table_info({t})")
            cols = [(c[1], c[2], c[5]) for c in cur.fetchall()]
            result.append((t, cols))
        conn.close()
    except Exception:
        pass
    return result


def _build_symbols(fetch_mode: str, single_symbol: str) -> list:
    """根据获取范围构建股票代码列表（全市场需网络，其余本地）。"""
    from portfolio.watchlist import (
        WatchlistManager, filter_out_benchmark_stocks, filter_out_benchmark_symbols,
    )
    if fetch_mode == "全市场":
        from data.financial_data_manager import FinancialDataManager
        fdn = FinancialDataManager()
        return fdn.get_all_stocks() or []
    if fetch_mode == "自选股":
        wl = WatchlistManager()
        return [s.symbol for s in filter_out_benchmark_stocks(wl.get_all_stocks())]
    # 单只股票
    if single_symbol:
        return filter_out_benchmark_symbols([single_symbol.upper()])
    return []


def _run_batch_update(fetch_mode: str, single_symbol: str, data_types: list,
                      start_year: int, progress_callback=None) -> dict:
    """批量更新财务数据（子线程执行）。progress_callback 为 2 元 (percent, msg)。"""
    from data.financial_data_manager import FinancialDataManager

    symbols = _build_symbols(fetch_mode, single_symbol)
    total = len(symbols)
    if progress_callback:
        progress_callback(0, f"准备获取 {total} 只股票...")

    def _adapt(current, tot, symbol):
        if progress_callback:
            pct = int(current / tot * 100) if tot else 0
            progress_callback(pct, f"进度: {current}/{tot} - {symbol}")

    fdn = FinancialDataManager()
    result = fdn.batch_update(
        symbols=symbols, data_types=data_types,
        start_year=start_year, progress_callback=_adapt,
    )
    return {"result": result or {}, "total": total}


def _run_fetch_valuation(fetch_mode: str, single_symbol: str, start_year: int,
                         valuation_mode: str, incremental: bool,
                         progress_callback=None) -> dict:
    """拉取并保存估值数据（子线程执行）。"""
    from data.financial_data_source import FinancialDataSource
    from data.financial_data_saver import FinancialDataSaver

    fds = FinancialDataSource()
    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = f"{int(start_year)}-01-01"
    latest_only = (valuation_mode == "最新快照（仅最近交易日）")

    symbols = _build_symbols(fetch_mode, single_symbol)
    total = len(symbols)

    df = pd.DataFrame()
    try:
        if fetch_mode == "全市场" and latest_only:
            df = fds.get_all_stocks_valuation()
        else:
            all_data = []
            for i, symbol in enumerate(symbols):
                if progress_callback:
                    progress_callback(int((i + 1) / total * 100) if total else 0,
                                     f"进度: {i + 1}/{total} - {symbol}")
                query_start = start_date
                if incremental and not latest_only:
                    try:
                        conn = sqlite3.connect(fds.db_path)
                        cur = conn.cursor()
                        cur.execute(
                            "SELECT MAX(trade_date) FROM valuation_data WHERE symbol = ?",
                            (symbol,),
                        )
                        row = cur.fetchone()
                        conn.close()
                        if row and row[0]:
                            last = datetime.strptime(str(row[0]), "%Y-%m-%d")
                            query_start = (last + timedelta(days=1)).strftime("%Y-%m-%d")
                    except Exception:
                        query_start = start_date
                if not latest_only and query_start > end_date:
                    continue
                stock_df = fds.get_history_valuation(symbol, query_start, end_date)
                if not stock_df.empty:
                    if latest_only:
                        stock_df = stock_df.sort_values("trade_date", ascending=False).head(1)
                    all_data.append(stock_df)
            if all_data:
                df = pd.concat(all_data, ignore_index=True)
    finally:
        try:
            fds.logout()
        except Exception:
            pass

    saved = 0
    if not df.empty:
        saver = FinancialDataSaver()
        saved = saver.save_valuation_data(df)
    return {"saved": saved, "df": df}


class DataMgmtPage(BasePage):
    """财务数据管理页"""

    def __init__(self, parent=None):
        self._db_path = Managers.instance().data_manager.db_path
        super().__init__(title="财务数据管理", subtitle="统一管理财务报表、估值与行情数据", parent=parent)

    # ============ 构建内容 ============

    def _build_content(self):
        self._msg = MessageBar()
        self.content_layout.addWidget(self._msg)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        self._layout = QVBoxLayout(inner)
        self._layout.setSpacing(14)
        scroll.setWidget(inner)
        self.content_layout.addWidget(scroll, 1)

        self._build_overview()
        self._build_fetch_section()
        self._build_batch_section()
        self._build_calendar_section()
        self._build_help_section()

    @staticmethod
    def _clear_layout(layout):
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

    # ============ 1. 状态总览 ============

    def _build_overview(self):
        self._layout.addWidget(SectionTitle("📊 数据源状态总览", "掌握各表记录量与最新日期，快速判断可用性"))

        self._overview_row = QHBoxLayout()
        self._overview_row.setSpacing(12)
        self._layout.addLayout(self._overview_row)

        self._status_table_layout = QVBoxLayout()
        self._layout.addLayout(self._status_table_layout)

        self._refresh_overview()

    def _refresh_overview(self):
        status = _get_data_status(self._db_path)
        self._clear_layout(self._overview_row)
        total = sum(s["count"] for s in status.values())
        stock_count = status.get("valuation_data", {}).get("count", 0)
        latest_kline = status.get("daily_kline", {}).get("latest_date", "无")
        latest_fin = status.get("profit_data", {}).get("latest_date", "无")
        for c in [
            MetricCard("总记录数", f"{total:,}"),
            MetricCard("股票数", f"{stock_count:,}"),
            MetricCard("行情最新", str(latest_kline)),
            MetricCard("财务最新", str(latest_fin)),
        ]:
            self._overview_row.addWidget(c)
        self._overview_row.addStretch(1)

        self._clear_layout(self._status_table_layout)
        rows = [{
            "数据类型": info["desc"], "表名": t,
            "记录数": f"{info['count']:,}", "最新日期": info["latest_date"],
        } for t, info in status.items()]
        df = pd.DataFrame(rows)
        table = PandasTableView()
        table.set_dataframe(df)
        self._status_table_layout.addWidget(table)

    # ============ 2. 获取财务数据 ============

    def _build_fetch_section(self):
        self._layout.addWidget(SectionTitle("🔄 获取财务数据", "支持全市场、自选股或单只股票增量更新"))

        # 获取范围
        mode_layout = QHBoxLayout()
        mode_layout.addWidget(QLabel("获取范围"))
        self._mode_combo = QComboBox()
        self._mode_combo.addItems(["全市场", "自选股", "单只股票"])
        self._mode_combo.currentTextChanged.connect(self._on_mode_changed)
        mode_layout.addWidget(self._mode_combo)
        mode_layout.addStretch(1)
        self._layout.addLayout(mode_layout)

        # 单只股票输入
        self._single_form = QFormLayout()
        self._single_edit = QLineEdit()
        self._single_edit.setPlaceholderText("000001.SZ")
        self._single_form.addRow("股票代码", self._single_edit)
        self._single_widget = QWidget()
        self._single_widget.setLayout(self._single_form)
        self._single_widget.setVisible(False)
        self._layout.addWidget(self._single_widget)

        # 数据类型
        self._layout.addWidget(QLabel("数据类型"))
        dtype_grid = QHBoxLayout()
        self._dtype_checks = {}
        for label in DATA_TYPE_OPTIONS:
            cb = QCheckBox(label)
            cb.setChecked(True)
            self._dtype_checks[label] = cb
            dtype_grid.addWidget(cb)
        dtype_grid.addStretch(1)
        self._layout.addLayout(dtype_grid)

        # 起始年份
        year_layout = QHBoxLayout()
        year_layout.addWidget(QLabel("起始年份"))
        self._year_spin = QSpinBox()
        self._year_spin.setRange(2010, datetime.now().year)
        self._year_spin.setValue(datetime.now().year - 4)
        year_layout.addWidget(self._year_spin)
        year_layout.addStretch(1)
        self._layout.addLayout(year_layout)

        # 按钮行
        btn_row = QHBoxLayout()
        fetch_btn = QPushButton("🚀 开始获取")
        fetch_btn.clicked.connect(self._on_fetch_financial)
        val_btn = QPushButton("📈 获取实时估值")
        val_btn.clicked.connect(self._on_fetch_valuation)
        btn_row.addWidget(fetch_btn)
        btn_row.addWidget(val_btn)
        btn_row.addStretch(1)
        self._layout.addLayout(btn_row)

        # 估值选项
        val_layout = QHBoxLayout()
        val_layout.addWidget(QLabel("估值获取模式"))
        self._val_mode_combo = QComboBox()
        self._val_mode_combo.addItems(["历史区间（从起始年份）", "最新快照（仅最近交易日）"])
        val_layout.addWidget(self._val_mode_combo)
        self._incremental_check = QCheckBox("仅增量更新估值（从库内最后日期之后开始）")
        self._incremental_check.setChecked(True)
        val_layout.addWidget(self._incremental_check)
        val_layout.addStretch(1)
        self._layout.addLayout(val_layout)

        # 结果展示容器
        self._fetch_result_container = QWidget()
        self._fetch_result_container.setLayout(QVBoxLayout())
        self._fetch_result_container.layout().setContentsMargins(0, 0, 0, 0)
        self._layout.addWidget(self._fetch_result_container)

    def _on_mode_changed(self, text):
        self._single_widget.setVisible(text == "单只股票")

    def _get_selected_dtypes(self):
        return [DATA_TYPE_OPTIONS[lbl] for lbl, cb in self._dtype_checks.items() if cb.isChecked()]

    def _on_fetch_financial(self):
        data_types = self._get_selected_dtypes()
        if not data_types:
            self._msg.warning("请至少选择一种数据类型")
            return
        mode = self._mode_combo.currentText()
        if mode == "单只股票" and not self._single_edit.text().strip():
            self._msg.warning("请输入股票代码")
            return
        self._msg.info("正在从 Baostock 获取财务数据（请耐心等待）...")
        worker = run_with_progress(
            self, _run_batch_update, mode, self._single_edit.text().strip(),
            data_types, self._year_spin.value(),
            title="获取财务数据", message="准备获取财务数据...",
        )
        worker.finished.connect(self._on_batch_finished)
        worker.error.connect(lambda e: self._msg.error(f"获取失败: {e}"))

    def _on_batch_finished(self, payload):
        result = payload.get("result", {})
        total = payload.get("total", 0)
        saved = sum(result.values())
        self._msg.success(f"获取完成！共保存 {saved} 条财务数据记录（{total} 只股票）")
        self._clear_layout(self._fetch_result_container.layout())
        rows = [{"数据类型": k, "记录数": str(v)} for k, v in result.items()]
        if rows:
            table = PandasTableView()
            table.set_dataframe(pd.DataFrame(rows))
            self._fetch_result_container.layout().addWidget(QLabel("各数据类型记录数："))
            self._fetch_result_container.layout().addWidget(table)
        self._refresh_overview()

    def _on_fetch_valuation(self):
        mode = self._mode_combo.currentText()
        if mode == "单只股票" and not self._single_edit.text().strip():
            self._msg.warning("请输入股票代码")
            return
        self._msg.info("正在获取估值数据...")
        worker = run_with_progress(
            self, _run_fetch_valuation, mode, self._single_edit.text().strip(),
            self._year_spin.value(), self._val_mode_combo.currentText(),
            self._incremental_check.isChecked(),
            title="获取实时估值", message="准备获取估值数据...",
        )
        worker.finished.connect(self._on_valuation_finished)
        worker.error.connect(lambda e: self._msg.error(f"获取估值数据失败: {e}"))

    def _on_valuation_finished(self, payload):
        saved = payload.get("saved", 0)
        df = payload.get("df")
        if saved > 0:
            self._msg.success(f"✅ 成功获取并保存 {saved} 只股票的估值数据")
        else:
            self._msg.warning("未获取到估值数据")
        self._clear_layout(self._fetch_result_container.layout())
        if df is not None and not df.empty:
            cols = [c for c in ["symbol", "trade_date", "pe_ttm", "pb", "ps", "pcf", "close"]
                    if c in df.columns]
            show = df.head(10)[cols].copy()
            table = PandasTableView()
            table.set_dataframe(show)
            self._fetch_result_container.layout().addWidget(QLabel("最新估值数据（前10只）："))
            self._fetch_result_container.layout().addWidget(table)
        self._refresh_overview()

    # ============ 3. 批量操作 ============

    def _build_batch_section(self):
        self._layout.addWidget(SectionTitle("🛠️ 批量操作", "查看结构、清理历史与刷新状态"))

        btn_row = QHBoxLayout()
        struct_btn = QPushButton("📋 查看数据库表结构")
        struct_btn.clicked.connect(self._on_show_structure)
        clear_btn = QPushButton("🗑️ 清除财务数据")
        clear_btn.clicked.connect(self._on_clear_financial)
        refresh_btn = QPushButton("🔄 刷新状态")
        refresh_btn.clicked.connect(lambda: (self._msg.info("状态已刷新"), self._refresh_overview()))
        btn_row.addWidget(struct_btn)
        btn_row.addWidget(clear_btn)
        btn_row.addWidget(refresh_btn)
        btn_row.addStretch(1)
        self._layout.addLayout(btn_row)

        self._schema_container = QWidget()
        self._schema_container.setLayout(QVBoxLayout())
        self._schema_container.layout().setContentsMargins(0, 0, 0, 0)
        self._layout.addWidget(self._schema_container)

    def _on_show_structure(self):
        self._clear_layout(self._schema_container.layout())
        structures = _get_table_structures(self._db_path)
        for table, cols in structures:
            self._schema_container.layout().addWidget(QLabel(f"<b>{table}</b>"))
            df = pd.DataFrame([{"列名": c[0], "类型": c[1], "主键": "是" if c[2] else ""} for c in cols])
            table_view = PandasTableView()
            table_view.set_dataframe(df)
            self._schema_container.layout().addWidget(table_view)

    def _on_clear_financial(self):
        reply = QMessageBox.question(
            self, "确认清除",
            "⚠️ 此操作将清除财务与估值相关数据，确认吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        cleared = _clear_financial_data(self._db_path)
        if cleared:
            self._msg.success(f"已清除 {len(cleared)} 张表的数据")
            self._refresh_overview()
        else:
            self._msg.warning("没有可清除的表（可能表不存在）")

    # ============ 4. 财报披露日历 ============

    def _build_calendar_section(self):
        self._layout.addWidget(SectionTitle("📅 财报披露日历", "根据披露窗口合理安排财务数据更新频率"))
        tips = self._disclosure_tips()
        box = QGroupBox()
        box_layout = QVBoxLayout(box)
        for tip in tips:
            box_layout.addWidget(QLabel(tip))
        self._layout.addWidget(box)

    @staticmethod
    def _disclosure_tips() -> list:
        m = datetime.now().month
        d = datetime.now().day
        if m < 5 or (m == 5 and d < 15):
            return ["📌 年报 + 一季报 披露期（1月-4月30日）", "   预计5月15日后可获取完整数据"]
        if m < 9 or (m == 9 and d < 15):
            return ["📌 中报 披露期（7月-8月31日）", "   预计9月15日后可获取完整数据"]
        if m < 11 or (m == 11 and d < 15):
            return ["📌 三季报 披露期（10月1日-10月31日）", "   预计11月15日后可获取完整数据"]
        return ["✅ 当前为财报真空期，所有最新财报已可获取"]

    # ============ 5. 使用说明 ============

    def _build_help_section(self):
        box = QGroupBox("📖 使用说明")
        box.setCheckable(True)
        box.setChecked(False)
        layout = QVBoxLayout(box)
        text = (
            "数据来源: Baostock (https://www.baostock.com)\n\n"
            "获取频率建议:\n"
            "  - 估值数据（PE/PB/PS）: 每日获取\n"
            "  - 财务数据（利润表/资产负债表等）: 每季度获取\n\n"
            "财报披露时间:\n"
            "  - 年报: 次年4月30日前\n"
            "  - 一季报: 次年4月30日前\n"
            "  - 中报: 次年8月31日前\n"
            "  - 三季报: 次年10月31日前\n\n"
            "注意事项:\n"
            "  1. 全市场获取耗时较长（约15-30分钟），建议分批获取\n"
            "  2. Baostock API 有访问限制，请勿频繁请求\n"
            "  3. 获取过程中请勿关闭页面"
        )
        label = QLabel(text)
        label.setWordWrap(True)
        layout.addWidget(label)
        self._layout.addWidget(box)
