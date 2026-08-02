"""
因子分析页 (FactorAnalysisPage) — 阶段3迁移（原 Tab4 / factor_analysis_page.py）

替代 web/factor_analysis_page.py 的「因子分析」页面。原实现用 st.columns + st.tabs +
st.rerun + st.session_state 联动，桌面版改用信号槽驱动局部刷新。

页面分两栏：
- 左：因子数据准备（批量准备因子值写入缓存 / 删除全部）
- 右：因子查询（QTabWidget 切换「单股查询」「多股排名」）

所有因子计算（准备 / 查询 / 排名 / 卡片格式化）均在子线程执行，worker 返回
可序列化的结果结构，主线程仅做渲染，避免跨线程使用数据库对象。
"""
import sqlite3
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import pandas as pd

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QGroupBox,
    QPushButton, QDateEdit, QComboBox, QFileDialog, QTabWidget,
    QScrollArea, QGridLayout, QCheckBox, QProgressBar,
)
from PySide6.QtCore import Qt, QDate

from desktop.pages.base_page import BasePage
from desktop.widgets.stock_selector import StockSelector, StockCheckboxGroup
from desktop.widgets.pandas_table import PandasTableView
from desktop.widgets.message_bar import MessageBar
from desktop.widgets.section_title import SectionTitle
from desktop.widgets.async_worker import AsyncWorker, run_with_progress
from desktop.models.managers import Managers

from web.factor_presenter import FactorPresenter
from data.factor_manager import FactorManager
from strategy.fundamental_factors import FundamentalFactors
from web.services.backtest_service import load_backtest_stock_data
from portfolio.watchlist import filter_out_benchmark_stocks


# ============ 模块级辅助函数（可在子线程执行）============

def _infer_required_report_date(asof_date: str) -> str:
    dt = pd.to_datetime(asof_date)
    y, m = dt.year, dt.month
    if m <= 4:
        return f"{y - 1}-09-30"
    if m <= 8:
        return f"{y}-03-31"
    if m <= 10:
        return f"{y}-06-30"
    return f"{y}-09-30"


def _check_financial_coverage(db_path: str, symbols: List[str], asof_date: str
                              ) -> Tuple[List[str], str]:
    required_report_date = _infer_required_report_date(asof_date)
    missing: List[str] = []
    conn = sqlite3.connect(db_path)
    try:
        for symbol in symbols:
            profit_row = conn.execute(
                "SELECT MAX(report_date) FROM profit_data WHERE symbol=? AND report_date<=?",
                (symbol, required_report_date)).fetchone()
            balance_row = conn.execute(
                "SELECT MAX(report_date) FROM balance_data WHERE symbol=? AND report_date<=?",
                (symbol, required_report_date)).fetchone()
            if not (profit_row and profit_row[0]) or not (balance_row and balance_row[0]):
                missing.append(symbol)
    finally:
        conn.close()
    return missing, required_report_date


def _delete_all_factor_values(db_path: str) -> int:
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute("SELECT COUNT(1) FROM factor_values").fetchone()
        total = int(row[0]) if row else 0
        conn.execute("DELETE FROM factor_values")
        conn.commit()
        return total
    finally:
        conn.close()


