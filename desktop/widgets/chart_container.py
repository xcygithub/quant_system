"""
ChartContainer 图表容器 — 替代 st.plotly_chart（10处）

过渡期方案：用 QWebEngineView 嵌入 plotly Figure。
阶段4再用 pyqtgraph 原生重写。

设计依据：web 屄 st.plotly_chart 全部传入 plotly Figure 对象，
全部用 use_container_width=True（Qt 布局天然自适应，无需该参数）。
图表类型：Scatter权益曲线、K线图、Heatmap热力图、Scatterpolar雷达图。

注意：QtWebEngine 是可选依赖，未安装时降级为占位提示。
"""
import logging
from typing import Optional
from PySide6.QtWidgets import QFrame, QVBoxLayout, QLabel
from PySide6.QtCore import Qt

logger = logging.getLogger(__name__)


class ChartContainer(QFrame):
    """图表容器

    过渡期：用 QWebEngineView 渲染 plotly Figure。

    Usage:
        container = ChartContainer(title="多因子组合权益曲线")
        container.set_figure(plotly_fig)

        # 无标题
        container = ChartContainer()
        container.set_figure(fig)

    Note:
        需要 PySide6-WebEngine 包。未安装时显示降级占位。
        安装: pip install PySide6-WebEngine
    """

    def __init__(self, title: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("chartContainer")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        if title:
            title_label = QLabel(title)
            title_label.setStyleSheet(
                "color: #1f2937; font-size: 14px; font-weight: bold; "
                "padding: 8px 12px; background-color: #f9fafb; "
                "border-bottom: 1px solid #e5e7eb;"
            )
            layout.addWidget(title_label)

        self._web_view = None
        self._init_web_view(layout)

        self.setStyleSheet("""
            QFrame#chartContainer {
                border: 1px solid #e5e7eb;
                border-radius: 8px;
                background-color: #ffffff;
            }
        """)
        self.setMinimumHeight(300)

    def _init_web_view(self, layout):
        """初始化 WebEngineView（含降级处理）"""
        try:
            from PySide6.QtWebEngineWidgets import QWebEngineView
            self._web_view = QWebEngineView()
            layout.addWidget(self._web_view, 1)
        except ImportError:
            placeholder = QLabel(
                "⚠️ QtWebEngine 未安装，无法渲染图表\n\n"
                "安装命令:\npip install PySide6-WebEngine"
            )
            placeholder.setStyleSheet(
                "color: #6b7280; padding: 40px; background-color: #f9fafb;"
            )
            placeholder.setAlignment(Qt.AlignCenter)
            layout.addWidget(placeholder, 1)
            logger.warning("QtWebEngine 未安装，ChartContainer 降级为占位")

    def set_figure(self, figure):
        """渲染 plotly Figure

        Args:
            figure: plotly Figure 对象（go.Figure 或 make_subplots 结果）
        """
        if self._web_view is None:
            logger.error("QtWebEngine 未安装，无法渲染图表")
            return

        try:
            html = figure.to_html(
                include_plotlyjs='cdn',
                full_html=False,
                config={
                    'displayModeBar': True,
                    'responsive': True,
                }
            )
            self._web_view.setHtml(html)
        except Exception as e:
            logger.exception("渲染图表失败")
            self._web_view.setHtml(
                f"<p style='color:#dc2626;padding:20px;'>渲染失败: {e}</p>"
            )

    def set_html(self, html: str):
        """直接设置 HTML 内容（高级用法）"""
        if self._web_view:
            self._web_view.setHtml(html)

    def set_message(self, text: str, level: str = "info"):
        """显示占位提示（替代 st.info / st.warning 出现在图表位置的场景）

        用于「暂无数据 / 正在加载 / 渲染失败」等空状态，避免留下一块空白画布。

        Args:
            text: 提示文本
            level: info（灰）/ warning（橙）/ error（红）
        """
        colors = {
            "info": "#6b7280",
            "warning": "#d97706",
            "error": "#dc2626",
        }
        color = colors.get(level, colors["info"])
        safe_text = (
            str(text)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace("\n", "<br/>")
        )
        html = (
            "<div style=\"display:flex;align-items:center;justify-content:center;"
            "height:100%;min-height:220px;margin:0;font-family:"
            "'Microsoft YaHei','PingFang SC',sans-serif;background:#ffffff;\">"
            f"<span style=\"color:{color};font-size:14px;text-align:center;\">"
            f"{safe_text}</span></div>"
        )
        if self._web_view:
            self._web_view.setHtml(html)
        else:
            logger.info("ChartContainer 占位提示（无 WebEngine）: %s", text)

    def clear(self):
        """清除图表"""
        if self._web_view:
            self._web_view.setHtml("")


def check_webengine_available() -> bool:
    """检查 QtWebEngine 是否可用

    Returns:
        True 表示可用
    """
    try:
        from PySide6.QtWebEngineWidgets import QWebEngineView  # noqa: F401
        return True
    except ImportError:
        return False
