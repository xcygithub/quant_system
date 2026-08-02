"""绩效分析页面 (Tab 7) — 阶段3迁移"""
from PySide6.QtWidgets import QLabel
from desktop.pages.base_page import BasePage


class PerformancePage(BasePage):
    def __init__(self, parent=None):
        super().__init__(title="绩效分析", subtitle="收益归因与风险指标", parent=parent)

    def _build_content(self):
        placeholder = QLabel("⏳ 阶段3迁移：绩效摘要、权益曲线、交易明细")
        placeholder.setStyleSheet("color: #64748b; font-size: 14px; padding: 40px;")
        self.content_layout.addWidget(placeholder)