def _prepare_factors(db_path: str, symbols: List[str], start_date: str,
                     end_date: str, progress_callback=None) -> Tuple[int, str]:
    """批量准备因子值并写入 factor_values。progress_callback(percent, msg) -> bool。"""
    stock_data = load_backtest_stock_data(db_path, symbols, start_date, end_date)
    if not stock_data:
        return 0, "未获取到可用行情数据，请先更新行情库。"

    ff = FundamentalFactors(db_path)
    factor_mgr = FactorManager(db_path)
    fp = FactorPresenter(db_path)
    rows = []
    try:
        factor_categories = fp.get_factor_list_by_category()
        factor_names = sorted({fn for factors in factor_categories.values()
                               for fn, _ in factors})
        if not factor_names:
            return 0, "未找到可用因子元数据。"

        total = len(stock_data)
        for idx, (symbol, df) in enumerate(stock_data.items(), start=1):
            date_series = (pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
                           if "date" in df.columns else df.index.astype(str))
            for trade_date in date_series:
                values = ff.calculate_all_factors(symbol, trade_date)
                report_date = ff.get_report_date(trade_date, symbol)
                report_pub_date = ff.get_report_publish_date(symbol, report_date)
                for factor_name in factor_names:
                    if factor_name not in values:
                        continue
                    value = values.get(factor_name)
                    if pd.isna(value):
                        continue
                    rows.append({
                        "symbol": symbol,
                        "trade_date": trade_date,
                        "factor_name": factor_name,
                        "factor_value": float(value),
                        "value_source": "prepare_task",
                        "is_imputed": 0,
                        "quality_flag": "ok",
                        "asof_trade_date": trade_date,
                        "source_report_date": report_date,
                        "source_pub_date": report_pub_date,
                    })
            if progress_callback and not progress_callback(
                    int(idx / max(1, total) * 100),
                    f"准备中: {symbol} ({idx}/{total})"):
                return len(rows), "已取消"
        if not rows:
            return 0, "准备完成但未产生可写入记录。"
        saved = factor_mgr.save_factor_values(pd.DataFrame(rows))
        return saved, f"覆盖股票 {len(stock_data)} 只，区间 {start_date} ~ {end_date}"
    finally:
        fp.close()
        ff.close()


def _query_single_factor(symbol: str, date_option: str, db_path: str) -> dict:
    """单股因子查询（子线程）。返回可序列化结果结构。"""
    fp = FactorPresenter(db_path)
    try:
        factor_categories = fp.get_factor_list_by_category()
        # 兜底：元数据为空时使用内置定义
        if not factor_categories:
            from strategy.fundamental_factors import FundamentalFactors as FF
            fallback = {}
            for fname, meta in FF.FACTOR_METADATA.items():
                cat_en = meta.get("category", "")
                cat_cn = fp.FACTOR_CATEGORIES.get(cat_en, "其他")
                fallback.setdefault(cat_cn, []).append(
                    (fname, fp.FACTOR_NAMES_CN.get(fname, fname)))
            factor_categories = fallback

        payload = fp.get_factors_on_date(symbol, date_option)
        factors_dict = payload["factors"]
        query_date = payload["query_date"]
        report_date = payload["report_date"]
        metadata_all = fp._get_factor_metadata()

        by_category = {}
        for category, factors in factor_categories.items():
            items = []
            for fname, fname_cn in factors:
                value = factors_dict.get(fname, 0)
                formatted = fp.format_factor_value(fname, value)
                direction = metadata_all.get(fname, {}).get("direction", "neutral")
                items.append((fname_cn, formatted, direction, value))
            by_category[category] = items

        return {
            "by_category": by_category,
            "factors_raw": dict(factors_dict),
            "query_date": query_date,
            "report_date": report_date,
            "error": None,
        }
    finally:
        fp.close()


def _query_ranking(symbols: List[str], factor_name: str, date_option: str,
                  db_path: str) -> dict:
    """多股单因子排名（子线程）。返回显示用 DataFrame 与上下文。"""
    fp = FactorPresenter(db_path)
    try:
        query_date = fp.resolve_trade_date(date_option)
        report_date = fp.ff.get_report_date(query_date)
        ranking_df = fp.get_multi_stock_single_factor(symbols, factor_name, query_date)
        if ranking_df is None or ranking_df.empty:
            return {"df": pd.DataFrame(), "query_date": query_date,
                    "report_date": report_date, "error": None}
        display = ranking_df.copy()
        display["因子值"] = [fp.format_factor_value(factor_name, v)
                             for v in display["因子值"]]
        display["查询日期"] = query_date
        display["财报截止日期"] = report_date
        from portfolio.watchlist import WatchlistManager
        wl = WatchlistManager()
        name_map = {s.symbol: s.name for s in wl.get_all_stocks()}
        display["股票"] = display["股票代码"].apply(
            lambda s: f"{s} - {name_map.get(s, s)}")
        display = display[["排名", "股票代码", "股票", "因子值", "查询日期", "财报截止日期"]]
        return {"df": display, "query_date": query_date,
                "report_date": report_date, "error": None}
    finally:
        fp.close()


