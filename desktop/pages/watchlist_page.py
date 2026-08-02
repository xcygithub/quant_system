"""自选股管理页面 (Tab 1) — 阶段3迁移"""
from PySide6.QtWidgets import QLabel, QVBoxLayout
from desktop.pages.base_page import BasePage


class WatchlistPage(BasePage):
    def __init__(self, parent=None):
        super().__init__(title="自选股管理", subtitle="行情展示与分组管理", parent=parent)

    def _build_content(self):
        placeholder = QLabel("⏳ 阶段3迁移：自选股行情展示、分组管理、股票详情")
        placeholder.setStyleSheet("color: #64748b; font-size: 14px; padding: 40px;")
        self.content_layout.addWidget(placeholder)
