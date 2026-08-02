"""
绩效分析页 (PerformancePage) — 阶段3迁移（原 Tab7）

原 Streamlit 版仅为 3 行空壳（render_section_title + st.info），读取
multi_backtest_results 的接口从未接线。桌面版将其升级为真实的绩效展示页：

- 读取 AppState.multi_backtest_results（由策略回测/多因子回测页运行后写入）
- 展示核心收益指标卡（总收益率/年化/夏普/最大回撤）
- 展示交易统计（总交易/买入/卖出）
- 渲染权益曲线（ChartContainer 封装 plotly，过渡期方案）
- 展示回测过程中的 warnings

无 st.session_state / st.rerun，状态通过 AppState 信号驱动局部刷新。
"""
import plotly.graph_objects as go

from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout,
                                 QLabel, QFrame, QScrollArea)
from PySide6.QtCore import Qt

from desktop.pages.base_page import BasePage
from desktop.widgets.section_title import SectionTitle
from desktop.widgets.metric_card import MetricCard, create_metric_row
from desktop.widgets.message_bar import MessageBar
from desktop.widgets.chart_container import ChartContainer
from desktop.models.app_state import AppState


class PerformancePage(BasePage):
    """绩效分析页"""

    def __init__(self, parent=None):
        # 必须在 super().__init__() 之前准备状态：
        # BasePage.__init__ 内部会触发 _setup_ui() -> _build_content()，
        # 而 _build_content() 末尾会读取 self._state.multi_backtest_results 做初始渲染。
        self._state = AppState.instance()

        super().__init__(
            title="绩效分析",
            subtitle="汇总回测表现并沉淀关键风险收益指标",
            parent=parent,
        )
        self._state.multi_backtest_results_changed.connect(self._on_results_changed)

    def _build_content(self):
        # 指标卡行
        self._metric_row = QHBoxLayout()
        self._metric_row.setSpacing(12)
        self.content_layout.addLayout(self._metric_row)

        # 交易统计行
        self._trade_row = QHBoxLayout()
        self._trade_row.setSpacing(12)
        self.content_layout.addLayout(self._trade_row)

        # 权益曲线图
        self._chart = ChartContainer(title="权益曲线")
        self._chart.setMinimumHeight(320)
        self.content_layout.addWidget(self._chart)

        # 警告信息
        self._warnings = MessageBar()
        self.content_layout.addWidget(self._warnings)

        self.content_layout.addStretch(1)

        # 初始渲染（若已有结果）
        self._render(self._state.multi_backtest_results)

    # ========== 数据渲染 ==========

    def _on_results_changed(self, results):
        self._render(results)

    def _render(self, payload):
        """渲染回测结果。payload 可能是完整返回 dict（含 'results' 键）或 results 本身。"""
        # 清空旧控件
        self._clear_layout(self._metric_row)
        self._clear_layout(self._trade_row)

        if not payload:
            self._warnings.info("请先在【策略回测】或【多因子回测】中运行回测，"
                                 "结果将自动在此展示。")
            self._chart.set_message("暂无回测数据")
            return

        results = payload.get("results", payload) if isinstance(payload, dict) else payload
        if not isinstance(results, dict) or not results:
            self._warnings.info("暂无回测结果。")
            self._chart.set_message("暂无回测数据")
            return

        self._warnings.clear()

        # 核心收益指标卡
        cards = [
            MetricCard("总收益率", self._pct(results.get("total_return"))),
            MetricCard("年化收益率", self._pct(results.get("annual_return"))),
            MetricCard("夏普比率", self._fmt(results.get("sharpe_ratio"), "{:.2f}")),
            MetricCard("最大回撤", self._pct(results.get("max_drawdown"))),
        ]
        for c in cards:
            self._metric_row.addWidget(c)

        # 交易统计
        trades = results.get("total_trades", 0)
        buy = results.get("buy_trades", 0)
        sell = results.get("sell_trades", 0)
        stats = [
            MetricCard("总交易次数", str(trades)),
            MetricCard("买入交易", str(buy)),
            MetricCard("卖出交易", str(sell)),
        ]
        for c in stats:
            self._trade_row.addWidget(c)

        # 权益曲线
        self._render_equity_curve(results.get("equity_curve"))

        # 警告
        warnings = payload.get("warnings") if isinstance(payload, dict) else None
        if warnings:
            for w in warnings:
                self._warnings.warning(w)

    def _render_equity_curve(self, equity_curve):
        if equity_curve is None or len(equity_curve) == 0:
            self._chart.set_message("无权益曲线数据")
            return
        try:
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=list(equity_curve["date"]),
                y=list(equity_curve["total_value"]),
                mode="lines",
                name="权益曲线",
                line=dict(color="#1d4ed8", width=2),
            ))
            fig.update_layout(
                margin=dict(l=50, r=20, t=30, b=40),
                height=320,
                xaxis_title="日期",
                yaxis_title="总资产（元）",
                hovermode="x unified",
            )
            self._chart.set_figure(fig)
        except Exception as e:
            self._chart.set_message(f"权益曲线渲染失败: {e}")

    # ========== 工具方法 ==========

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

    @staticmethod
    def _clear_layout(layout):
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
