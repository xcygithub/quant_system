"""
StrategyParamsWidget 策略参数组件 — 替代 Tab2/Tab6 重复的策略滑块组

Tab2(app.py:1480-1499) 与 Tab6(app.py:1705-1724) 的策略参数滑块组几乎逐行相同。
本组件统一封装，参数范围完全一致。参数键名对齐 SignalScanner.DEFAULT_PARAMS /
backtest_service.STRATEGY_CLASS_MAP，确保后端可直接消费。

Signals:
    strategy_changed(str): 当前策略变化
    params_changed(dict): 当前策略参数 dict 变化

Usage:
    w = StrategyParamsWidget(include_multi_factor=True)
    w.strategy_changed.connect(self._on_strategy_changed)
    strategy = w.get_strategy()
    params = w.get_params()   # {"fast_period": 20, "slow_period": 60, ...}
"""
from typing import List, Optional, Tuple, Callable
from PySide6.QtWidgets import (QWidget, QComboBox, QFormLayout,
                                 QSpinBox, QDoubleSpinBox, QVBoxLayout, QLabel)
from PySide6.QtCore import Signal

# (参数键, 标签, 最小值, 最大值, 默认值, 步进, 类型)
_STRATEGY_PARAM_SPECS = {
    "均线交叉 (MA Cross)": [
        ("fast_period", "短期均线", 5, 60, 20, 1, int),
        ("slow_period", "长期均线", 10, 120, 60, 1, int),
    ],
    "MACD": [
        ("fast", "快线周期", 5, 20, 12, 1, int),
        ("slow", "慢线周期", 15, 40, 26, 1, int),
        ("signal", "信号线周期", 5, 15, 9, 1, int),
    ],
    "布林带 (Bollinger Bands)": [
        ("period", "周期", 10, 50, 20, 1, int),
        ("std_dev", "标准差", 1.0, 3.0, 2.0, 0.1, float),
    ],
    "RSI": [
        ("period", "RSI周期", 5, 30, 14, 1, int),
        ("oversold", "超卖阈值", 10, 40, 30, 1, int),
        ("overbought", "超买阈值", 60, 90, 70, 1, int),
    ],
}

_STANDARD_STRATEGIES = [
    "均线交叉 (MA Cross)",
    "MACD",
    "布林带 (Bollinger Bands)",
    "RSI",
]


class StrategyParamsWidget(QWidget):
    """策略参数组件（策略选择 + 动态参数）"""

    strategy_changed = Signal(str)
    params_changed = Signal(dict)

    def __init__(self, parent=None, strategies: Optional[List[str]] = None,
                 include_multi_factor: bool = False):
        super().__init__(parent)

        if strategies is None:
            strategies = list(_STANDARD_STRATEGIES)
        if include_multi_factor and "多因子 (Multi-Factor)" not in strategies:
            strategies.append("多因子 (Multi-Factor)")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self._combo = QComboBox()
        self._combo.addItems(strategies)
        self._combo.currentTextChanged.connect(self._on_strategy_changed)
        layout.addWidget(self._combo)

        self._container = QWidget()
        self._form = QFormLayout(self._container)
        self._form.setContentsMargins(0, 0, 0, 0)
        self._form.setSpacing(6)
        layout.addWidget(self._container)

        self._controls = {}  # key -> (spinbox, getter)
        self._build_params(self._combo.currentText())

    def _build_params(self, strategy: str):
        # 清空旧控件
        while self._form.count():
            item = self._form.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self._controls = {}

        for (key, label, minv, maxv, default, step, typ) in \
                _STRATEGY_PARAM_SPECS.get(strategy, []):
            if typ is float:
                sb = QDoubleSpinBox()
                sb.setRange(minv, maxv)
                sb.setSingleStep(step)
                sb.setValue(default)
                sb.setDecimals(1)
            else:
                sb = QSpinBox()
                sb.setRange(minv, maxv)
                sb.setSingleStep(step)
                sb.setValue(default)
            self._form.addRow(label, sb)
            self._controls[key] = (sb, sb.value)

    def _on_strategy_changed(self, name: str):
        self._build_params(name)
        self.strategy_changed.emit(name)
        self.params_changed.emit(self.get_params())

    def get_strategy(self) -> str:
        return self._combo.currentText()

    def get_params(self) -> dict:
        return {k: getter() for k, (_, getter) in self._controls.items()}
