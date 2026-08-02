"""
StockSelector 股票选择器 — 替代 st.selectbox 股票选择（18处）

支持：
- format_func 等价（"代码 - 名称"显示映射）
- 搜索补全（输入代码/名称模糊匹配）
- 选项变更信号联动数据加载（信号槽天然替代 st.rerun）
- 股票池来源切换（自选股 vs 自定义列表，StockPoolSelector）

设计依据：web 屄 selectbox 股票选择3种模式：
- 模式A: 自选股列表 + format_func 显示"代码 - 名称"
- 模式B: 自选股列表切换 + 联动数据加载（session_state + st.rerun）
- 模式C: 股票池来源切换（自选股 vs 自定义列表）
"""
from typing import Dict, List, Optional
from PySide6.QtWidgets import (QWidget, QComboBox, QHBoxLayout, QLabel,
                                 QLineEdit, QRadioButton, QButtonGroup,
                                 QVBoxLayout, QCompleter, QFrame,
                                 QCheckBox, QScrollArea, QGridLayout)
from PySide6.QtCore import Signal, Qt, QStringListModel


class StockSelector(QWidget):
    """股票选择器

    封装 QComboBox + 显示映射 + 搜索补全 + 联动信号。
    信号槽天然替代 Streamlit 的 session_state + st.rerun 联动。

    Signals:
        stock_changed(str): 选中的股票代码变化

    Usage:
        selector = StockSelector(label="切换股票")
        selector.set_stocks(symbols, display_map={"000001.SZ": "000001.SZ - 平安银行"})
        selector.stock_changed.connect(self._load_stock_data)

        # 获取选中
        symbol = selector.get_selected_stock()
    """

    stock_changed = Signal(str)

    def __init__(self, parent=None, label: str = "选择股票"):
        super().__init__(parent)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        if label:
            label_widget = QLabel(label)
            layout.addWidget(label_widget)

        self._combo = QComboBox()
        self._combo.setMinimumWidth(240)
        layout.addWidget(self._combo, 1)

        # 搜索补全（模糊匹配代码或名称）
        self._completer = QCompleter()
        self._completer.setFilterMode(Qt.MatchContains)
        self._completer.setCaseSensitivity(Qt.CaseInsensitive)
        self._combo.setCompleter(self._completer)

        self._display_map = {}  # symbol -> display_text
        self._combo.currentIndexChanged.connect(self._on_index_changed)

    def set_stocks(self, stocks: List[str],
                   display_map: Optional[Dict[str, str]] = None):
        """设置股票列表

        Args:
            stocks: 股票代码列表 ['000001.SZ', '600000.SH', ...]
            display_map: 可选的显示映射 {symbol: "000001.SZ - 平安银行"}
                         若不传，显示原始代码
        """
        self._combo.blockSignals(True)
        self._combo.clear()
        self._display_map = display_map or {}

        for symbol in stocks:
            display = self._display_map.get(symbol, symbol)
            self._combo.addItem(display, symbol)  # userData 存原始代码

        # 更新补全模型
        display_texts = list(self._display_map.values()) or list(stocks)
        self._completer.setModel(QStringListModel(display_texts))

        self._combo.blockSignals(False)
        if stocks:
            self._on_index_changed(0)

    def get_selected_stock(self) -> str:
        """获取选中的股票代码（原始代码，非显示文本）"""
        return self._combo.currentData() or self._combo.currentText()

    def set_selected_stock(self, symbol: str):
        """设置选中股票（按代码）"""
        for i in range(self._combo.count()):
            if self._combo.itemData(i) == symbol:
                self._combo.setCurrentIndex(i)
                break

    def clear(self):
        """清空选项"""
        self._combo.blockSignals(True)
        self._combo.clear()
        self._display_map = {}
        self._combo.blockSignals(False)

    def _on_index_changed(self, index: int):
        if index >= 0:
            symbol = self._combo.itemData(index)
            if symbol:
                self.stock_changed.emit(symbol)


