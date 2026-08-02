"""
统一消息条组件 — 替代 st.error / st.warning / st.info / st.success

支持4级语义、emoji图标、多行文本、内联显示（非弹窗）。
web 屄有约 70 处消息调用，success 几乎必带 ✅，warning 偶带 ⚠️。

提供：
- MessageBar: 内联消息条（QFrame），可关闭
- MessageHelper: 静态工具类（状态栏消息 + 模态对话框）
"""
from PySide6.QtWidgets import (QFrame, QLabel, QHBoxLayout, QPushButton,
                                 QMessageBox, QStatusBar)
from PySide6.QtCore import Signal


class MessageBar(QFrame):
    """统一内联消息条

    4级语义：success / warning / error / info
    每级有专属背景色、边框色、文字色、emoji图标。
    支持关闭按钮。

    Usage:
        bar = MessageBar()
        bar.success("✅ 回测完成！")
        bar.error("数据获取失败: 网络超时")
        bar.warning("⚠️ 请至少选择一只股票")
        bar.info("👈 请在左侧配置参数后点击「开始回测」")
    """

    closed = Signal()

    LEVELS = {
        'success': {
            'bg': '#dcfce7', 'border': '#86efac',
            'text': '#15803d', 'icon': '✅',
        },
        'warning': {
            'bg': '#fef3c7', 'border': '#fcd34d',
            'text': '#92400e', 'icon': '⚠️',
        },
        'error': {
            'bg': '#fee2e2', 'border': '#fca5a5',
            'text': '#991b1b', 'icon': '❌',
        },
        'info': {
            'bg': '#dbeafe', 'border': '#93c5fd',
            'text': '#1e40af', 'icon': 'ℹ️',
        },
    }

    def __init__(self, parent=None, closable=True):
        super().__init__(parent)
        self.setObjectName("messageBar")
        self._closable = closable

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(8)

        self._icon_label = QLabel()
        self._icon_label.setFixedWidth(20)
        layout.addWidget(self._icon_label)

        self._text_label = QLabel()
        self._text_label.setWordWrap(True)
        self._text_label.setObjectName("messageText")
        layout.addWidget(self._text_label, 1)

        if closable:
            close_btn = QPushButton("×")
            close_btn.setFixedSize(24, 24)
            close_btn.setFlat(True)
            close_btn.setObjectName("messageCloseBtn")
            close_btn.setCursor(self._make_cursor())
            close_btn.clicked.connect(self._on_close)
            layout.addWidget(close_btn)

        self.hide()

    def _make_cursor(self):
        from PySide6.QtGui import QCursor, Qt
        return QCursor(Qt.PointingHandCursor)

    def show_message(self, level, text, auto_icon=True):
        """显示消息

        Args:
            level: 'success' / 'warning' / 'error' / 'info'
            text: 消息文本（可多行，支持 \\n）
            auto_icon: 是否自动添加级别图标（若 text 已含 emoji 则设 False）
        """
        config = self.LEVELS.get(level, self.LEVELS['info'])

        if auto_icon:
            self._icon_label.setText(config['icon'])
        else:
            self._icon_label.setText("")

        self._text_label.setText(text)

        self.setStyleSheet(f"""
            QFrame#messageBar {{
                background-color: {config['bg']};
                border: 1px solid {config['border']};
                border-radius: 6px;
            }}
            QLabel#messageText {{
                color: {config['text']};
                font-size: 13px;
            }}
            QPushButton#messageCloseBtn {{
                color: {config['text']};
                border: none;
                font-size: 16px;
                font-weight: bold;
            }}
            QPushButton#messageCloseBtn:hover {{
                background-color: rgba(0,0,0,0.1);
                border-radius: 12px;
            }}
        """)

        self.show()

    def success(self, text, auto_icon=True):
        """成功消息（绿色）"""
        self.show_message('success', text, auto_icon)

    def warning(self, text, auto_icon=True):
        """警告消息（黄色）"""
        self.show_message('warning', text, auto_icon)

    def error(self, text, auto_icon=True):
        """错误消息（红色）"""
        self.show_message('error', text, auto_icon)

    def info(self, text, auto_icon=True):
        """信息消息（蓝色）"""
        self.show_message('info', text, auto_icon)

    def clear(self):
        """清除消息并隐藏"""
        self.hide()
        self._text_label.setText("")

    def _on_close(self):
        self.clear()
        self.closed.emit()


class MessageHelper:
    """静态消息工具类 — 快捷调用

    提供两种消息方式：
    1. 状态栏临时消息（替代 st.success 等的轻量提示）
    2. 模态对话框（用于重要确认或错误）
    """

    @staticmethod
    def show_in_statusbar(statusbar: QStatusBar, level: str, text: str,
                          timeout: int = 5000):
        """在状态栏显示临时消息

        Args:
            statusbar: 主窗口的状态栏
            level: 'success' / 'warning' / 'error' / 'info'
            text: 消息文本
            timeout: 显示时长(ms)，0 表示持续
        """
        config = MessageBar.LEVELS.get(level, MessageBar.LEVELS['info'])
        statusbar.showMessage(f"{config['icon']} {text}", timeout)

    @staticmethod
    def show_dialog(parent, level: str, title: str, text: str) -> int:
        """显示模态消息对话框

        Returns:
            点击的按钮（QMessageBox.Ok 等）
        """
        msg_map = {
            'success': QMessageBox.Information,
            'info': QMessageBox.Information,
            'warning': QMessageBox.Warning,
            'error': QMessageBox.Critical,
        }
        icon_type = msg_map.get(level, QMessageBox.Information)
        box = QMessageBox(icon_type, title, text, QMessageBox.Ok, parent)
        return box.exec()

    @staticmethod
    def confirm(parent, title: str, text: str,
                yes_text="确认", no_text="取消") -> bool:
        """确认对话框（替代 session_state 里的 confirm 标记）

        Returns:
            True 表示用户点击了确认
        """
        box = QMessageBox(QMessageBox.Question, title, text,
                          QMessageBox.Yes | QMessageBox.No, parent)
        box.setButtonText(QMessageBox.Yes, yes_text)
        box.setButtonText(QMessageBox.No, no_text)
        return box.exec() == QMessageBox.Yes
