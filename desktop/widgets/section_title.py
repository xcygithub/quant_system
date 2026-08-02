"""
标题组件族 — 替代 _render_page_title + HTML注入（25处）

提供：
- SectionTitle: 区块标题（最常用，左边框 + icon + 主副标题）
- PageTitle: 页面标题（深色/浅色两种主题）
- PageHero: 顶部产品头（大渐变卡 + 徽章列表）

设计依据：web 屄有4套标题组件：
- .app-hero: 深蓝渐变大卡 + hero-badge 胶囊标签（render_app_hero）
- .market-page-title: 深色渐变标题卡
- .section-title: 左边框 + 浅蓝底 + icon+主副标题（_render_page_title）
- _render_subsection_title: 小节标题

注意：QSS 不支持复杂渐变，统一用纯色替代（计划文档已确认）。
"""
from typing import List, Optional
from PySide6.QtWidgets import QFrame, QLabel, QHBoxLayout, QVBoxLayout
from PySide6.QtCore import Qt


class SectionTitle(QFrame):
    """区块标题（最常用）

    左边框 + icon + 主标题 + 副标题（可选）
    替代 _render_page_title 的 .section-title 结构。

    Usage:
        title = SectionTitle("📊 多因子回测", "统一配置因子、权重与风控参数")
        title = SectionTitle("🔬 因子分析", "因子计算、预处理与IC分析")
        title = SectionTitle("📥 财务数据管理", "Baostock财务数据获取与管理")
    """

    def __init__(self, main_text: str, desc: str = "", icon: str = "",
                 parent=None):
        """
        Args:
            main_text: 主标题（可含 emoji，如"📊 多因子回测"）
            desc: 副标题描述（可选）
            icon: 独立图标 emoji（若 main_text 已含 emoji 可不传）
        """
        super().__init__(parent)
        self.setObjectName("sectionTitle")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(8)

        if icon:
            icon_label = QLabel(icon)
            icon_label.setStyleSheet("font-size: 18px;")
            layout.addWidget(icon_label)

        text_layout = QVBoxLayout()
        text_layout.setSpacing(2)

        main_label = QLabel(main_text)
        main_label.setStyleSheet(
            "color: #1e40af; font-size: 16px; font-weight: bold;"
        )
        text_layout.addWidget(main_label)

        if desc:
            desc_label = QLabel(desc)
            desc_label.setStyleSheet("color: #6b7280; font-size: 12px;")
            text_layout.addWidget(desc_label)

        layout.addLayout(text_layout)
        layout.addStretch()

        self.setStyleSheet("""
            QFrame#sectionTitle {
                background-color: #eff6ff;
                border-left: 4px solid #2563eb;
                border-radius: 4px;
            }
        """)


class PageTitle(QFrame):
    """页面标题（深色或浅色主题）

    替代 .market-page-title（深色渐变标题卡）。

    Usage:
        title = PageTitle("📈 行情详情终端", theme="dark")
        title = PageTitle("策略回测", "配置参数运行单/多股票回测", theme="light")
    """

    def __init__(self, main_text: str, desc: str = "", theme: str = "dark",
                 parent=None):
        """
        Args:
            main_text: 主标题（可含 emoji）
            desc: 副标题（可选）
            theme: 'dark' 深色背景白字 / 'light' 浅色背景深字
        """
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
            self.setStyleSheet("""
                QFrame#pageTitle {
                    background-color: #1e3a8a;
                    border-radius: 10px;
                }
                QLabel#pageTitleMain {
                    color: #ffffff;
                    font-size: 20px;
                    font-weight: bold;
                }
                QLabel#pageTitleDesc {
                    color: #bfdbfe;
                    font-size: 13px;
                }
            """)
        else:
            self.setStyleSheet("""
                QFrame#pageTitle {
                    background-color: #f0f9ff;
                    border: 1px solid #bae6fd;
                    border-radius: 10px;
                }
                QLabel#pageTitleMain {
                    color: #0c4a6e;
                    font-size: 20px;
                    font-weight: bold;
                }
                QLabel#pageTitleDesc {
                    color: #0369a1;
                    font-size: 13px;
                }
            """)


class PageHero(QFrame):
    """顶部产品头（大卡片 + 徽章列表）

    替代 render_app_hero 的 .app-hero 结构。
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
        title_label.setStyleSheet(
            "color: #ffffff; font-size: 22px; font-weight: bold;"
        )
        layout.addWidget(title_label)

        if subtitle:
            sub_label = QLabel(subtitle)
            sub_label.setObjectName("heroSubtitle")
            sub_label.setStyleSheet("color: #bfdbfe; font-size: 13px;")
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

        self.setStyleSheet("""
            QFrame#pageHero {
                background-color: #1d4ed8;
                border-radius: 12px;
            }
        """)
