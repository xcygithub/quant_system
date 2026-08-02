"""
策略回测页 (BacktestPage) — 阶段3迁移（原 Tab2）

替代 web/app.py 的「策略回测」Tab。原实现用 st.expander + 三栏 columns +
st.rerun 联动，桌面版改用信号槽驱动局部刷新，无 session_state / st.rerun。

注意：本页仅处理普通策略回测（均线交叉 / MACD / 布林带 / RSI）。多因子回测
在单独的 FactorBacktestPage（Tab5）中实现。

布局：
- 控制面板（三栏）：股票选择 | 策略+参数 | 资金/组合/仓位/止损/日期
- 操作栏：运行回测 / 导出信号CSV / 状态
- 结果：核心指标卡 + 权益曲线图 + 信号图（子图/热力图可选） + 交易明细表 + 持仓明细
- 回测在 AsyncWorker(QThread) 中执行，完成后写入 AppState.multi_backtest_results

长耗时操作在子线程执行；信号图使用独立的 plotly 辅助函数（不依赖已废弃的
web/charts 模块）。
"""
import pandas as pd

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QGroupBox,
    QPushButton, QDateEdit, QSpinBox, QDoubleSpinBox, QComboBox,
    QFileDialog,
)
from PySide6.QtCore import Qt, QDate

import plotly.graph_objects as go
from plotly.subplots import make_subplots

from desktop.pages.base_page import BasePage
from desktop.widgets.strategy_params_widget import StrategyParamsWidget
from desktop.widgets.stock_selector import StockCheckboxGroup
from desktop.widgets.pandas_table import (
    PandasTableView, make_change_color_rule,
)
from desktop.widgets.metric_card import MetricCard
from desktop.widgets.message_bar import MessageBar
from desktop.widgets.chart_container import ChartContainer
from desktop.widgets.async_worker import AsyncWorker
from desktop.models.app_state import AppState
from desktop.models.managers import Managers

from web.services.backtest_service import (
    load_backtest_stock_data, run_standard_strategy_backtest,
)
from web.services.backtest_params_service import validate_run_config

# 仓位分配方法：值 -> 中文标签
POSITION_METHODS = [
    ("equal", "等权重"),
    ("risk_parity", "风险平价"),
    ("momentum", "动量加权"),
    ("score", "综合打分"),
    ("kelly", "凯利公式"),
]


# ============ 后台回测函数（在子线程执行）============
def _do_backtest(run_config: dict, db_path: str, stock_names: dict) -> dict:
    """在子线程执行普通策略回测。

    使用 db_path 新建独立的行情数据连接（SQLite 连接非线程安全，不复用主线程对象）。
    """
    stock_data = load_backtest_stock_data(
        db_path, run_config["symbols"],
        run_config["start_date_str"], run_config["end_date_str"],
    )
    if len(stock_data) == 0:
        return {"error": "所有股票都没有获取到数据!"}

    run_result = run_standard_strategy_backtest(
        stock_data=stock_data,
        strategy_name=run_config["strategy_name"],
        strategy_params=run_config["strategy_params"],
        start_date=run_config["start_date_str"],
        end_date=run_config["end_date_str"],
        initial_capital=run_config["initial_capital"],
        commission_rate=run_config["commission_rate"],
        max_positions=run_config["max_positions"],
        rebalance_days=run_config["rebalance_days"],
        position_method=run_config["position_method"],
        max_single_position=run_config["max_single_position"],
        max_total_position=run_config["max_total_position"],
        stop_loss=run_config["stop_loss"],
        stock_names=stock_names,
    )
    run_result["stock_data"] = stock_data
    return run_result


