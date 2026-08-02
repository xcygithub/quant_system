"""策略回测页面 (Tab 2) — 阶段3迁移"""
from PySide6.QtWidgets import QLabel
from desktop.pages.base_page import BasePage


class BacktestPage(BasePage):
    def __init__(self, parent=None):
        super().__init__(title="策略回测", subtitle="单股票/多股票策略回测", parent=parent)

    def _build_content(self):
        placeholder = QLabel("⏳ 阶段3迁移：策略选择、参数配置、回测执行、结果展示")
        placeholder.setStyleSheet("color: #64748b; font-size: 14px; padding: 40px;")
        self.content_layout.addWidget(placeholder)
