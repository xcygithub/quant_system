"""
页面基类

所有 Tab 页面的公共基类，提供统一的页面标题和内容区域布局。
后续阶段迁移时，子类在 _build_content() 中填充具体内容。
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QFrame, QLabel, QHBoxLayout
)


class BasePage(QWidget):
    """
    页面基类

    结构：
    ┌──────────────────────────┐
    │  页面标题 (pageTitle)     │
    │  └ 副标题                │
    ├──────────────────────────┤
    │                          │
    │  内容区域 (子类实现)      │
    │                          │
    └──────────────────────────┘
    """

    def __init__(self, title: str = "", subtitle: str = "", parent=None):
        super().__init__(parent)
        self._title = title
        self._subtitle = subtitle
        self._setup_ui()

    def _setup_ui(self):
        """构建页面基础布局"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # 页面标题栏
        if self._title:
            title_frame = QFrame()
            title_frame.setObjectName("pageTitle")
            title_layout = QHBoxLayout(title_frame)
            title_layout.setContentsMargins(14, 12, 14, 12)

            title_label = QLabel(self._title)
            title_label.setObjectName("pageTitleMain")
            title_layout.addWidget(title_label)

            if self._subtitle:
                sub_label = QLabel(self._subtitle)
                sub_label.setObjectName("pageTitleSub")
                title_layout.addStretch()
                title_layout.addWidget(sub_label)

            layout.addWidget(title_frame)

        # 内容区域（子类重写）
        self._content_container = QWidget()
        self._content_layout = QVBoxLayout(self._content_container)
        self._content_layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._content_container, 1)

        # 子类在此填充内容
        self._build_content()

    def _build_content(self):
        """子类重写：构建页面具体内容"""
        pass

    @property
    def content_layout(self) -> QVBoxLayout:
        """获取内容区域的布局，供子类添加控件"""
        return self._content_layout
