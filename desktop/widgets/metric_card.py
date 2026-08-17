"""
MetricCard 指标卡片 — 替代 st.metric（30处）

三槽位：label / value / delta
- value 接预格式化字符串（由调用方用 f-string 格式化，如 f"{ret:.2%}"）
- delta 可承载 emoji icon（📈📊⚖️📉🌊）或文本（"+2.3%"）
- 支持涨跌色（涨红跌绿，中国股市惯例）

v3.0（UI 优化 Phase 2）：
- 删除内置 Tailwind 色板与内联样式，色值统一从 styles/tokens.py 取
- 数值字号 24px（FONT_METRIC），与页面标题 H1(20px) 拉开层级
- 外观由 theme.qss 的 #metricCard/#metricLabel/#metricValue/#metricDelta 控制
"""
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QHBoxLayout, QSizePolicy
from PySide6.QtCore import Qt

from desktop.styles.tokens import UP, DOWN, TEXT_3


# ===== 颜色常量（从 tokens 取，保留旧名兼容外部引用）=====
COLOR_UP = UP           # 红色 - 涨
COLOR_DOWN = DOWN       # 绿色 - 跌
COLOR_NEUTRAL = TEXT_3  # 灰色 - 中性


class MetricCard(QFrame):
    """指标卡片

    Usage:
        card = MetricCard("总收益率", "12.50%", delta="📈")
        card = MetricCard("最大回撤", "-5.30%", delta="📉", delta_color="down")
        card = MetricCard("夏普比率", "1.85", delta="⚖️")
        card = MetricCard("扫描股票数", "4,523")

    Args:
        label: 指标名（如"总收益率"）
        value: 指标值（预格式化字符串，如"12.50%"）
        delta: 增量/图标（如"📈"或"+2.3%"）
        delta_color: 增量颜色模式
            - 'auto': 自动判断（含+/涨→红，含-/跌→绿，纯emoji不着色）
            - 'up': 红色（涨）
            - 'down': 绿色（跌）
            - 'neutral': 灰色
            - 'none': 不着色
    """

    def __init__(self, label: str = "", value: str = "", delta: str = "",
                 delta_color: str = "auto", parent=None):
        super().__init__(parent)
        self.setObjectName("metricCard")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(4)

        # label（指标名）
        self._label_label = QLabel(label)
        self._label_label.setObjectName("metricLabel")
        layout.addWidget(self._label_label)

        # value（指标值）
        self._value_label = QLabel(value)
        self._value_label.setObjectName("metricValue")
        layout.addWidget(self._value_label)

        # delta（增量/图标）
        self._delta_label = None
        if delta:
            self._delta_label = QLabel(delta)
            self._delta_label.setObjectName("metricDelta")
            self._set_delta_color(delta, delta_color)
            layout.addWidget(self._delta_label)

    def _set_delta_color(self, text: str, mode: str):
        if mode == 'none' or self._delta_label is None:
            return

        if mode == 'up':
            color = COLOR_UP
        elif mode == 'down':
            color = COLOR_DOWN
        elif mode == 'neutral':
            color = COLOR_NEUTRAL
        else:  # auto
            color = self._auto_color(text)

        if color:
            self._delta_label.setStyleSheet(f"color: {color};")
        else:
            self._delta_label.setStyleSheet("")

    @staticmethod
    def _auto_color(text: str) -> str:
        """自动判断涨跌色（中国股市惯例：涨红跌绿）

        纯 emoji（如 📈）无明确方向，不着色。
        含 +/-/涨/跌/↑↓ 等符号才着色。
        """
        if not text:
            return None
        # 涨：红色
        if any(c in text for c in ['+', '涨', '↑', '🔴', '增']):
            return COLOR_UP
        # 跌：绿色
        if any(c in text for c in ['-', '跌', '↓', '🟢', '减']):
            return COLOR_DOWN
        # 纯 emoji 或无方向：不着色
        return None

    def set_label(self, text: str):
        self._label_label.setText(text)

    def set_value(self, text: str):
        self._value_label.setText(text)

    def set_delta(self, text: str, delta_color: str = "auto"):
        """设置/更新 delta

        若卡片创建时无 delta，会动态添加。
        """
        if self._delta_label is None:
            self._delta_label = QLabel(text)
            self._delta_label.setObjectName("metricDelta")
            self.layout().addWidget(self._delta_label)
        else:
            self._delta_label.setText(text)
        self._set_delta_color(text, delta_color)

    def update(self, label: str = None, value: str = None,
               delta: str = None, delta_color: str = "auto"):
        """批量更新卡片内容（None 表示不修改该项）"""
        if label is not None:
            self._label_label.setText(label)
        if value is not None:
            self._value_label.setText(value)
        if delta is not None:
            self.set_delta(delta, delta_color)


def create_metric_row(metrics, parent=None) -> QHBoxLayout:
    """创建一行指标卡布局（卡片等宽分布）

    Args:
        metrics: [(label, value, delta), ...] 或 [(label, value), ...]
            delta 可选，可为 emoji 或文本
        parent: 父控件

    Returns:
        QHBoxLayout（已添加所有卡片，等宽）

    Usage:
        row = create_metric_row([
            ("总收益率", "12.50%", "📈"),
            ("夏普比率", "1.85", "⚖️"),
            ("最大回撤", "-5.30%", "📉"),
        ])
        container.setLayout(row)
    """
    layout = QHBoxLayout(parent)
    layout.setSpacing(12)
    for item in metrics:
        label = item[0] if len(item) > 0 else ""
        value = item[1] if len(item) > 1 else ""
        delta = item[2] if len(item) > 2 else ""
        card = MetricCard(label, value, delta)
        layout.addWidget(card, 1)  # 等宽
    return layout
