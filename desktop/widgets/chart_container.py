"""
ChartContainer 图表容器 — 阶段4：pyqtgraph 原生 + WebEngine 兼容双轨

阶段3 时用 QWebEngineView 嵌 plotly 过渡；阶段4 改为以 pyqtgraph 原生为主路径。
所有页面优先用 `set_plot_widget(pg_widget)` 渲染原生图表；
尚未迁移的页面可继续用 `set_figure(plotly_fig)` 走 WebEngine 兼容路径。

内部维护单一「内容槽」QWidget，三种渲染路径互斥切换：
- set_plot_widget(pg.PlotWidget / pg.GraphicsLayoutWidget) — 原生（推荐）
- set_figure(plotly Figure)                                 — WebEngine（兼容）
- set_message(text)                                         — 占位提示
"""
import logging
from typing import Optional

from PySide6.QtWidgets import QFrame, QVBoxLayout, QLabel, QWidget
from PySide6.QtCore import Qt

logger = logging.getLogger(__name__)


class ChartContainer(QFrame):
    """图表容器

    Usage（推荐，阶段4）::
        container = ChartContainer(title="权益曲线")
        from desktop.charts.equity_chart import build_equity_plot
        container.set_plot_widget(build_equity_plot(equity_df))

    Usage（兼容，未迁移页面）::
        container.set_figure(plotly_fig)
    """

    def __init__(self, title: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("chartContainer")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        if title:
            title_label = QLabel(title)
            title_label.setObjectName("chartTitle")  # 样式见 theme.qss
            outer.addWidget(title_label)

        # 内容槽：装 pyqtgraph widget / WebEngine view / 占位 QLabel
        self._content_slot = QWidget()
        self._content_slot.setObjectName("chartContentSlot")
        self._content_layout = QVBoxLayout(self._content_slot)
        self._content_layout.setContentsMargins(0, 0, 0, 0)
        self._content_layout.setSpacing(0)
        outer.addWidget(self._content_slot, 1)

        # 当前内容引用 + 类型标记
        self._content_widget: Optional[QWidget] = None
        self._content_kind: str = ""    # "pyqtgraph" / "webengine" / "message" / ""

        # WebEngine view 懒加载（仅 set_figure 路径用）
        self._web_view = None

        # 外观由 theme.qss 的 #chartContainer / #chartContentSlot 承载（v3.0）
        self.setMinimumHeight(300)

    # ========== 内部：替换内容槽中的 widget ==========
    def _replace_content(self, widget: Optional[QWidget], kind: str):
        """清掉旧内容，装新 widget（widget 为 None 表示只清空）"""
        # 1) 拆掉旧的
        if self._content_widget is not None:
            self._content_layout.takeAt(0)
            try:
                self._content_widget.setParent(None)
                self._content_widget.deleteLater()
            except RuntimeError:
                pass    # C++ 对象已销毁

        self._content_widget = widget
        self._content_kind = kind

        # 2) 装新的
        if widget is not None:
            self._content_layout.addWidget(widget, 1)

    # ========== 主路径：pyqtgraph 原生 ==========
    def set_plot_widget(self, plot_widget: QWidget):
        """渲染 pyqtgraph 原生 widget（PlotWidget / GraphicsLayoutWidget）

        阶段4 主路径，调用方从 desktop/charts/*_chart.py 取构建好的 widget 传入。
        """
        if plot_widget is None:
            self.set_message("图表渲染失败：widget 为空", level="error")
            return
        # 释放旧的 WebEngine（如果之前用过）
        self._release_web_view()
        self._replace_content(plot_widget, "pyqtgraph")

    # ========== 兼容路径：plotly Figure via WebEngine ==========
    def set_figure(self, figure):
        """渲染 plotly Figure（兼容路径，未迁移页面继续用）

        内部懒加载 QWebEngineView。未安装 PySide6-WebEngine 时降级为占位。
        """
        view = self._ensure_web_view()
        if view is None:
            self.set_message(
                "⚠️ QtWebEngine 未安装，无法渲染 plotly 图表\n"
                "安装: pip install PySide6-WebEngine",
                level="warning",
            )
            return

        try:
            html = figure.to_html(
                include_plotlyjs='cdn',
                full_html=False,
                config={'displayModeBar': True, 'responsive': True},
            )
            view.setHtml(html)
        except Exception as e:
            logger.exception("渲染图表失败")
            self.set_message(f"渲染失败: {e}", level="error")

    def set_html(self, html: str):
        """直接设置 HTML 内容（高级用法，仅 WebEngine 路径）"""
        view = self._ensure_web_view()
        if view is not None:
            view.setHtml(html)

    def _ensure_web_view(self):
        """懒加载 QWebEngineView；已切换到 pyqtgraph 时需重新装回"""
        if self._web_view is not None:
            # 之前用过，确保它还在内容槽里
            if self._content_kind != "webengine":
                self._replace_content(self._web_view, "webengine")
            return self._web_view

        try:
            from PySide6.QtWebEngineWidgets import QWebEngineView
        except ImportError:
            logger.warning("QtWebEngine 未安装，ChartContainer 无法渲染 plotly")
            return None

        self._web_view = QWebEngineView()
        self._replace_content(self._web_view, "webengine")
        return self._web_view

    def _release_web_view(self):
        """彻底释放 WebEngine view（迁移到 pyqtgraph 后释放内存）"""
        if self._web_view is not None:
            try:
                self._web_view.deleteLater()
            except RuntimeError:
                pass
            self._web_view = None

    # ========== 占位提示 ==========
    def set_message(self, text: str, level: str = "info"):
        """显示占位提示（替代 st.info / st.warning 出现在图表位置的场景）

        Args:
            text: 提示文本
            level: info（灰）/ warning（橙）/ error（红）
        """
        # 切到 pyqtgraph 路径后，message 用 QLabel 占位；不再走 WebEngine
        self._release_web_view()

        from desktop.styles import tokens
        colors = {
            "info": tokens.TEXT_3,
            "warning": "#d97706",
            "error": tokens.UP,
        }
        color = colors.get(level, colors["info"])
        label = QLabel(str(text))
        label.setAlignment(Qt.AlignCenter)
        label.setStyleSheet(
            f"color: {color}; padding: 40px; background-color: #FFFFFF; "
            "font-size: 14px;"
        )
        label.setWordWrap(True)
        self._replace_content(label, "message")

    # ========== 清空 ==========
    def clear(self):
        """清除图表"""
        self._release_web_view()
        self._replace_content(None, "")

    # ========== 诊断 ==========
    @property
    def content_kind(self) -> str:
        """当前内容类型：'pyqtgraph' / 'webengine' / 'message' / ''"""
        return self._content_kind


def check_webengine_available() -> bool:
    """检查 QtWebEngine 是否可用（兼容旧代码）"""
    try:
        from PySide6.QtWebEngineWidgets import QWebEngineView  # noqa: F401
        return True
    except ImportError:
        return False
