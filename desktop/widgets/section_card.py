"""
SectionCard — 统一的功能区白卡容器

v3.0（UI 优化 Phase 2）新增：
- 页面功能区一律用白卡承载（工具/筛选区、统计区、数据区），
  替代 QGroupBox 原生贴片标题与裸布局平铺（见 docs/ui_polish_plan.md E3）
- 结构：H3 卡片标题（可选）+ 1px 分隔线 + 内容区

Usage:
    card = SectionCard("筛选条件")
    card.content_layout.addWidget(my_form)
    page_layout.addWidget(card)

    # 无标题纯容器
    card = SectionCard()
    card.content_layout.addLayout(toolbar)
"""
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget

from desktop.styles import tokens


class SectionCard(QFrame):
    """白卡容器（H3 标题 + 内容区）

    Args:
        title: 卡片标题（H3），空字符串则不显示标题与分隔线
        margins: 内容区内边距，默认 CARD_PADDING=16
    """

    def __init__(self, title: str = "", margins: int = tokens.CARD_PADDING,
                 parent=None):
        super().__init__(parent)
        self.setObjectName("sectionCard")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        if title:
            title_label = QLabel(title)
            title_label.setObjectName("sectionCardTitle")
            title_label.setContentsMargins(margins, 12, margins, 10)
            outer.addWidget(title_label)

            divider = QFrame()
            divider.setObjectName("sectionCardDivider")
            outer.addWidget(divider)

        self._content = QWidget()
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(margins, margins, margins, margins)
        self._content_layout.setSpacing(tokens.CONTROL_GAP)
        outer.addWidget(self._content, 1)

    @property
    def content_layout(self) -> QVBoxLayout:
        """卡片内容区布局"""
        return self._content_layout

    @property
    def content_widget(self) -> QWidget:
        return self._content
