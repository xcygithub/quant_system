"""多因子回测页面 (Tab 5) — 阶段3迁移"""
from PySide6.QtWidgets import QLabel
from desktop.pages.base_page import BasePage


class FactorBacktestPage(BasePage):
    def __init__(self, parent=None):
        super().__init__(title="多因子回测", subtitle="IC 动态权重与因子归因分析", parent=parent)

    def _build_content(self):
        placeholder = QLabel("⏳ 阶段3迁移：因子配置、IC加权、回测执行、归因分析")
        placeholder.setStyleSheet("color: #64748b; font-size: 14px; padding: 40px;")
        self.content_layout.addWidget(placeholder)
