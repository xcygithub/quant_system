"""
ToggleSwitch 开关组件 — 替代 QCheckBox 的开关样式

设计规范：
- 轨道尺寸：36px × 20px
- 关闭：背景 --color-neutral-200 (#E9ECEF)
- 开启：背景 --color-primary-500 (#378ADD)
- 滑块：18px 白色圆形
- 标签在右侧，12px

支持：
- 点击/空格切换
- 信号 toggled(bool)
- 可设置标签文本
- 可编程设置 checked 状态
- 自动刷新场景：开启后禁用关联的手动刷新按钮
"""
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel
from PySide6.QtCore import Qt, Signal, Property, QSize, QRectF
from PySide6.QtGui import QPainter, QColor, QBrush, QPen


class ToggleSwitch(QWidget):
    """开关组件

    Usage:
        toggle = ToggleSwitch("自动刷新")
        toggle.toggled.connect(self._on_auto_refresh_toggled)
        toggle.setChecked(True)
    """

    toggled = Signal(bool)

    # 设计规范色值
    _COLOR_ON = "#378ADD"       # --color-primary-500
    _COLOR_OFF = "#E9ECEF"      # --color-neutral-200
    _COLOR_KNOB = "#FFFFFF"
    _COLOR_LABEL = "#6C757D"    # --color-neutral-600

    # 尺寸
    _TRACK_W = 36
    _TRACK_H = 20
    _KNOB_SIZE = 18
    _KNOB_MARGIN = 1  # 轨道内边距

    def __init__(self, label: str = "", parent=None):
        super().__init__(parent)
        self._checked = False
        self._label_text = label

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # 开关轨道
        self._track = _TrackWidget(self)
        self._track.setFixedSize(self._TRACK_W, self._TRACK_H)
        self._track.clicked.connect(self._toggle)
        layout.addWidget(self._track)

        # 标签
        if label:
            lbl = QLabel(label)
            lbl.setStyleSheet(
                f"color: {self._COLOR_LABEL}; font-size: 12px;"
            )
            layout.addWidget(lbl)

        layout.addStretch()
        self.setFixedSize(self.sizeHint())

    def _toggle(self):
        self.setChecked(not self._checked)

    def checked(self) -> bool:
        return self._checked

    def setChecked(self, checked: bool):
        if self._checked != checked:
            self._checked = checked
            self._track.set_checked(checked)
            self.toggled.emit(checked)

    def isChecked(self) -> bool:
        return self._checked

    def sizeHint(self):
        w = self._TRACK_W + 6
        if self._label_text:
            from PySide6.QtGui import QFontMetrics, QFont
            fm = QFontMetrics(QFont())
            w += 6 + fm.horizontalAdvance(self._label_text)
        return QSize(w, self._TRACK_H)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._toggle()
        super().mousePressEvent(event)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Space, Qt.Key_Return):
            self._toggle()
        super().keyPressEvent(event)


class _TrackWidget(QWidget):
    """轨道绘制组件（内部使用）"""

    clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._checked = False
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("点击切换")

    def set_checked(self, checked: bool):
        self._checked = checked
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # 轨道
        track_rect = QRectF(0, 0, self.width(), self.height())
        track_color = QColor(ToggleSwitch._COLOR_ON if self._checked
                             else ToggleSwitch._COLOR_OFF)
        painter.setBrush(QBrush(track_color))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(track_rect, self.height() / 2, self.height() / 2)

        # 滑块
        margin = ToggleSwitch._KNOB_MARGIN
        knob_size = ToggleSwitch._KNOB_SIZE
        if self._checked:
            knob_x = self.width() - knob_size - margin
        else:
            knob_x = margin
        knob_y = (self.height() - knob_size) / 2
        painter.setBrush(QBrush(QColor(ToggleSwitch._COLOR_KNOB)))
        # 滑块阴影
        painter.setPen(QPen(QColor(0, 0, 0, 25), 0.5))
        painter.drawEllipse(QRectF(knob_x, knob_y, knob_size, knob_size))

        painter.end()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
            event.accept()  # 阻止事件冒泡给父级 ToggleSwitch，避免二次 toggle
            return
        super().mousePressEvent(event)
