"""
量化交易系统 - 桌面客户端入口

启动方式（任选其一）：
    python -m desktop.main
    python desktop/main.py
    run_desktop.bat

无论哪种方式启动，main.py 都会自动将项目根目录加入 sys.path，
因此可以直接运行而不需要手动设置 PYTHONPATH。
"""
import sys
import logging
from pathlib import Path

# 将项目根目录加入 sys.path（兼容多种启动方式）
# 当以 `python desktop/main.py` 运行时，Python 默认把 desktop/ 加入 sys.path，
# 而我们需要在项目根级别 import desktop.* 包，所以需要显式修复路径。
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFont

from desktop.styles.theme import apply_theme
from desktop.models.log_handler import LogManager
from desktop.main_window import MainWindow


def main():
    """应用入口"""
    # 1. 创建 QApplication（高 DPI 支持）
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt_HighDpiScaleFactorRoundingPolicy()
    )

    app = QApplication(sys.argv)
    app.setApplicationName("量化交易系统")
    app.setApplicationVersion("0.1.0")
    app.setOrganizationName("QuantSystem")

    # 2. 设置默认字体
    font = QFont("Microsoft YaHei", 9)
    app.setFont(font)

    # 3. 应用全局 QSS 主题
    apply_theme(app)

    # 4. 初始化日志系统
    log_manager = LogManager()
    log_manager.setup(console=True, file_log=True)

    logging.info("=" * 50)
    logging.info("量化交易系统桌面版启动")
    logging.info("=" * 50)

    # 5. 创建并显示主窗口
    window = MainWindow(log_manager=log_manager)
    window.show()

    logging.info("应用窗口已显示，进入事件循环")

    # 6. 运行事件循环
    exit_code = app.exec()
    sys.exit(exit_code)


def Qt_HighDpiScaleFactorRoundingPolicy():
    """获取高 DPI 缩放舍入策略（兼容写法）"""
    from PySide6.QtCore import Qt
    return Qt.HighDpiScaleFactorRoundingPolicy.PassThrough


if __name__ == "__main__":
    main()
