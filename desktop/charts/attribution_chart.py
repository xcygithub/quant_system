"""
desktop/charts/attribution_chart — 因子归因 1x2 子图

左：因子收益贡献柱状图（正红负绿，符合中国股市约定）
右：因子收益率柱状图
"""
import numpy as np
import pyqtgraph as pg

from desktop.charts.theme import (
    apply_plot_style, COLOR_UP, COLOR_DOWN, COLOR_FOREGROUND,
)


def _color_for_value(v):
    return COLOR_UP if v >= 0 else COLOR_DOWN


def _add_bar_subplot(glw, row, col, title, labels, values):
    """在 GraphicsLayoutWidget 的指定位置加一个柱状图子图"""
    item = glw.addPlot(row=row, col=col, title=title)
    apply_plot_style(item)
    item.setLabel("left", "数值")
    item.showGrid(x=False, y=True, alpha=0.25)

    n = len(labels)
    if n == 0:
        return item

    x = np.arange(n, dtype=float)
    y = np.asarray(values, dtype=float)

    # 每根柱子按值正负着色
    brushes = []
    for v in y:
        c = _color_for_value(v)
        brushes.append(pg.mkBrush((c.red(), c.green(), c.blue(), 200)))

    # 用 BarGraphItem
    bar = pg.BarGraphItem(
        x=x, height=y, width=0.6, brushes=brushes,
        pen=pg.mkPen(color=(0, 0, 0, 0)),
    )
    item.addItem(bar)

    # 0 基线
    item.addItem(pg.InfiniteLine(
        pos=0, angle=0,
        pen=pg.mkPen(color=(107, 114, 128, 200), width=1),
    ))

    # X 轴：因子名
    ticks = [[(i, str(labels[i])) for i in range(n)]]
    item.getAxis("bottom").setTicks(ticks)

    return item


def build_attribution_widget(
    attribution: dict,
    *,
    height: int = 350,
) -> pg.GraphicsLayoutWidget:
    """构建因子归因 1x2 子图

    Args:
        attribution: {factor: {"contribution": float, "factor_return": float}}

    Returns:
        pg.GraphicsLayoutWidget
    """
    glw = pg.GraphicsLayoutWidget()
    glw.setMinimumHeight(height)

    if not attribution:
        return glw

    factors = list(attribution.keys())
    contributions = [float(attribution[f].get("contribution", 0) or 0) for f in factors]
    returns = [float(attribution[f].get("factor_return", 0) or 0) for f in factors]

    _add_bar_subplot(glw, 0, 0, "收益贡献", factors, contributions)
    _add_bar_subplot(glw, 0, 1, "因子收益率", factors, returns)

    return glw
