"""
单元测试：UI 重设计新增组件

- ToggleSwitch 开关组件
- CheckableTableModel / CheckableTableView 带 Checkbox 列的表格
- AddStockDialog 添加自选股弹窗
"""
import os
import sys
import pytest

os.environ['QT_QPA_PLATFORM'] = 'offscreen'

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

# 确保 QApplication 实例
app = QApplication.instance() or QApplication(sys.argv)

import pandas as pd
import numpy as np

from desktop.widgets.toggle_switch import ToggleSwitch, _TrackWidget
from desktop.pages.watchlist_page import (
    CheckableTableModel, CheckableTableView, AddStockDialog,
)


class TestToggleSwitch:
    """ToggleSwitch 开关组件测试"""

    def test_default_unchecked(self):
        toggle = ToggleSwitch("自动刷新")
        assert not toggle.checked()
        assert not toggle.isChecked()

    def test_set_checked(self):
        toggle = ToggleSwitch()
        toggle.setChecked(True)
        assert toggle.checked()
        assert toggle.isChecked()

    def test_toggle_signal(self):
        toggle = ToggleSwitch()
        received = []
        toggle.toggled.connect(lambda v: received.append(v))
        toggle.setChecked(True)
        assert received == [True]
        toggle.setChecked(False)
        assert received == [True, False]

    def test_no_duplicate_signal(self):
        toggle = ToggleSwitch()
        toggle.setChecked(True)
        received = []
        toggle.toggled.connect(lambda v: received.append(v))
        toggle.setChecked(True)  # 重复设置相同值
        assert received == []  # 不应触发信号

    def test_label_text(self):
        toggle = ToggleSwitch("自动刷新")
        assert toggle._label_text == "自动刷新"

    def test_track_widget(self):
        track = _TrackWidget()
        assert not track._checked
        track.set_checked(True)
        assert track._checked

    def test_size_hint(self):
        toggle = ToggleSwitch("自动刷新")
        hint = toggle.sizeHint()
        assert hint.width() > 0
        assert hint.height() > 0

    def test_click_track_toggles_once(self):
        """回归测试：点击轨道只触发一次 toggle（修复二次冒泡 bug）"""
        from PySide6.QtTest import QTest
        from PySide6.QtCore import QPoint
        toggle = ToggleSwitch("自动刷新")
        toggle.show()
        app.processEvents()

        received = []
        toggle.toggled.connect(lambda v: received.append(v))

        # 点击轨道中心
        QTest.mouseClick(toggle._track, Qt.LeftButton, pos=QPoint(18, 10))
        app.processEvents()

        # 只应触发一次 toggle，状态翻转为 True
        assert received == [True], f"应只触发一次 toggle，实际 {received}"
        assert toggle.checked() is True

    def test_click_track_toggle_off_and_on(self):
        """回归测试：连续点击轨道应正确来回切换"""
        from PySide6.QtTest import QTest
        from PySide6.QtCore import QPoint
        toggle = ToggleSwitch("自动刷新")
        toggle.show()
        app.processEvents()

        QTest.mouseClick(toggle._track, Qt.LeftButton, pos=QPoint(18, 10))
        app.processEvents()
        assert toggle.checked() is True

        QTest.mouseClick(toggle._track, Qt.LeftButton, pos=QPoint(18, 10))
        app.processEvents()
        assert toggle.checked() is False

    def test_click_label_toggles_once(self):
        """回归测试：点击文字标签也只触发一次 toggle"""
        from PySide6.QtTest import QTest
        from PySide6.QtCore import QPoint
        from PySide6.QtWidgets import QLabel
        toggle = ToggleSwitch("自动刷新")
        toggle.show()
        app.processEvents()

        received = []
        toggle.toggled.connect(lambda v: received.append(v))

        lbl = toggle.findChild(QLabel)
        QTest.mouseClick(lbl, Qt.LeftButton,
                         pos=QPoint(lbl.width() // 2, lbl.height() // 2))
        app.processEvents()

        assert received == [True], f"点击标签应只触发一次 toggle，实际 {received}"
        assert toggle.checked() is True


class TestCheckableTableModel:
    """CheckableTableModel 带 Checkbox 列的代理模型测试"""

    def _make_model(self):
        from desktop.widgets.pandas_table import PandasTableModel
        df = pd.DataFrame({
            "代码": ["000001.SH", "600000.SH", "000002.SZ"],
            "名称": ["平安银行", "浦发银行", "万科A"],
            "涨跌幅(%)": [1.5, -0.8, 0.0],
        })
        source = PandasTableModel(df)
        proxy = CheckableTableModel(source)
        return proxy

    def test_column_count_with_checkbox(self):
        proxy = self._make_model()
        # 源模型 3 列 + 1 列 Checkbox = 4
        assert proxy.columnCount() == 4

    def test_initial_no_checked(self):
        proxy = self._make_model()
        assert proxy.checked_count() == 0
        assert proxy.checked_rows() == set()

    def test_check_state_role(self):
        proxy = self._make_model()
        idx = proxy.index(0, 0)
        # 初始未选中
        assert proxy.data(idx, Qt.CheckStateRole) == Qt.Unchecked

    def test_toggle_check(self):
        proxy = self._make_model()
        proxy.toggle_check(0)  # 选中第 0 行
        assert proxy.checked_count() == 1
        idx = proxy.index(0, 0)
        assert proxy.data(idx, Qt.CheckStateRole) == Qt.Checked

    def test_toggle_check_off(self):
        proxy = self._make_model()
        proxy.toggle_check(0)
        proxy.toggle_check(0)  # 取消选中
        assert proxy.checked_count() == 0

    def test_set_all_checked(self):
        proxy = self._make_model()
        proxy.set_all_checked(True)
        assert proxy.checked_count() == 3

    def test_set_all_unchecked(self):
        proxy = self._make_model()
        proxy.set_all_checked(True)
        proxy.set_all_checked(False)
        assert proxy.checked_count() == 0

    def test_set_data_check_state(self):
        proxy = self._make_model()
        idx = proxy.index(1, 0)
        proxy.setData(idx, Qt.Checked, Qt.CheckStateRole)
        assert proxy.checked_count() == 1
        assert 1 in proxy.checked_rows()

    def test_header_data_checkbox_col(self):
        proxy = self._make_model()
        # Checkbox 列的表头为空
        assert proxy.headerData(0, Qt.Horizontal, Qt.DisplayRole) == ""
        # 其他列正常
        assert proxy.headerData(1, Qt.Horizontal, Qt.DisplayRole) == "代码"

    def test_flags_checkbox_col(self):
        proxy = self._make_model()
        idx = proxy.index(0, 0)
        flags = proxy.flags(idx)
        assert bool(flags & Qt.ItemIsUserCheckable)
        assert bool(flags & Qt.ItemIsEnabled)

    def test_data_other_columns(self):
        proxy = self._make_model()
        # 第 1 列（Checkbox 之后）对应源模型第 0 列
        idx = proxy.index(0, 1)
        assert proxy.data(idx, Qt.DisplayRole) == "000001.SH"


class TestCheckableTableView:
    """CheckableTableView 带 Checkbox 列的表格视图测试"""

    def _make_table(self):
        table = CheckableTableView()
        df = pd.DataFrame({
            "代码": ["000001.SH", "600000.SH"],
            "名称": ["平安银行", "浦发银行"],
            "最新价": [10.5, 8.3],
            "涨跌幅(%)": [1.5, -0.8],
            "成交量(万)": [100.0, 200.0],
            "分组": ["默认", "银行"],
        })
        table.set_checkable_data(
            df,
            formatters={"最新价": "{:.2f}", "涨跌幅(%)": "{:+.2f}", "成交量(万)": "{:.1f}"},
            color_rules={"涨跌幅(%)": lambda v: "#E24B4A" if v and v > 0 else "#639922" if v and v < 0 else None},
        )
        return table

    def test_set_checkable_data(self):
        table = self._make_table()
        assert table._proxy_model is not None
        assert table._proxy_model.columnCount() == 7  # 6 + 1

    def test_initial_no_checked(self):
        table = self._make_table()
        assert table.get_checked_count() == 0
        assert table.get_checked_symbols() == []

    def test_select_all(self):
        table = self._make_table()
        table.select_all()
        assert table.get_checked_count() == 2
        assert table.get_checked_symbols() == ["000001.SH", "600000.SH"]

    def test_deselect_all(self):
        table = self._make_table()
        table.select_all()
        table.deselect_all()
        assert table.get_checked_count() == 0

    def test_selection_changed_signal(self):
        table = self._make_table()
        received = []
        table.selection_changed.connect(lambda c: received.append(c))
        table.select_all()
        assert len(received) > 0
        assert received[-1] == 2

    def test_checkbox_column_width(self):
        table = self._make_table()
        header = table.horizontalHeader()
        assert header.sectionSize(0) == 40  # Checkbox 列宽固定 40


class TestAddStockDialog:
    """添加自选股弹窗测试"""

    def test_construction(self):
        dialog = AddStockDialog()
        assert dialog.windowTitle() == "添加自选股"

    def test_get_stock_data(self):
        dialog = AddStockDialog()
        dialog._symbol_edit.setText("000001.SH")
        dialog._name_edit.setText("平安银行")
        dialog._group_combo.setCurrentText("默认")
        data = dialog.get_stock_data()
        assert data["symbol"] == "000001.SH"
        assert data["name"] == "平安银行"
        assert data["group"] == "默认"

    def test_custom_group(self):
        dialog = AddStockDialog()
        dialog._symbol_edit.setText("600000.SH")
        dialog._group_combo.setCurrentText("自定义")
        dialog._custom_edit.setText("金融")
        dialog._custom_edit.setVisible(True)
        data = dialog.get_stock_data()
        assert data["group"] == "金融"

    def test_custom_group_fallback(self):
        dialog = AddStockDialog()
        dialog._symbol_edit.setText("600000.SH")
        dialog._group_combo.setCurrentText("自定义")
        dialog._custom_edit.setVisible(True)
        # 自定义分组名为空，应回退到"默认"
        data = dialog.get_stock_data()
        assert data["group"] == "默认"

    def test_is_qdialog(self):
        from PySide6.QtWidgets import QDialog
        dialog = AddStockDialog()
        assert isinstance(dialog, QDialog)
