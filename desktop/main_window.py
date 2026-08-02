"""
主窗口 (MainWindow)

桌面应用主界面，包含：
- 左侧导航栏（7个功能页）
- 右侧页面堆栈（QStackedWidget）
- 底部状态栏 + 可折叠日志面板
- 顶部菜单栏
"""
import logging
from typing import Optional

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QAction, QKeySequence, QCloseEvent
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QListWidget, QListWidgetItem, QStackedWidget,
    QStatusBar, QDockWidget, QTextEdit, QSplitter,
    QLabel, QToolBar, QSizePolicy
)

from desktop.models.app_state import AppState
from desktop.models.log_handler import LogManager
from desktop.pages.watchlist_page import WatchlistPage
from desktop.pages.backtest_page import BacktestPage
from desktop.pages.data_mgmt_page import DataMgmtPage
from desktop.pages.factor_analysis_page import FactorAnalysisPage
from desktop.pages.factor_backtest_page import FactorBacktestPage
from desktop.pages.signal_scan_page import SignalScanPage
from desktop.pages.performance_page import PerformancePage
from desktop.pages.widget_gallery_page import WidgetGalleryPage

logger = logging.getLogger(__name__)

# 导航项配置：(显示名称, 页面类)
NAV_ITEMS = [
    ("自选股管理", WatchlistPage),
    ("策略回测", BacktestPage),
    ("财务数据管理", DataMgmtPage),
    ("因子分析", FactorAnalysisPage),
    ("多因子回测", FactorBacktestPage),
    ("信号扫描", SignalScanPage),
    ("绩效分析", PerformancePage),
    ("组件展示", WidgetGalleryPage),  # 阶段2开发调试
]


class MainWindow(QMainWindow):
    """量化交易系统桌面主窗口"""

    def __init__(self, log_manager: Optional[LogManager] = None):
        super().__init__()
        self._log_manager = log_manager
        self._state = AppState.instance()

        self.setWindowTitle("量化交易系统 · 桌面版")
        self.resize(1400, 900)
        self.setMinimumSize(1000, 650)

        self._setup_ui()
        self._setup_menu()
        self._setup_statusbar()
        self._setup_log_panel()
        self._setup_connections()

        logger.info("主窗口初始化完成")

    # ========== UI 构建 ==========

    def _setup_ui(self):
        """构建主界面布局：左侧导航 + 右侧页面堆栈"""
        central = QWidget()
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 侧边导航栏
        self._nav_list = QListWidget()
        self._nav_list.setObjectName("navList")
        self._nav_list.setFixedWidth(180)
        self._nav_list.setIconSize(QSize(20, 20))
        self._nav_list.setCurrentRow(0)

        # 页面堆栈
        self._page_stack = QStackedWidget()

        # 添加导航项和页面
        for name, page_class in NAV_ITEMS:
            item = QListWidgetItem(name)
            self._nav_list.addItem(item)
            page = page_class()
            self._page_stack.addWidget(page)

        layout.addWidget(self._nav_list)
        layout.addWidget(self._page_stack, 1)

        self.setCentralWidget(central)

    def _setup_menu(self):
        """构建菜单栏"""
        menubar = self.menuBar()

        # 文件菜单
        file_menu = menubar.addMenu("文件")

        exit_action = QAction("退出", self)
        exit_action.setShortcut(QKeySequence.Quit)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # 视图菜单
        view_menu = menubar.addMenu("视图")

        self._toggle_log_action = QAction("显示/隐藏日志面板", self)
        self._toggle_log_action.setShortcut(QKeySequence("Ctrl+L"))
        self._toggle_log_action.setCheckable(True)
        self._toggle_log_action.triggered.connect(self._toggle_log_panel)
        view_menu.addAction(self._toggle_log_action)

        # 帮助菜单
        help_menu = menubar.addMenu("帮助")
        about_action = QAction("关于", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

    def _setup_statusbar(self):
        """构建状态栏"""
        status = QStatusBar()
        self.setStatusBar(status)

        self._status_label = QLabel("就绪")
        status.addWidget(self._status_label)

        # 右侧版本信息
        version_label = QLabel("v0.1.0")
        version_label.setStyleSheet("color: #94a3b8;")
        status.addPermanentWidget(version_label)

    def _setup_log_panel(self):
        """构建底部日志面板（可折叠 DockWidget）"""
        self._log_dock = QDockWidget("日志", self)
        self._log_dock.setObjectName("logDock")
        self._log_dock.setAllowedAreas(Qt.BottomDockWidgetArea)

        self._log_text = QTextEdit()
        self._log_text.setObjectName("logPanel")
        self._log_text.setReadOnly(True)
        self._log_text.setMaximumHeight(180)
        self._log_dock.setWidget(self._log_text)

        self.addDockWidget(Qt.BottomDockWidgetArea, self._log_dock)

        # 连接日志管理器
        if self._log_manager:
            self._log_manager.connect_to_textedit(self._log_text)

    def _setup_connections(self):
        """连接信号槽"""
        # 导航切换
        self._nav_list.currentRowChanged.connect(self._page_stack.setCurrentIndex)

    # ========== 槽方法 ==========

    def _toggle_log_panel(self):
        """切换日志面板显示/隐藏"""
        self._log_dock.setVisible(not self._log_dock.isVisible())

    def _show_about(self):
        """显示关于对话框"""
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.about(
            self,
            "关于",
            "<h3>量化交易系统 · 桌面版</h3>"
            "<p>版本: 0.1.0</p>"
            "<p>基于 PySide6 + pyqtgraph 构建</p>"
            "<p>从 Streamlit Web 应用迁移而来</p>"
        )

    def set_status(self, message: str):
        """更新状态栏消息"""
        self._status_label.setText(message)

    # ========== 资源清理 ==========

    def closeEvent(self, event: QCloseEvent):
        """窗口关闭事件：等待后台线程结束并释放数据层连接"""
        logger.info("应用正在关闭...")

        # 1) 请求所有后台 worker 取消并等待退出。
        #    QThread 若在运行中被销毁，Qt 会直接 abort 进程，因此必须先等。
        try:
            from desktop.widgets.async_worker import shutdown_workers
            shutdown_workers(timeout_ms=3000)
        except Exception as e:
            logger.error(f"关闭后台任务出错: {e}")

        # 2) 释放共享管理器持有的数据库连接
        try:
            from desktop.models.managers import Managers
            Managers.instance().close_all()
        except Exception as e:
            logger.error(f"资源清理出错: {e}")

        event.accept()
        logger.info("应用已关闭")
