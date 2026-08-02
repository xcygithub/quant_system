"""
QSS 主题加载器
负责加载和应用全局 Qt StyleSheet
"""
from pathlib import Path
from PySide6.QtWidgets import QApplication


def load_stylesheet() -> str:
    """加载 theme.qss 全局样式表"""
    qss_path = Path(__file__).parent / "theme.qss"
    if qss_path.exists():
        return qss_path.read_text(encoding="utf-8")
    return ""


def apply_theme(app: QApplication) -> None:
    """将全局样式应用到 QApplication"""
    stylesheet = load_stylesheet()
    if stylesheet:
        app.setStyleSheet(stylesheet)
