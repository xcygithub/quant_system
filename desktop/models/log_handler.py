"""
日志系统

将 Python logging 输出转发到 Qt 界面的 QTextEdit 面板，
同时保留文件日志用于排查问题。
"""
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, Signal, Slot
from PySide6.QtGui import QTextCursor, QTextCharFormat, QColor, QFont


class LogSignalBridge(QObject):
    """
    跨线程信号桥接器

    logging Handler 可能在任意线程被调用（如 QThread 中的日志），
    通过信号槽机制安全地转发到主线程更新 UI。
    """
    log_message = Signal(str, str)  # (level_name, formatted_message)

    @Slot(str, str)
    def emit_log(self, level: str, message: str):
        self.log_message.emit(level, message)


class QTextEditLogHandler(logging.Handler):
    """
    将日志输出到 QTextEdit 面板的 logging Handler

    通过信号桥接器实现线程安全，支持 QThread 中的日志记录。
    不同级别的日志用不同颜色显示。
    """

    # 日志级别对应颜色
    LEVEL_COLORS = {
        "DEBUG": "#94a3b8",    # 灰色
        "INFO": "#e2e8f0",     # 浅色
        "WARNING": "#fbbf24",  # 黄色
        "ERROR": "#f87171",    # 红色
        "CRITICAL": "#ef4444", # 亮红
    }

    def __init__(self, bridge: LogSignalBridge):
        super().__init__()
        self._bridge = bridge
        self.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%H:%M:%S"
        ))

    def emit(self, record: logging.LogRecord) -> None:
        """重写 emit，通过信号桥接器转发日志"""
        try:
            msg = self.format(record)
            self._bridge.emit_log(record.levelname, msg)
        except Exception:
            self.handleError(record)


class LogManager:
    """
    日志管理器

    负责初始化日志系统：
    1. 配置文件日志（写入 logs/ 目录）
    2. 配置控制台日志（开发模式）
    3. 配置 UI 日志面板（通过信号桥接器）

    使用方式：
        manager = LogManager()
        manager.setup_ui_handler(text_edit)  # 连接到 UI 面板
        logging.info("日志信息")  # 自动显示在面板中
    """

    def __init__(self, log_dir: Optional[Path] = None):
        self._bridge = LogSignalBridge()
        self._ui_handler: Optional[QTextEditLogHandler] = None
        self._text_edit = None

        # 日志目录
        if log_dir is None:
            log_dir = Path(__file__).parent.parent.parent / "logs"
        self._log_dir = log_dir
        self._log_dir.mkdir(parents=True, exist_ok=True)

        # 初始化根 logger
        self._root_logger = logging.getLogger()
        self._root_logger.setLevel(logging.DEBUG)

    @property
    def bridge(self) -> LogSignalBridge:
        """获取信号桥接器（用于连接 UI）"""
        return self._bridge

    def setup(self, console: bool = True, file_log: bool = True) -> None:
        """
        初始化日志系统

        Args:
            console: 是否输出到控制台
            file_log: 是否输出到文件
        """
        # 文件日志
        if file_log:
            log_file = self._log_dir / f"quant_{datetime.now().strftime('%Y%m%d')}.log"
            file_handler = logging.FileHandler(str(log_file), encoding="utf-8")
            file_handler.setLevel(logging.DEBUG)
            file_handler.setFormatter(logging.Formatter(
                "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S"
            ))
            self._root_logger.addHandler(file_handler)

        # 控制台日志
        if console:
            console_handler = logging.StreamHandler()
            console_handler.setLevel(logging.INFO)
            console_handler.setFormatter(logging.Formatter(
                "%(asctime)s [%(levelname)s] %(message)s",
                datefmt="%H:%M:%S"
            ))
            self._root_logger.addHandler(console_handler)

        # UI 日志 handler（始终创建，但需要连接到 text_edit 才会显示）
        self._ui_handler = QTextEditLogHandler(self._bridge)
        self._ui_handler.setLevel(logging.INFO)
        self._root_logger.addHandler(self._ui_handler)

        logging.info("日志系统初始化完成")

    def connect_to_textedit(self, text_edit) -> None:
        """
        将日志桥接器连接到 QTextEdit 面板

        Args:
            text_edit: QTextEdit 或 QPlainTextEdit 组件
        """
        self._text_edit = text_edit
        self._bridge.log_message.connect(self._append_log)

    @Slot(str, str)
    def _append_log(self, level: str, message: str) -> None:
        """将日志消息追加到 QTextEdit 面板"""
        if self._text_edit is None:
            return

        color = QTextEditLogHandler.LEVEL_COLORS.get(level, "#e2e8f0")

        cursor = self._text_edit.textCursor()
        cursor.movePosition(QTextCursor.End)

        fmt = QTextCharFormat()
        fmt.setForeground(QColor(color))
        cursor.setCharFormat(fmt)
        cursor.insertText(message + "\n")

        # 自动滚动到底部
        self._text_edit.setTextCursor(cursor)
        self._text_edit.ensureCursorVisible()
