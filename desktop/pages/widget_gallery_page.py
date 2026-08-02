"""
组件展示页面 (WidgetGalleryPage)

可视化验证阶段2全部8个组件，作为开发调试工具。
集成到主窗口导航，可通过"组件展示"导航项访问。
"""
import time
import pandas as pd
import numpy as np

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QScrollArea,
    QPushButton, QLabel, QFrame,
)
from PySide6.QtCore import Qt

from desktop.widgets.section_title import SectionTitle, PageHero
from desktop.widgets.metric_card import MetricCard, create_metric_row
from desktop.widgets.message_bar import MessageBar
from desktop.widgets.pandas_table import PandasTableView, make_change_color_rule
from desktop.widgets.stock_selector import StockSelector
from desktop.widgets.chart_container import ChartContainer, check_webengine_available
from desktop.widgets.async_worker import run_with_progress


class WidgetGalleryPage(QWidget):
    """组件展示页 — 可视化验证所有阶段2组件"""

    def __init__(self):
        super().__init__()
        self._worker = None  # 保持 worker 引用避免 GC

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(16, 16, 16, 16)
        content_layout.setSpacing(16)

        content_layout.addWidget(self._build_hero())
        content_layout.addWidget(self._build_metrics())
        content_layout.addWidget(self._build_messages())
        content_layout.addWidget(self._build_table())
        content_layout.addWidget(self._build_stock_selector())
        content_layout.addWidget(self._build_chart())
        content_layout.addWidget(self._build_async_demo())
        content_layout.addStretch()

        scroll.setWidget(content)
        layout.addWidget(scroll)

    def _build_hero(self) -> PageHero:
        return PageHero(
            "量化交易系统 · 组件库",
            "阶段2核心组件可视化展示",
            ["8个组件", "68项测试通过", "PySide6"],
        )

    def _build_metrics(self) -> QFrame:
        frame = QFrame()
        layout = QVBoxLayout(frame)
        layout.setSpacing(8)
        layout.addWidget(SectionTitle("📊 MetricCard 指标卡片", "替代 st.metric（30处）"))
        metrics_row = create_metric_row([
            ("总收益率", "12.50%", "📈"),
            ("年化收益率", "8.30%", "📊"),
            ("夏普比率", "1.85", "⚖️"),
            ("最大回撤", "-5.30%", "📉"),
        ])
        layout.addLayout(metrics_row)
        return frame

    def _build_messages(self) -> QFrame:
        frame = QFrame()
        layout = QVBoxLayout(frame)
        layout.setSpacing(8)
        layout.addWidget(SectionTitle("💬 MessageBar 消息条", "替代 st.error/warning/info/success（70处）"))
        for level, text in [
            ('success', '✅ 回测完成！共回测 5 只股票'),
            ('info', '👈 请在左侧配置参数后点击「开始回测」'),
            ('warning', '⚠️ 请至少选择一只股票'),
            ('error', '数据获取失败: 网络超时'),
        ]:
            bar = MessageBar(closable=False)
            bar.show_message(level, text)
            layout.addWidget(bar)
        return frame

    def _build_table(self) -> QFrame:
        frame = QFrame()
        layout = QVBoxLayout(frame)
        layout.setSpacing(8)
        layout.addWidget(SectionTitle("📋 PandasTableView 表格",
                                       "替代 st.dataframe（20处），支持格式化与涨跌着色"))
        table = PandasTableView()
        df = pd.DataFrame({
            '代码': ['000001.SZ', '600000.SH', '000858.SZ', '600519.SH'],
            '名称': ['平安银行', '浦发银行', '五粮液', '贵州茅台'],
            '最新价': [10.52, 7.85, 156.30, 1689.00],
            '涨跌幅': [2.35, -1.20, 0.85, -3.45],
            '成交量': [1234567, 987654, 345678, 567890],
        })
        table.set_dataframe(
            df,
            formatters={'最新价': '{:.2f}', '涨跌幅': '{:+.2f}%', '成交量': '{:,}'},
            color_rules={'涨跌幅': make_change_color_rule()},
        )
        table.setMinimumHeight(200)
        layout.addWidget(table)
        return frame

    def _build_stock_selector(self) -> QFrame:
        frame = QFrame()
        layout = QVBoxLayout(frame)
        layout.setSpacing(8)
        layout.addWidget(SectionTitle("🔍 StockSelector 股票选择器",
                                       "替代 st.selectbox（18处），支持搜索补全"))
        selector = StockSelector(label="切换股票")
        selector.set_stocks(
            ['000001.SZ', '600000.SH', '000858.SZ', '600519.SH'],
            display_map={
                '000001.SZ': '000001.SZ - 平安银行',
                '600000.SH': '600000.SH - 浦发银行',
                '000858.SZ': '000858.SZ - 五粮液',
                '600519.SH': '600519.SH - 贵州茅台',
            }
        )
        layout.addWidget(selector)

        status_label = QLabel("选中: 000001.SZ")
        status_label.setStyleSheet("color: #6b7280; font-size: 12px;")
        selector.stock_changed.connect(
            lambda s: status_label.setText(f"选中: {s}")
        )
        layout.addWidget(status_label)
        return frame

    def _build_chart(self) -> QFrame:
        frame = QFrame()
        layout = QVBoxLayout(frame)
        layout.setSpacing(8)
        layout.addWidget(SectionTitle("📈 ChartContainer 图表容器",
                                       "替代 st.plotly_chart（10处），QtWebEngine嵌入plotly"))
        chart = ChartContainer(title="示例：权益曲线")
        layout.addWidget(chart)

        if check_webengine_available():
            try:
                import plotly.graph_objects as go
                np.random.seed(42)
                fig = go.Figure()
                fig.add_trace(go.Scatter(
                    x=pd.date_range('2024-01-01', periods=30),
                    y=np.cumsum(np.random.randn(30)) + 100,
                    name='权益',
                    line=dict(color='#1d4ed8', width=2),
                ))
                fig.update_layout(title='示例权益曲线', height=350,
                                  margin=dict(l=40, r=20, t=40, b=30))
                chart.set_figure(fig)
            except Exception as e:
                layout.addWidget(QLabel(f"图表渲染失败: {e}"))
        return frame

    def _build_async_demo(self) -> QFrame:
        frame = QFrame()
        layout = QVBoxLayout(frame)
        layout.setSpacing(8)
        layout.addWidget(SectionTitle("⚙️ AsyncWorker 异步任务",
                                       "替代 st.spinner（13处），不冻结UI"))

        btn_layout = QHBoxLayout()
        btn = QPushButton("运行示例任务（3秒，带进度）")
        status_label = QLabel("就绪")
        status_label.setStyleSheet("color: #6b7280; font-size: 12px;")
        btn_layout.addWidget(btn)
        btn_layout.addWidget(status_label)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        def run_task():
            btn.setEnabled(False)
            status_label.setText("运行中...")

            def on_finished(result):
                status_label.setText(f"完成: {result}")
                btn.setEnabled(True)

            def on_error(err):
                status_label.setText(f"错误: {err}")
                btn.setEnabled(True)

            self._worker = run_with_progress(
                self, self._sample_task, 3,
                title="异步任务", message="正在执行示例任务...",
            )
            self._worker.finished.connect(on_finished)
            self._worker.error.connect(on_error)

        btn.clicked.connect(run_task)
        return frame

    @staticmethod
    def _sample_task(seconds, progress_callback=None):
        """示例耗时任务"""
        total = seconds * 10
        for i in range(total):
            if progress_callback:
                progress_callback(
                    int(i / total * 100),
                    f"进度 {i + 1}/{total}"
                )
            time.sleep(0.1)
        return f"耗时 {seconds} 秒完成"
