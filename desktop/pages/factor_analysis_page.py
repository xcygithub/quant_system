"""因子分析页面 (Tab 4) — 阶段3迁移"""
from PySide6.QtWidgets import QLabel
from desktop.pages.base_page import BasePage


class FactorAnalysisPage(BasePage):
    def __init__(self, parent=None):
        super().__init__(title="因子分析", subtitle="因子 IC 分析与有效性评估", parent=parent)

    def _build_content(self):
        placeholder = QLabel("⏳ 阶段3迁移：因子 IC 计算、分层回测、有效性判定")
        placeholder.setStyleSheet("color: #64748b; font-size: 14px; padding: 40px;")
        self.content_layout.addWidget(placeholder)
