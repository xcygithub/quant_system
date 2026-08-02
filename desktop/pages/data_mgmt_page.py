"""财务数据管理页面 (Tab 3) — 阶段3迁移"""
from PySide6.QtWidgets import QLabel
from desktop.pages.base_page import BasePage


class DataMgmtPage(BasePage):
    def __init__(self, parent=None):
        super().__init__(title="财务数据管理", subtitle="Baostock 数据获取与更新", parent=parent)

    def _build_content(self):
        placeholder = QLabel("⏳ 阶段3迁移：数据更新、新鲜度检查、批量获取")
        placeholder.setStyleSheet("color: #64748b; font-size: 14px; padding: 40px;")
        self.content_layout.addWidget(placeholder)
