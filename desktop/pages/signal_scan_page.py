"""信号扫描页面 (Tab 6) — 阶段3迁移"""
from PySide6.QtWidgets import QLabel
from desktop.pages.base_page import BasePage


class SignalScanPage(BasePage):
    def __init__(self, parent=None):
        super().__init__(title="信号扫描", subtitle="全市场批量信号扫描", parent=parent)

    def _build_content(self):
        placeholder = QLabel("⏳ 阶段3迁移：扫描配置、批量执行、结果过滤、导出")
        placeholder.setStyleSheet("color: #64748b; font-size: 14px; padding: 40px;")
        self.content_layout.addWidget(placeholder)