def _get_factor_date_options(quarter_count: int = 12) -> List[str]:
    options = ["最新"]
    today = pd.Timestamp.today()
    quarter_ends = pd.date_range(end=today, periods=quarter_count, freq="QE")
    labels = {"03-31": "一季报", "06-30": "中报", "09-30": "三季报", "12-31": "年报"}
    for qe in sorted(quarter_ends, reverse=True):
        ds = qe.strftime("%Y-%m-%d")
        options.append(f"{ds} ({labels.get(qe.strftime('%m-%d'), '财报')})")
    return options


class FactorAnalysisPage(BasePage):
    """因子分析页"""

    def __init__(self, parent=None):
        # 必须在 super().__init__() 之前设置，因为 _build_content 在 super 内触发
        self._db_path = Managers.instance().data_manager.db_path
        self._date_options = _get_factor_date_options()

        super().__init__(
            title="因子分析",
            subtitle="支持单股因子洞察与多股横向排名，快速识别优质标的",
            parent=parent,
        )
        self._state = None  # 本页无跨页状态依赖

    # ========== UI 构建 ==========

    def _build_content(self):
        # 消息条需最先创建：_build_ranking_tab 末尾会调用 _refresh_stock_lists，
        # 其中的失败分支会用到 self._msg
        self._msg = MessageBar()

        main = QHBoxLayout()
        main.setSpacing(12)

        # ===== 左：因子数据准备 =====
        left = QGroupBox("因子数据准备")
        left.setFixedWidth(300)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(12, 14, 12, 14)
        left_layout.setSpacing(8)
        self._build_prepare_controls(left_layout)
        left_layout.addStretch(1)
        main.addWidget(left)

        # ===== 右：因子查询 =====
        right = QGroupBox("因子查询")
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(12, 14, 12, 14)
        self._tabs = QTabWidget()
        self._build_single_tab()
        self._build_ranking_tab()
        right_layout.addWidget(self._tabs)
        main.addWidget(right, 1)

        self.content_layout.addLayout(main)
        self.content_layout.addWidget(self._msg)

    def _build_prepare_controls(self, layout: QVBoxLayout):
        layout.addWidget(QLabel("为多因子回测批量准备因子值并写入缓存"))
        date_row = QHBoxLayout()
        date_row.setSpacing(6)
        self._prep_start = QDateEdit(QDate(2023, 1, 1))
        self._prep_start.setCalendarPopup(True)
        self._prep_start.setDisplayFormat("yyyy-MM-dd")
        self._prep_end = QDateEdit(QDate.currentDate())
        self._prep_end.setCalendarPopup(True)
        self._prep_end.setDisplayFormat("yyyy-MM-dd")
        date_row.addWidget(QLabel("起"))
        date_row.addWidget(self._prep_start)
        date_row.addWidget(QLabel("止"))
        date_row.addWidget(self._prep_end)
        layout.addLayout(date_row)

        self._prepare_btn = QPushButton("🛠️ 准备因子数据")
        self._prepare_btn.setObjectName("primaryButton")
        self._prepare_btn.clicked.connect(self._on_prepare)
        layout.addWidget(self._prepare_btn)

        self._delete_btn = QPushButton("🗑️ 删除所有因子数据")
        self._delete_btn.setObjectName("secondaryButton")
        self._delete_btn.clicked.connect(self._on_delete)
        layout.addWidget(self._delete_btn)

        self._prepare_status = QLabel("")
        self._prepare_status.setWordWrap(True)
        self._prepare_status.setStyleSheet("color: #6b7280; font-size: 12px;")
        layout.addWidget(self._prepare_status)

    def _build_single_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        ctrl = QHBoxLayout()
        ctrl.setSpacing(8)
        self._single_selector = StockSelector(label="选择股票")
        self._single_date = QComboBox()
        self._single_date.addItems(self._date_options)
        ctrl.addWidget(self._single_selector, 1)
        ctrl.addWidget(QLabel("查询日期"))
        ctrl.addWidget(self._single_date)
        layout.addLayout(ctrl)

        self._single_caption = QLabel("")
        self._single_caption.setStyleSheet("color: #6b7280; font-size: 12px;")
        layout.addWidget(self._single_caption)

        self._single_export = QPushButton("📥 导出因子CSV")
        self._single_export.setObjectName("secondaryButton")
        self._single_export.clicked.connect(self._on_export_single)
        self._single_export.setEnabled(False)
        layout.addWidget(self._single_export, 0, Qt.AlignLeft)

        # 因子卡片滚动区
        self._single_scroll = QScrollArea()
        self._single_scroll.setWidgetResizable(True)
        self._single_content = QWidget()
        self._single_content_layout = QVBoxLayout(self._single_content)
        self._single_content_layout.setContentsMargins(0, 0, 0, 0)
        self._single_content_layout.setSpacing(10)
        self._single_scroll.setWidget(self._single_content)
        layout.addWidget(self._single_scroll, 1)

        self._single_result: Optional[dict] = None

        self._single_selector.stock_changed.connect(self._on_single_symbol_changed)
        self._single_date.currentTextChanged.connect(self._on_single_date_changed)

        self._tabs.addTab(tab, "单股查询")

    def _build_ranking_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # 股票多选
        self._rank_stocks = StockCheckboxGroup(columns=3, max_height=160)
        layout.addWidget(self._rank_stocks)

        ctrl = QHBoxLayout()
        ctrl.setSpacing(8)
        self._rank_factor = QComboBox()
        ctrl.addWidget(QLabel("因子"))
        ctrl.addWidget(self._rank_factor, 1)
        self._rank_date = QComboBox()
        self._rank_date.addItems(self._date_options)
        ctrl.addWidget(QLabel("日期"))
        ctrl.addWidget(self._rank_date)
        layout.addLayout(ctrl)

        self._rank_query_btn = QPushButton("🔍 查询排名")
        self._rank_query_btn.setObjectName("primaryButton")
        self._rank_query_btn.clicked.connect(self._on_query_ranking)
        layout.addWidget(self._rank_query_btn, 0, Qt.AlignLeft)

        self._rank_caption = QLabel("")
        self._rank_caption.setStyleSheet("color: #6b7280; font-size: 12px;")
        layout.addWidget(self._rank_caption)

        self._rank_export = QPushButton("📥 导出CSV")
        self._rank_export.setObjectName("secondaryButton")
        self._rank_export.clicked.connect(self._on_export_ranking)
        self._rank_export.setEnabled(False)
        layout.addWidget(self._rank_export, 0, Qt.AlignLeft)

        self._rank_table = PandasTableView()
        self._rank_table.setMinimumHeight(200)
        layout.addWidget(self._rank_table, 1)

        self._rank_result: Optional[dict] = None

        self._tabs.addTab(tab, "多股排名")

        # 初始化因子下拉
        self._refresh_factor_combo()
        self._refresh_stock_lists()

    def _refresh_factor_combo(self):
        self._rank_factor.blockSignals(True)
        self._rank_factor.clear()
        try:
            fp = FactorPresenter(self._db_path)
            cats = fp.get_factor_list_by_category()
            fp.close()
        except Exception:
            cats = {}
        for category, factors in cats.items():
            for fname, fname_cn in factors:
                self._rank_factor.addItem(f"{fname_cn}（{category}）", fname)
        if self._rank_factor.count() == 0:
            self._rank_factor.addItem("（无可用因子）", "")
        self._rank_factor.blockSignals(False)

    def _refresh_stock_lists(self):
        try:
            wl = Managers.instance().watchlist_manager
            stocks = filter_out_benchmark_stocks(wl.get_all_stocks())
        except Exception as e:
            self._msg.error(f"读取自选股失败: {e}")
            return
        pairs = [(s.symbol, s.name) for s in stocks]
        # 单股下拉
        self._single_selector.set_stocks(
            [s for s, _ in pairs],
            display_map={s: f"{s} - {n}" for s, n in pairs},
        )
        # 多股复选
        self._rank_stocks.set_stocks(pairs)
        self._rank_stocks.set_selected([s for s, _ in pairs[:5]])
        if not pairs:
            self._msg.warning("⚠️ 自选股为空，请先到【自选股管理】添加股票。")

    # ========== 准备 / 删除 ==========

    def _on_prepare(self):
        symbols = self._rank_stocks.get_selected() or self._get_all_symbols()
        if not symbols:
            self._msg.warning("⚠️ 没有可选股票，请先添加自选股。")
            return
        start = self._prep_start.date().toString("yyyy-MM-dd")
        end = self._prep_end.date().toString("yyyy-MM-dd")
        if self._prep_start.date() > self._prep_end.date():
            self._msg.error("开始日期不能晚于结束日期。")
            return

        # 财务覆盖检查（同步，快速）
        missing, required = _check_financial_coverage(self._db_path, symbols, start)
        if missing:
            preview = "、".join(missing[:8])
            tail = "" if len(missing) <= 8 else f" 等 {len(missing)} 只"
            self._msg.error(
                f"财务数据覆盖不足：起始日需报告期 <= {required}，以下股票缺少必要财务数据："
                f"{preview}{tail}。请先到「财务数据管理」更新。"
            )
            return

        self._prepare_btn.setEnabled(False)
        self._prepare_status.setText("🔄 正在准备因子数据...")

        def _work(progress_callback=None):
            return _prepare_factors(self._db_path, symbols, start, end, progress_callback)

        worker = run_with_progress(
            self, _work, title="准备因子数据", message="正在批量计算因子...",
        )
        worker.finished.connect(
            lambda res: self._on_prepare_finished(res))
        worker.error.connect(
            lambda err: self._on_prepare_error(err))

    def _on_prepare_finished(self, result):
        self._prepare_btn.setEnabled(True)
        rows, message = result
        if rows > 0:
            self._prepare_status.setText(f"状态：成功 | {message}")
            self._msg.success(f"✅ 因子数据准备完成：写入 {rows} 条记录。")
            self._refresh_factor_combo()
        else:
            self._prepare_status.setText(f"状态：失败 | {message}")
            self._msg.error(message)

    def _on_prepare_error(self, err_msg):
        self._prepare_btn.setEnabled(True)
        self._prepare_status.setText("状态：失败")
        self._msg.error(f"因子准备出错: {err_msg}")

    def _on_delete(self):
        from PySide6.QtWidgets import QMessageBox
        ok = QMessageBox.question(
            self, "确认删除", "确认要删除所有因子数据吗？此操作不可撤销。",
            QMessageBox.Yes | QMessageBox.No)
        if ok != QMessageBox.Yes:
            return
        deleted = _delete_all_factor_values(self._db_path)
        self._prepare_status.setText(
            f"状态：成功 | 已删除 factor_values 共 {deleted} 条记录")
        self._msg.success(f"✅ 已删除 factor_values 共 {deleted} 条记录。")
        self._refresh_factor_combo()

    def _get_all_symbols(self):
        try:
            wl = Managers.instance().watchlist_manager
            return [s.symbol for s in filter_out_benchmark_stocks(wl.get_all_stocks())]
        except Exception:
            return []

    # ========== 单股查询 ==========

    def _on_single_symbol_changed(self, symbol: str):
        self._run_single_query()

    def _on_single_date_changed(self, _=None):
        self._run_single_query()

    def _run_single_query(self):
        symbol = self._single_selector.get_selected_stock()
        if not symbol:
            return
        date_option = self._single_date.currentText()
        self._single_caption.setText("🔄 查询中...")
        worker = AsyncWorker(_query_single_factor, symbol, date_option, self._db_path)
        worker.finished.connect(self._on_single_finished)
        worker.error.connect(lambda e: self._msg.error(f"因子查询出错: {e}"))
        worker.start()

    def _on_single_finished(self, result: dict):
        if result.get("error"):
            self._msg.error(result["error"])
            return
        self._single_result = result
        self._single_caption.setText(
            f"查询日期: {result['query_date']} | 实际财报截止日期: {result['report_date']}")
        self._render_factor_cards(result["by_category"])
        self._single_export.setEnabled(True)

    def _render_factor_cards(self, by_category: dict):
        # 清空旧内容
        while self._single_content_layout.count():
            item = self._single_content_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        if not by_category:
            self._single_content_layout.addWidget(
                QLabel("暂无可展示的因子分类，请先检查因子元数据初始化。"))
            return

        for category, items in by_category.items():
            title = SectionTitle(category)
            self._single_content_layout.addWidget(title)
            grid = QGridLayout()
            grid.setSpacing(8)
            for i, (fname_cn, formatted, direction, value) in enumerate(items):
                card = self._make_factor_card(fname_cn, formatted, direction, value)
                grid.addWidget(card, i // 3, i % 3)
            container = QWidget()
            container.setLayout(grid)
            self._single_content_layout.addWidget(container)

    @staticmethod
    def _make_factor_card(name: str, formatted: str, direction: str, value) -> QFrame:
        card = QFrame()
        card.setObjectName("factorCard")
        cl = QVBoxLayout(card)
        cl.setContentsMargins(12, 10, 12, 10)
        cl.setSpacing(4)
        cl.addWidget(QLabel(name))
        value_label = QLabel(formatted if value != 0 else "无数据")
        value_label.setStyleSheet(
            f"font-size: 20px; font-weight: bold; color: {_factor_color(value, direction)};")
        cl.addWidget(value_label)
        dir_text = {"positive": "正向", "negative": "负向", "neutral": "中性"}.get(direction, "")
        cl.addWidget(QLabel(dir_text))
        card.setStyleSheet("""
            QFrame#factorCard {
                background-color: #f8fafc;
                border: 1px solid #e2e8f0;
                border-radius: 8px;
            }
            QLabel { color: #475569; font-size: 12px; }
        """)
        return card

    def _on_export_single(self):
        if not self._single_result:
            self._msg.warning("⚠️ 暂无可导出的因子数据。")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "导出因子数据", "factors_single.csv",
            "CSV Files (*.csv);;All Files (*)")
        if not path:
            return
        res = self._single_result
        row = {
            "股票代码": self._single_selector.get_selected_stock(),
            "查询日期": res["query_date"],
            "财报截止日期": res["report_date"],
        }
        for fname, val in res["factors_raw"].items():
            row[FactorPresenter.FACTOR_NAMES_CN.get(fname, fname)] = val
        pd.DataFrame([row]).to_csv(path, index=False, encoding="utf-8-sig")
        self._msg.success(f"✅ 因子数据已导出到：{path}")

    # ========== 多股排名 ==========

    def _on_query_ranking(self):
        symbols = self._rank_stocks.get_selected()
        factor_name = self._rank_factor.currentData()
        if not symbols:
            self._msg.warning("⚠️ 请至少选择一只股票。")
            return
        if not factor_name:
            self._msg.warning("⚠️ 未选择有效因子。")
            return
        date_option = self._rank_date.currentText()
        self._rank_caption.setText("🔄 查询排名中...")
        worker = AsyncWorker(_query_ranking, symbols, factor_name, date_option, self._db_path)
        worker.finished.connect(self._on_ranking_finished)
        worker.error.connect(lambda e: self._msg.error(f"排名查询出错: {e}"))
        worker.start()

    def _on_ranking_finished(self, result: dict):
        if result.get("error"):
            self._msg.error(result["error"])
            return
        self._rank_result = result
        df = result.get("df")
        self._rank_caption.setText(
            f"查询日期: {result['query_date']} | 实际财报截止日期: {result['report_date']}")
        if df is None or df.empty:
            self._rank_table.set_dataframe(pd.DataFrame())
            self._msg.warning("没有查询到有效数据。")
            self._rank_export.setEnabled(False)
            return
        self._rank_table.set_dataframe(df, auto_resize=True)
        self._rank_export.setEnabled(True)

    def _on_export_ranking(self):
        if self._rank_result is None or self._rank_result.get("df") is None \
                or self._rank_result["df"].empty:
            self._msg.warning("⚠️ 暂无可导出的排名数据。")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "导出排名", "factor_ranking.csv",
            "CSV Files (*.csv);;All Files (*)")
        if not path:
            return
        self._rank_result["df"].to_csv(path, index=False, encoding="utf-8-sig")
        self._msg.success(f"✅ 排名数据已导出到：{path}")


def _factor_color(value, direction: str) -> str:
    if value == 0:
        return "#cccccc"
    if direction == "positive":
        return "#ff6b6b" if value > 0 else "#cccccc"
    if direction == "negative":
        return "#51cf66" if value > 0 else "#cccccc"
    return "#339af0"
