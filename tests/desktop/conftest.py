"""
桌面组件测试公共 fixtures

提供 QApplication 实例和 sys.path 配置。
"""
import sys
import os
import pytest

# 确保项目根目录在 sys.path
_PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..', '..')
)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


@pytest.fixture(scope='session')
def qapp():
    """提供 QApplication 实例（整个测试会话共享）"""
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(sys.argv)
    yield app
