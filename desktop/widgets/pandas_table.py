"""
PandasTableModel + PandasTableView — 替代 st.dataframe（20处）

支持：
- 列格式化器（{:.2f}, {:+.2f}%）
- 单元格条件着色（涨红跌绿，中国股市惯例）
- 单行选择回调
- hide_index（默认隐藏行号）
- 列排序（点击表头）
- 10000行流畅滚动（QTableView 虚拟滚动）

设计依据：web 屄 st.dataframe 用法：
- 中文列名为主，原始数据表保留英文
- 典型行数 10-50，部分含 Styler 涨跌着色
- 部分用 on_select="rerun" single-row 实现行选择
"""
from typing import Dict, Callable, Optional
import pandas as pd
import numpy as np
from PySide6.QtCore import (QAbstractTableModel, Qt, QModelIndex, Signal)
from PySide6.QtGui import QColor, QBrush
from PySide6.QtWidgets import (QTableView, QAbstractItemView,
                                 QHeaderView)


# ===== 颜色常量（中国股市惯例：涨红跌绿）=====
COLOR_UP = "#dc2626"      # 红色 - 涨
COLOR_DOWN = "#16a34a"    # 绿色 - 跌
COLOR_FLAT = "#6b7280"    # 灰色 - 平


def make_change_color_rule(threshold: float = 0) -> Callable:
    """创建涨跌着色规则工厂

    涨用红色，跌用绿色（中国股市惯例）。

    Args:
        threshold: 涨跌分界阈值，默认0

    Returns:
        着色函数 (value) -> color_str | None

    Usage:
        color_rules = {
            '涨跌幅': make_change_color_rule(),
            '收益率': make_change_color_rule(),
        }
        table.set_dataframe(df, color_rules=color_rules)
    """
    def rule(value):
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return None
        if not isinstance(value, (int, float, np.number)):
            return None
        if value > threshold:
            return COLOR_UP
        elif value < threshold:
            return COLOR_DOWN
        return COLOR_FLAT
    return rule


class PandasTableModel(QAbstractTableModel):
    """Pandas DataFrame 表格模型

    支持列格式化和单元格条件着色。

    Args:
        df: DataFrame 数据
        formatters: 列格式化器 {列名: 格式串}，如 {'价格': '{:.2f}', '涨幅': '{:+.2f}%'}
        color_rules: 条件着色规则 {列名: (value)->color_str}
        show_index: 是否显示行索引（默认 False，等价 hide_index）
    """

    def __init__(self, df: pd.DataFrame = None,
                 formatters: Dict[str, str] = None,
                 color_rules: Dict[str, Callable] = None,
                 show_index: bool = False):
        super().__init__()
        self._df = df if df is not None else pd.DataFrame()
        self._formatters = formatters or {}
        self._color_rules = color_rules or {}
        self._show_index = show_index

    def update_data(self, df: pd.DataFrame,
                    formatters: Dict[str, str] = None,
                    color_rules: Dict[str, Callable] = None):
        """更新数据（触发模型重置信号）"""
        self.beginResetModel()
        self._df = df if df is not None else pd.DataFrame()
        if formatters is not None:
            self._formatters = formatters
        if color_rules is not None:
            self._color_rules = color_rules
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return len(self._df)

    def columnCount(self, parent=QModelIndex()):
        return len(self._df.columns)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        row, col = index.row(), index.column()
        col_name = self._df.columns[col]
        value = self._df.iloc[row, col]

        if role == Qt.DisplayRole:
            # 列格式化
            if col_name in self._formatters:
                fmt = self._formatters[col_name]
                try:
                    if pd.isna(value):
                        return "-"
                    return fmt.format(value)
                except (ValueError, TypeError):
                    return str(value)
            if pd.isna(value):
                return ""
            return str(value)

        elif role == Qt.ForegroundRole:
            # 单元格条件着色
            if col_name in self._color_rules:
                color = self._color_rules[col_name](value)
                if color:
                    return QBrush(QColor(color))

        elif role == Qt.TextAlignmentRole:
            # 数值右对齐，文本左对齐
            if isinstance(value, (int, float, np.number)) and not pd.isna(value):
                return int(Qt.AlignRight | Qt.AlignVCenter)
            return int(Qt.AlignLeft | Qt.AlignVCenter)

        elif role == Qt.ToolTipRole:
            return str(value) if not pd.isna(value) else ""

        return None

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role != Qt.DisplayRole:
            return None
        if orientation == Qt.Horizontal:
            return str(self._df.columns[section])
        else:
            if self._show_index:
                return str(self._df.index[section])
            return None

    def sort(self, column, order=Qt.AscendingOrder):
        """点击表头排序"""
        self.layoutAboutToBeChanged.emit()
        col_name = self._df.columns[column]
        ascending = (order == Qt.AscendingOrder)
        self._df = self._df.sort_values(
            col_name, ascending=ascending, na_position='last'
        ).reset_index(drop=True)
        self.layoutChanged.emit()

    def get_dataframe(self) -> pd.DataFrame:
        """获取内部 DataFrame"""
        return self._df

    def get_row_data(self, row: int) -> Optional[pd.Series]:
        """获取指定行数据"""
        if 0 <= row < len(self._df):
            return self._df.iloc[row]
        return None


