"""
标题组件族 — 替代 _render_page_title + HTML注入（25处）

提供：
- SectionTitle: 区块标题（v3.0 去横条化：H2 文字 + 底部细分隔线）
- PageTitle: 页面标题（深色/浅色两种主题）
- PageHero: 顶部产品头（大纯色卡 + 徽章列表）

v3.0（UI 优化 Phase 2）：
- SectionTitle 废除「蓝底横条 + 4px 左竖线」，改为安静的 H2 + 分隔线，
  装饰噪音让位给数据（见 docs/ui_polish_plan.md D4）
- 色值统一从 styles/tokens.py 取，样式由 theme.qss 承载
"""
from typing import List, Optional
from PySide6.QtWidgets import QFrame, QLabel, QHBoxLayout, QVBoxLayout
from PySide6.QtCore import Qt

from desktop.styles import tokens


class SectionTitle(QFrame):
    """区块标题（最常用）

    v3.0 样式：H2 主标题 + 可选副标题 + 底部 1px 分隔线（theme.qss 承载）。

    Usage:
        title = SectionTitle("多因子回测", "统一配置因子、权重与风控参数")
        title = SectionTitle("因子分析", "因子计算、预处理与IC分析")
    """

    def __init__(self, main_text: str, desc: str = "", icon: str = "",
                 parent=None):
        """
        Args:
            main_text: 主标题
            desc: 副标题描述（可选）
            icon: 独立图标 emoji（可选，置于主标题前）
        """
        super().__init__(parent)
        self.setObjectName("sectionTitle")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(2, 4, 2, 0)
        layout.setSpacing(8)

        if icon:
            icon_label = QLabel(icon)
            icon_label.setStyleSheet("font-size: 16px;")
            layout.addWidget(icon_label)

        text_layout = QVBoxLayout()
        text_layout.setSpacing(2)

        main_label = QLabel(main_text)
        main_label.setObjectName("sectionMain")
        text_layout.addWidget(main_label)

        if desc:
            desc_label = QLabel(desc)
            desc_label.setObjectName("sectionDesc")
            text_layout.addWidget(desc_label)

        layout.addLayout(text_layout)
        layout.addStretch()


class PageTitle(QFrame):
    """页面标题（深色或浅色主题）

    Usage:
        title = PageTitle("行情详情终端", theme="dark")
        title = PageTitle("策略回测", "配置参数运行单/多股票回测", theme="light")
    """

    def __init__(self, main_text: str, desc: str = "", theme: str = "dark",
                 parent=None):
        super().__init__(parent)
        self.setObjectName("pageTitle")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(4)

        main_label = QLabel(main_text)
        main_label.setObjectName("pageTitleMain")
        layout.addWidget(main_label)

        if desc:
            desc_label = QLabel(desc)
            desc_label.setObjectName("pageTitleDesc")
            layout.addWidget(desc_label)

        if theme == "dark":
            self.setStyleSheet(f"""
                QFrame#pageTitle {{
                    background-color: {tokens.PRIMARY_HOVER};
                    border-radius: 10px;
                }}
                QLabel#pageTitleMain {{
                    color: #ffffff;
                    font-size: 20px;
                    font-weight: bold;
                }}
                QLabel#pageTitleDesc {{
                    color: {tokens.PRIMARY_100};
                    font-size: 13px;
                }}
            """)
        else:
            self.setStyleSheet(f"""
                QFrame#pageTitle {{
                    background-color: {tokens.PRIMARY_50};
                    border: 1px solid {tokens.PRIMARY_100};
                    border-radius: 10px;
                }}
                QLabel#pageTitleMain {{
                    color: {tokens.PRIMARY_PRESSED};
                    font-size: 20px;
                    font-weight: bold;
                }}
                QLabel#pageTitleDesc {{
                    color: {tokens.PRIMARY_HOVER};
                    font-size: 13px;
                }}
            """)


class PageHero(QFrame):
    """顶部产品头（大卡片 + 徽章列表）

    QSS 用纯色替代渐变。

    Usage:
        hero = PageHero(
            title="量化交易系统 · 专业版工作台",
            subtitle="聚合行情、策略回测、因子研究与数据管理",
            badges=["自选股 12 只", "分组 3 个", "环境 PySide6"],
        )
    """

    def __init__(self, title: str, subtitle: str = "",
                 badges: Optional[List[str]] = None, parent=None):
        super().__init__(parent)
        self.setObjectName("pageHero")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(8)

        title_label = QLabel(title)
        title_label.setObjectName("heroTitle")
        layout.addWidget(title_label)

        if subtitle:
            sub_label = QLabel(subtitle)
            sub_label.setObjectName("heroSubtitle")
            layout.addWidget(sub_label)

        if badges:
            badge_layout = QHBoxLayout()
            badge_layout.setSpacing(8)
            for badge_text in badges:
                badge = QLabel(badge_text)
                badge.setStyleSheet("""
                    background-color: rgba(255,255,255,0.2);
                    color: #ffffff;
                    padding: 4px 12px;
                    border-radius: 12px;
                    font-size: 12px;
                """)
                badge_layout.addWidget(badge)
            badge_layout.addStretch()
            layout.addLayout(badge_layout)