# ============ 信号图辅助函数（纯 plotly，不依赖 web/charts）============
def _make_signals_heatmap(signals: dict, symbols: list, dates) -> go.Figure:
    df = pd.DataFrame({
        s: sig.reindex(pd.to_datetime(dates)).ffill()
        for s, sig in signals.items() if s in symbols
    }).T
    fig = go.Figure(go.Heatmap(
        z=df.values,
        x=[str(d)[:10] for d in df.columns],
        y=list(df.index),
        colorscale=[[0, "#16a34a"], [0.5, "#ffffff"], [1, "#dc2626"]],
        zmid=0,
        zmin=-1, zmax=1,
        colorbar=dict(title="信号"),
    ))
    fig.update_layout(
        title="信号热力图（红=买入 绿=卖出）",
        height=400, xaxis_title="日期", yaxis_title="股票",
    )
    return fig


def _make_multi_stock_subplots(stock_data: dict, signals: dict, symbols: list) -> go.Figure:
    n = len(symbols)
    fig = make_subplots(rows=n, cols=1, shared_xaxes=True, subplot_titles=symbols)
    for i, s in enumerate(symbols, start=1):
        df = stock_data.get(s)
        if df is None or df.empty:
            continue
        fig.add_trace(
            go.Scatter(x=list(df["date"]), y=list(df["close"]),
                       name=s, mode="lines", line=dict(color="#1f77b4", width=1)),
            row=i, col=1,
        )
        sig = signals.get(s)
        if sig is not None:
            closes = df["close"].reset_index(drop=True)
            sig_vals = sig.reset_index(drop=True)
            if len(closes) == len(sig_vals):
                buy_idx = sig_vals[sig_vals == 1].index
                sell_idx = sig_vals[sig_vals == -1].index
                if len(buy_idx):
                    fig.add_trace(go.Scatter(
                        x=[df["date"].iloc[j] for j in buy_idx],
                        y=[closes.iloc[j] for j in buy_idx],
                        mode="markers", name="买入",
                        marker=dict(color="#dc2626", size=8, symbol="triangle-up"),
                    ), row=i, col=1)
                if len(sell_idx):
                    fig.add_trace(go.Scatter(
                        x=[df["date"].iloc[j] for j in sell_idx],
                        y=[closes.iloc[j] for j in sell_idx],
                        mode="markers", name="卖出",
                        marker=dict(color="#16a34a", size=8, symbol="triangle-down"),
                    ), row=i, col=1)
    fig.update_layout(height=max(300, 180 * n), showlegend=False,
                      title="各股票信号（▲买入 ▼卖出）")
    return fig