class StockPoolSelector(QWidget):
    """股票池来源选择器（自选股 vs 自定义列表）

    替代 web 屄模式C: selectbox "股票池来源" + text_area。
    选中"自选股"时使用传入的自选股列表；
    选中"自定义列表"时显示输入框，用户输入逗号分隔的代码。

    Signals:
        stocks_changed(list): 最终的股票代码列表变化

    Usage:
        pool = StockPoolSelector()
        pool.set_watchlist(["000001.SZ", "600000.SH"])
        pool.stocks_changed.connect(self._on_stocks_changed)
    """

    stocks_changed = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # 来源切换
        source_layout = QHBoxLayout()
        source_layout.setSpacing(12)
        self._radio_watchlist = QRadioButton("📈 自选股")
        self._radio_custom = QRadioButton("📋 自定义列表")
        self._radio_watchlist.setChecked(True)
        self._btn_group = QButtonGroup(self)
        self._btn_group.addButton(self._radio_watchlist)
        self._btn_group.addButton(self._radio_custom)
        source_layout.addWidget(self._radio_watchlist)
        source_layout.addWidget(self._radio_custom)
        source_layout.addStretch()
        layout.addLayout(source_layout)

        # 自定义输入框
        self._custom_input = QLineEdit()
        self._custom_input.setPlaceholderText("股票代码（逗号分隔），如 000001.SZ, 600000.SH")
        self._custom_input.hide()
        layout.addWidget(self._custom_input)

        # 状态标签
        self._status_label = QLabel()
        self._status_label.setStyleSheet("color: #6b7280; font-size: 12px;")
        layout.addWidget(self._status_label)

        self._watchlist = []

        # 信号连接
        self._radio_watchlist.toggled.connect(self._on_source_changed)
        self._custom_input.textChanged.connect(self._on_custom_changed)

    def set_watchlist(self, symbols: List[str]):
        """设置自选股列表"""
        self._watchlist = list(symbols)
        if self._radio_watchlist.isChecked():
            self._emit_stocks()

    def get_stocks(self) -> List[str]:
        """获取当前股票池"""
        if self._radio_watchlist.isChecked():
            return list(self._watchlist)
        else:
            text = self._custom_input.text().strip()
            return [s.strip() for s in text.split(",") if s.strip()]

    def _on_source_changed(self):
        if self._radio_watchlist.isChecked():
            self._custom_input.hide()
        else:
            self._custom_input.show()
        self._emit_stocks()

    def _on_custom_changed(self):
        self._emit_stocks()

    def _emit_stocks(self):
        stocks = self.get_stocks()
        if self._radio_watchlist.isChecked():
            self._status_label.setText(f"将使用 {len(stocks)} 只自选股")
        else:
            self._status_label.setText(f"自定义列表: {len(stocks)} 只")
        self.stocks_changed.emit(stocks)


class StockCheckboxGroup(QWidget):
    """股票多选复选框组（带全选 + 滚动）

    替代 web 屄 Tab2 与 Tab6 中几乎逐行相同的复选框股票选择器
    （app.py:1435-1459 与 app.py:1731-1754）。通过 selection_changed
    信号暴露当前勾选集合，天然替代 st.rerun 的自动重绘。

    Signals:
        selection_changed(list): 当前勾选的股票代码列表变化

    Usage:
        group = StockCheckboxGroup()
        group.set_stocks([("000001.SZ", "平安银行"), ("600000.SH", "浦发银行")])
        group.selection_changed.connect(self._on_selection_changed)
        selected = group.get_selected()  # ["000001.SZ", ...]
    """

    selection_changed = Signal(list)

    def __init__(self, parent=None, columns: int = 2, max_height: int = 220):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self._select_all = QCheckBox("全选")
        self._select_all.stateChanged.connect(self._on_select_all)
        layout.addWidget(self._select_all)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMaximumHeight(max_height)
        self._list_widget = QWidget()
        self._grid = QGridLayout(self._list_widget)
        self._grid.setContentsMargins(4, 4, 4, 4)
        self._grid.setSpacing(4)
        scroll.setWidget(self._list_widget)
        layout.addWidget(scroll, 1)

        self._checkboxes = {}   # symbol -> QCheckBox
        self._columns = columns
        self._building = False

    def set_stocks(self, stocks: List[tuple]):
        """设置股票列表

        Args:
            stocks: [(symbol, name), ...]
        """
        self._building = True
        for cb in self._checkboxes.values():
            cb.deleteLater()
        self._checkboxes = {}
        # 清空 grid 中残留的子 widget
        while self._grid.count():
            item = self._grid.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        for i, (symbol, name) in enumerate(stocks):
            cb = QCheckBox(f"{symbol} {name}")
            cb.setProperty("symbol", symbol)
            cb.stateChanged.connect(
                lambda _state, s=symbol: self._on_cb_changed(s)
            )
            row = i // self._columns
            col = i % self._columns
            self._grid.addWidget(cb, row, col)
            self._checkboxes[symbol] = cb
        self._building = False
        self._update_select_all_state()

    def get_selected(self) -> List[str]:
        """获取当前勾选的股票代码列表"""
        return [s for s, cb in self._checkboxes.items() if cb.isChecked()]

    def set_selected(self, symbols: List[str]):
        """设置勾选集合"""
        self._building = True
        symbol_set = set(symbols)
        for s, cb in self._checkboxes.items():
            cb.setChecked(s in symbol_set)
        self._building = False
        self._update_select_all_state()
        self.selection_changed.emit(self.get_selected())

    def _on_cb_changed(self, symbol: str):
        if self._building:
            return
        self._update_select_all_state()
        self.selection_changed.emit(self.get_selected())

    def _on_select_all(self, state: int):
        if self._building:
            return
        checked = (state == Qt.Checked)
        self._building = True
        for cb in self._checkboxes.values():
            cb.setChecked(checked)
        self._building = False
        self.selection_changed.emit(self.get_selected())

    def _update_select_all_state(self):
        n = len(self._checkboxes)
        sel = len(self.get_selected())
        self._building = True
        if n == 0 or sel == 0:
            self._select_all.setCheckState(Qt.Unchecked)
        elif sel == n:
            self._select_all.setCheckState(Qt.Checked)
        else:
            self._select_all.setCheckState(Qt.PartiallyChecked)
        self._building = False