class PandasTableView(QTableView):
    """Pandas 表格视图

    封装常用配置：交替行色、整行选中、单选、列排序。
    提供 set_dataframe() 便捷方法和行选择信号。

    Signals:
        row_selected(int): 选中行号变化
        row_double_clicked(int): 双击行号
    """
    row_selected = Signal(int)
    row_double_clicked = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        self.setAlternatingRowColors(True)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.horizontalHeader().setStretchLastSection(True)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.verticalHeader().setVisible(False)  # 默认 hide_index
        self.setSortingEnabled(True)
        # 性能优化：大数据量时关闭自动调整
        self.setWordWrap(False)

    def setModel(self, model):
        super().setModel(model)
        sm = self.selectionModel()
        if sm:
            sm.selectionChanged.connect(self._on_selection_changed)
        self.doubleClicked.connect(self._on_double_click)

    def set_dataframe(self, df: pd.DataFrame,
                      formatters: Dict[str, str] = None,
                      color_rules: Dict[str, Callable] = None,
                      show_index: bool = False,
                      auto_resize: bool = True,
                      max_col_width: int = 300):
        """便捷设置数据

        Args:
            df: DataFrame
            formatters: 列格式化器 {列名: 格式串}
            color_rules: 条件着色规则 {列名: (value)->color}
            show_index: 是否显示行索引
            auto_resize: 是否自动调整列宽
            max_col_width: 自动调整时的最大列宽
        """
        model = self.model()
        if not isinstance(model, PandasTableModel):
            model = PandasTableModel(df, formatters, color_rules, show_index)
            self.setModel(model)
        else:
            model.update_data(df, formatters, color_rules)
            model._show_index = show_index

        self.verticalHeader().setVisible(show_index)

        if auto_resize:
            self.resizeColumnsToContents()
            header = self.horizontalHeader()
            for i in range(header.count()):
                if header.sectionSize(i) > max_col_width:
                    header.resizeSection(i, max_col_width)

    def _on_selection_changed(self, selected, deselected):
        indexes = self.selectionModel().selectedRows()
        if indexes:
            self.row_selected.emit(indexes[0].row())

    def _on_double_click(self, index):
        if index.isValid():
            self.row_double_clicked.emit(index.row())

    def get_selected_row(self) -> int:
        """获取当前选中行号，无选中返回 -1"""
        indexes = self.selectionModel().selectedRows()
        return indexes[0].row() if indexes else -1

    def get_selected_data(self) -> Optional[pd.Series]:
        """获取选中行数据 (pd.Series)，无选中返回 None"""
        row = self.get_selected_row()
        if row >= 0 and isinstance(self.model(), PandasTableModel):
            return self.model().get_row_data(row)
        return None

    def clear_selection(self):
        """清除选中"""
        self.clearSelection()