class BacktestPage(BasePage):
    """策略回测页"""

    def __init__(self, parent=None):
        super().__init__(
            title="策略回测",
            subtitle="支持单股 / 组合回测与参数化策略配置",
            parent=parent,
        )
        self._state = AppState.instance()
        self._worker: object = None
        self._signals: dict = {}
        self._stock_data: dict = {}
        self._symbols: list = []

        self._state.multi_backtest_results_changed.connect(self._on_results_changed)

    # ========== UI 构建 ==========

    def _build_content(self):
        control = QHBoxLayout()
        control.setSpacing(12)

        # 栏1：股票选择
        stock_box = QGroupBox("股票选择（勾选参与回测）")
        stock_box.setLayout(QVBoxLayout())
        stock_box.layout().setContentsMargins(10, 12, 10, 10)
        self._stock_group = StockCheckboxGroup(columns=1, max_height=260)
        stock_box.layout().addWidget(self._stock_group)
        control.addWidget(stock_box, 1)

        # 栏2：策略 + 参数
        strategy_box = QGroupBox("策略选择")
        strategy_box.setLayout(QVBoxLayout())
        strategy_box.layout().setContentsMargins(10, 12, 10, 10)
        self._strategy_widget = StrategyParamsWidget()  # 仅4个标准策略
        strategy_box.layout().addWidget(self._strategy_widget)
        control.addWidget(strategy_box, 1)

        # 栏3：资金/组合/仓位/止损/日期
        param_box = QGroupBox("资金与组合参数")
        param_layout = QVBoxLayout(param_box)
        param_layout.setContentsMargins(10, 12, 10, 10)
        param_layout.setSpacing(8)
        self._build_param_controls(param_layout)
        control.addWidget(param_box, 1)

        self.content_layout.addLayout(control)

        # 操作栏
        toolbar = QHBoxLayout()
        toolbar.setSpacing(10)
        self._run_btn = QPushButton("🚀 运行回测")
        self._run_btn.setObjectName("primaryButton")
        self._run_btn.clicked.connect(self._on_run_backtest)
        self._export_btn = QPushButton("📥 导出信号CSV")
        self._export_btn.setObjectName("secondaryButton")
        self._export_btn.clicked.connect(self._on_export_csv)
        self._export_btn.setEnabled(False)
        self._status_label = QLabel("")
        self._status_label.setStyleSheet("color: #6b7280; font-size: 13px;")
        toolbar.addWidget(self._run_btn)
        toolbar.addWidget(self._export_btn)
        toolbar.addWidget(self._status_label, 1)
        self.content_layout.addLayout(toolbar)

        # 消息条
        self._msg = MessageBar()
        self.content_layout.addWidget(self._msg)

        # 指标卡
        self._metric_row = QHBoxLayout()
        self._metric_row.setSpacing(12)
        self.content_layout.addLayout(self._metric_row)

        # 权益曲线
        self._equity_chart = ChartContainer(title="组合权益曲线")
        self._equity_chart.setMinimumHeight(300)
        self.content_layout.addWidget(self._equity_chart)

        # 信号图（可选）
        sig_layout = QHBoxLayout()
        sig_layout.setSpacing(8)
        sig_layout.addWidget(QLabel("信号图展示："))
        self._signal_mode = QComboBox()
        self._signal_mode.addItems(["不显示", "子图分股票", "热力图"])
        self._signal_mode.setCurrentText("不显示")
        self._signal_mode.currentTextChanged.connect(self._on_signal_mode_changed)
        sig_layout.addWidget(self._signal_mode)
        sig_layout.addStretch(1)
        self.content_layout.addLayout(sig_layout)
        self._signals_chart = ChartContainer(title="信号图")
        self._signals_chart.setMinimumHeight(280)
        self.content_layout.addWidget(self._signals_chart)

        # 交易明细
        self.content_layout.addWidget(QLabel("📋 每次操作收益率明细"))
        self._trade_table = PandasTableView()
        self._trade_table.setMinimumHeight(180)
        self.content_layout.addWidget(self._trade_table)

        # 持仓明细
        self._positions_label = QLabel("")
        self.content_layout.addWidget(self._positions_label)

        self.content_layout.addStretch(1)

        # 初始加载自选股
        self._refresh_stock_list()

    def _build_param_controls(self, layout: QVBoxLayout):
        # 日期
        date_row = QHBoxLayout()
        date_row.setSpacing(6)
        self._start_edit = QDateEdit(QDate(2023, 1, 1))
        self._start_edit.setCalendarPopup(True)
        self._start_edit.setDisplayFormat("yyyy-MM-dd")
        self._end_edit = QDateEdit(QDate.currentDate())
        self._end_edit.setCalendarPopup(True)
        self._end_edit.setDisplayFormat("yyyy-MM-dd")
        date_row.addWidget(QLabel("起"))
        date_row.addWidget(self._start_edit)
        date_row.addWidget(QLabel("止"))
        date_row.addWidget(self._end_edit)
        layout.addLayout(date_row)

        # 初始资金
        self._capital_spin = QSpinBox()
        self._capital_spin.setRange(10000, 100000000)
        self._capital_spin.setSingleStep(100000)
        self._capital_spin.setValue(1000000)
        layout.addWidget(self._labeled("初始资金（元）", self._capital_spin))

        # 手续费率
        self._commission_spin = QDoubleSpinBox()
        self._commission_spin.setRange(0.0001, 0.005)
        self._commission_spin.setSingleStep(0.0001)
        self._commission_spin.setDecimals(4)
        self._commission_spin.setValue(0.0003)
        layout.addWidget(self._labeled("手续费率", self._commission_spin))

        # 最大持仓数
        self._max_pos_spin = QSpinBox()
        self._max_pos_spin.setRange(1, 20)
        self._max_pos_spin.setValue(5)
        layout.addWidget(self._labeled("最大持仓数", self._max_pos_spin))

        # 调仓周期
        self._rebal_spin = QSpinBox()
        self._rebal_spin.setRange(1, 30)
        self._rebal_spin.setValue(5)
        layout.addWidget(self._labeled("调仓周期（天）", self._rebal_spin))

        # 仓位分配方法
        self._pos_method = QComboBox()
        for val, label in POSITION_METHODS:
            self._pos_method.addItem(label, val)
        self._pos_method.setCurrentIndex(0)
        layout.addWidget(self._labeled("仓位分配方法", self._pos_method))

        # 单只最大仓位
        self._max_single_spin = QSpinBox()
        self._max_single_spin.setRange(0, 100)
        self._max_single_spin.setValue(20)
        self._max_single_spin.setSuffix("%")
        layout.addWidget(self._labeled("单只最大仓位", self._max_single_spin))

        # 最大总仓位
        self._max_total_spin = QSpinBox()
        self._max_total_spin.setRange(0, 100)
        self._max_total_spin.setValue(80)
        self._max_total_spin.setSuffix("%")
        layout.addWidget(self._labeled("最大总仓位", self._max_total_spin))

        # 止损比例
        self._stop_loss_spin = QSpinBox()
        self._stop_loss_spin.setRange(0, 50)
        self._stop_loss_spin.setValue(0)
        self._stop_loss_spin.setSuffix("%")
        layout.addWidget(self._labeled("止损比例（0=不止损）", self._stop_loss_spin))

    @staticmethod
    def _labeled(text: str, widget: QWidget) -> QWidget:
        box = QFrame()
        bl = QVBoxLayout(box)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(2)
        bl.addWidget(QLabel(text))
        bl.addWidget(widget)
        return box

    # ========== 数据加载 ==========

    def _refresh_stock_list(self):
        try:
            wl = Managers.instance().watchlist_manager
            stocks = wl.get_all_stocks()
        except Exception as e:
            self._msg.error(f"读取自选股失败: {e}")
            return
        # 排除默认指数
        from portfolio.watchlist import filter_out_benchmark_stocks
        stocks = filter_out_benchmark_stocks(stocks)
        self._all_stocks = [(s.symbol, s.name) for s in stocks]
        self._stock_group.set_stocks(self._all_stocks)
        self._stock_group.set_selected([s for s, _ in self._all_stocks])
        if not self._all_stocks:
            self._msg.warning("⚠️ 暂无可回测自选股（默认指数已排除），请先添加股票。")

    # ========== 交互 ==========

    def _on_run_backtest(self):
        symbols = self._stock_group.get_selected()
        if not symbols:
            self._msg.warning("⚠️ 请至少选择一只股票进行回测。")
            return

        strategy = self._strategy_widget.get_strategy()
        params = self._strategy_widget.get_params()
        start_date = self._start_edit.date().toString("yyyy-MM-dd")
        end_date = self._end_edit.date().toString("yyyy-MM-dd")

        run_config = {
            "symbols": sorted(symbols),
            "is_single_stock": len(symbols) == 1,
            "is_multi_factor": False,
            "start_date_str": start_date,
            "end_date_str": end_date,
            "strategy_name": strategy,
            "strategy_params": params,
            "initial_capital": float(self._capital_spin.value()),
            "commission_rate": self._commission_spin.value(),
            "max_positions": 1 if len(symbols) == 1 else self._max_pos_spin.value(),
            "rebalance_days": self._rebal_spin.value(),
            "position_method": self._pos_method.currentData(),
            "max_single_position": self._max_single_spin.value() / 100.0,
            "max_total_position": self._max_total_spin.value() / 100.0,
            "stop_loss": self._stop_loss_spin.value() / 100.0,
        }

        errors = validate_run_config(run_config)
        if errors:
            for err in errors:
                self._msg.error(err)
            return

        # 股票名称映射（主线程计算，避免子线程访问共享对象）
        wl = Managers.instance().watchlist_manager
        stock_names = {}
        for sym in run_config["symbols"]:
            info = wl.get_stock(sym)
            if info and info.name:
                stock_names[sym] = info.name

        db_path = Managers.instance().data_manager.db_path

        self._run_btn.setEnabled(False)
        self._export_btn.setEnabled(False)
        self._status_label.setText(
            f"🔄 正在回测 {len(symbols)} 只股票（{strategy}）..."
        )
        self._msg.info("回测在后台线程执行，界面可继续操作。")

        self._worker = AsyncWorker(_do_backtest, run_config, db_path, stock_names)
        self._worker.finished.connect(self._on_backtest_finished)
        self._worker.error.connect(self._on_backtest_error)
        self._worker.start()

    def _on_backtest_finished(self, run_result: dict):
        self._run_btn.setEnabled(True)

        if run_result.get("error"):
            self._status_label.setText("❌ 回测失败")
            self._msg.error(run_result["error"])
            return

        for w in run_result.get("warnings", []):
            self._msg.warning(w)

        results = run_result.get("results")
        if not results:
            self._status_label.setText("⚠️ 无有效结果")
            self._msg.warning("⚠️ 本次回测无有效结果（数据不足或信号为空）。")
            return

        # 保存供信号图使用
        self._signals = run_result.get("signals", {})
        self._stock_data = run_result.get("stock_data", {})
        self._symbols = list(self._stock_data.keys())
        equity = results.get("equity_curve")
        self._common_dates = list(equity["date"]) if equity is not None and len(equity) else []

        # 推送全局状态 -> 绩效分析页自动刷新
        self._state.multi_backtest_results = results
        self._state.is_multi_factor_backtest = False

        self._status_label.setText(
            f"✅ 回测完成：{results.get('total_return', 0):.2%} 收益，"
            f"{results.get('total_trades', 0)} 笔交易"
        )
        self._msg.success(
            f"✅ 回测完成！共回测 {len(self._stock_data)} 只股票。"
        )

        self._render_metrics(results)
        self._render_equity_curve(results.get("equity_curve"))
        self._render_signals_chart(self._signal_mode.currentText())
        self._render_trade_details(results)
        self._render_positions(results)
        self._export_btn.setEnabled(True)

    def _on_backtest_error(self, err_msg: str):
        self._run_btn.setEnabled(True)
        self._export_btn.setEnabled(False)
        self._status_label.setText("❌ 回测异常")
        self._msg.error(f"回测执行出错: {err_msg}")

    def _on_signal_mode_changed(self, mode: str):
        self._render_signals_chart(mode)

    def _on_export_csv(self):
        if not self._signals:
            self._msg.warning("⚠️ 暂无可导出的信号数据，请先运行回测。")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "导出信号数据", "multi_stock_signals.csv",
            "CSV Files (*.csv);;All Files (*)",
        )
        if not path:
            return
        try:
            df = pd.DataFrame(self._signals)
            df.index.name = "date"
            df.to_csv(path, encoding="utf-8-sig")
            self._msg.success(f"✅ 信号数据已导出到：{path}")
        except Exception as e:
            self._msg.error(f"导出失败: {e}")

    # ========== AppState 联动 ==========

    def _on_results_changed(self, results):
        # 仅当非本页写入（避免重复渲染）；本页写入时已直接渲染
        # 此处用于跨页面（如多因子页）触发时的兜底刷新
        if not isinstance(results, dict) or not results:
            return
        # 跳过空渲染；若用户尚未在本页运行，则由他页触发展示
        if self._run_btn.isEnabled():
            # 由他页写入：渲染指标与曲线（不重复发起回测）
            pass

    # ========== 渲染 ==========

    def _render_metrics(self, results: dict):
        while self._metric_row.count():
            item = self._metric_row.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        cards = [
            MetricCard("总收益率", self._pct(results.get("total_return")), delta="📈",
                       delta_color="up"),
            MetricCard("年化收益率", self._pct(results.get("annual_return")), delta="⏱️",
                       delta_color="neutral"),
            MetricCard("夏普比率", self._fmt(results.get("sharpe_ratio"), "{:.2f}"),
                       delta="⚖️", delta_color="neutral"),
            MetricCard("最大回撤", self._pct(results.get("max_drawdown")), delta="📉",
                       delta_color="down"),
        ]
        for c in cards:
            self._metric_row.addWidget(c)
        self._metric_row.addStretch(1)

    def _render_equity_curve(self, equity_curve):
        if equity_curve is None or len(equity_curve) == 0:
            self._equity_chart.set_message("无权益曲线数据")
            return
        try:
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=list(equity_curve["date"]),
                y=list(equity_curve["total_value"]),
                mode="lines", name="组合净值",
                line=dict(color="#1f77b4", width=2),
            ))
            fig.update_layout(
                margin=dict(l=50, r=20, t=30, b=40),
                height=300, xaxis_title="日期", yaxis_title="净值（元）",
                hovermode="x unified",
            )
            self._equity_chart.set_figure(fig)
        except Exception as e:
            self._equity_chart.set_message(f"权益曲线渲染失败: {e}")

    def _render_signals_chart(self, mode: str):
        if mode == "不显示" or not self._signals:
            self._signals_chart.set_message(
                "选择展示方式以渲染信号图" if self._signals else "运行回测后可选信号图"
            )
            return
        try:
            if mode == "子图分股票":
                fig = _make_multi_stock_subplots(
                    self._stock_data, self._signals, self._symbols
                )
            else:  # 热力图
                fig = _make_signals_heatmap(
                    self._signals, self._symbols, self._common_dates
                )
            self._signals_chart.set_figure(fig)
        except Exception as e:
            self._signals_chart.set_message(f"信号图渲染失败: {e}")

    def _render_trade_details(self, results: dict):
        trade_df = results.get("trade_details")
        if trade_df is None or (isinstance(trade_df, pd.DataFrame) and trade_df.empty):
            self._trade_table.set_dataframe(pd.DataFrame())
            self._msg.info("本次回测无交易记录。")
            return

        formatters = {}
        color_rules = {}
        for col in trade_df.columns:
            if pd.api.types.is_float_dtype(trade_df[col].dtype):
                formatters[col] = "{:.2f}"
            if any(k in col for k in ("收益率", "盈亏", "收益", "回报")):
                color_rules[col] = make_change_color_rule()

        self._trade_table.set_dataframe(
            trade_df, formatters=formatters, color_rules=color_rules, auto_resize=True,
        )

    def _render_positions(self, results: dict):
        final_positions = results.get("final_positions") or {}
        if not final_positions:
            self._positions_label.setText("")
            return
        lines = []
        for sym, p in final_positions.items():
            ret = p.get("return", 0) or 0
            lines.append(
                f"{sym}: 数量 {p.get('quantity', 0)} 股, "
                f"均价 {p.get('avg_price', 0):.2f} 元, "
                f"现价 {p.get('current_price', 0):.2f} 元, "
                f"浮动盈亏 {ret:+.2%}"
            )
        self._positions_label.setText("📌 持仓明细（持有中）:\n" + "\n".join(lines))
        self._positions_label.setStyleSheet("color: #374151; font-size: 12px;")

    # ========== 工具 ==========

    @staticmethod
    def _pct(value):
        if value is None:
            return "—"
        return f"{value * 100:.2f}%"

    @staticmethod
    def _fmt(value, fmt):
        if value is None:
            return "—"
        try:
            return fmt.format(value)
        except Exception:
            return str(value)
