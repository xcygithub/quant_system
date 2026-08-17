"""
页面基类

所有 Tab 页面的公共基类，提供统一的页面标题和内容区域布局。
后续阶段迁移时，子类在 _build_content() 中填充具体内容。
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QFrame, QLabel, QHBoxLayout
)

from desktop.styles import tokens


class BasePage(QWidget):
    """
    页面基类

    结构：
    ┌──────────────────────────┐
    │  页面标题 (pageTitle)     │
    │  └ 副标题                │
    ├──────────────────────────┤
    │  分隔线 (titleDivider)    │
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
        """构建页面基础布局

        v3.0：边距/间距全部取 tokens（PAGE_MARGIN / SECTION_GAP），
        标题区下方加 1px 分隔线。
        """
        layout = QVBoxLayout(self)
        layout.setContentsMargins(*tokens.PAGE_MARGIN)
        layout.setSpacing(tokens.SECTION_GAP)

        # 页面标题栏（H1 样式，无背景色）
        if self._title:
            title_frame = QFrame()
            title_frame.setObjectName("pageTitle")
            title_layout = QHBoxLayout(title_frame)
            title_layout.setContentsMargins(0, 0, 0, 0)
            title_layout.setSpacing(8)

            # 左侧：主标题 + 副标题
            title_left = QVBoxLayout()
            title_left.setSpacing(2)

            title_label = QLabel(self._title)
            title_label.setObjectName("pageTitleMain")
            title_left.addWidget(title_label)

            if self._subtitle:
                sub_label = QLabel(self._subtitle)
                sub_label.setObjectName("pageTitleSub")
                title_left.addWidget(sub_label)

            title_layout.addLayout(title_left, 1)

            # 右侧：全局操作区域（子类可覆盖 _build_title_actions 添加按钮）
            self._title_actions = QWidget()
            self._title_actions_layout = QHBoxLayout(self._title_actions)
            self._title_actions_layout.setContentsMargins(0, 0, 0, 0)
            self._title_actions_layout.setSpacing(4)
            self._build_title_actions(self._title_actions_layout)
            title_layout.addWidget(self._title_actions)

            layout.addWidget(title_frame)

            # 标题区下方分隔线
            divider = QFrame()
            divider.setObjectName("titleDivider")
            layout.addWidget(divider)

        # 内容区域（子类重写）
        self._content_container = QWidget()
        self._content_layout = QVBoxLayout(self._content_container)
        self._content_layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._content_container, 1)

        # 子类在此填充内容
        self._build_content()

    def _build_title_actions(self, layout):
        """子类可重写：在标题栏右侧添加全局操作按钮（如设置、帮助）"""
        pass

    def _build_content(self):
        """子类重写：构建页面具体内容"""
        pass

    @property
    def content_layout(self) -> QVBoxLayout:
        """获取内容区域的布局，供子类添加控件"""
        return self._content_layout
