"""
EmptyState — 统一空状态组件

v3.0（UI 优化 Phase 2）新增：
- 替代各页面"暂无数据"单行灰字（见 docs/ui_polish_plan.md D5）
- 结构：大图标 + 主文案 + 辅助描述 + 可选引导按钮

Usage:
    empty = EmptyState("📭", "暂无自选股", "添加股票后即可查看行情")
    empty.set_action("+ 添加股票", on_clicked)
    layout.addWidget(empty)
"""
from typing import Callable, Optional
from PySide6.QtWidgets import QFrame, QLabel, QPushButton, QVBoxLayout
from PySide6.QtCore import Qt


class EmptyState(QFrame):
    """空状态占位

    Args:
        icon: 大图标（emoji），如 "📭" / "🔍" / "📊"
        title: 主文案，如 "暂无自选股"
        desc: 辅助描述（可选）
    """

    def __init__(self, icon: str = "📭", title: str = "暂无数据",
                 desc: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("emptyState")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 48, 24, 48)
        layout.setSpacing(8)
        layout.setAlignment(Qt.AlignCenter)

        self._icon_label = QLabel(icon)
        self._icon_label.setObjectName("emptyIcon")
        self._icon_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._icon_label)

        self._title_label = QLabel(title)
        self._title_label.setObjectName("emptyTitle")
        self._title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._title_label)

        self._desc_label = None
        if desc:
            self._desc_label = QLabel(desc)
            self._desc_label.setObjectName("emptyDesc")
            self._desc_label.setAlignment(Qt.AlignCenter)
            self._desc_label.setWordWrap(True)
            layout.addWidget(self._desc_label)

        self._action_btn: Optional[QPushButton] = None

    def set_action(self, text: str, on_clicked: Callable = None):
        """添加引导按钮（主按钮样式）

        Args:
            text: 按钮文案，如 "+ 添加股票"
            on_clicked: 点击回调
        """
        if self._action_btn is None:
            self._action_btn = QPushButton(text)
            self._action_btn.setObjectName("primaryBtn")
            self.layout().addSpacing(8)
            self.layout().addWidget(self._action_btn, 0, Qt.AlignCenter)
        else:
            self._action_btn.setText(text)
        if on_clicked is not None:
            self._action_btn.clicked.connect(on_clicked)

    def set_title(self, text: str):
        self._title_label.setText(text)

    def set_desc(self, text: str):
        if self._desc_label is None:
            self._desc_label = QLabel(text)
            self._desc_label.setObjectName("emptyDesc")
            self._desc_label.setAlignment(Qt.AlignCenter)
            self._desc_label.setWordWrap(True)
            self.layout().insertWidget(2, self._desc_label)
        else:
            self._desc_label.setText(text)
