"""
desktop/charts/exposure_chart — 因子暴露度时序图

支持：
- 多因子时序暴露度（每列一个因子）
- 列数 ≤3 时堆叠面积；>3 时多线对比
- 日期 X 轴 + 中国配色
"""
import numpy as np
import pandas as pd
import pyqtgraph as pg
from PySide6.QtCore import Qt

from desktop.charts.theme import (
    apply_plot_style, factor_color, COLOR_FOREGROUND, qcolor_to_rgba,
)
from desktop.charts.candlestick import AxisTime


def build_exposure_widget(
    exposure_df: pd.DataFrame,
    *,
    title: str = "因子暴露度",
    height: int = 360,
) -> pg.PlotWidget:
    """构建因子暴露度时序图

    Args:
        exposure_df: index=日期，每列一个因子的暴露度数值
        title: 标题
        height: 推荐高度

    Returns:
        pg.PlotWidget
    """
    pw = pg.PlotWidget()
    pw.setMinimumHeight(height)
    item = pw.getPlotItem()
    apply_plot_style(item)
    item.setTitle(title)
    item.setLabel("left", "暴露度")
    item.setLabel("bottom", "日期")
    item.showGrid(x=True, y=True, alpha=0.25)

    if exposure_df is None or len(exposure_df) == 0 or exposure_df.empty:
        return pw

    df = exposure_df.copy()
    # X 轴：整数索引 + 日期刻度
    if isinstance(df.index, pd.DatetimeIndex):
        date_str = [d.strftime("%Y-%m-%d") for d in df.index]
    else:
        date_str = [str(d)[:10] for d in df.index]
    x = np.arange(len(date_str), dtype=float)
    axis = AxisTime(date_str, orientation="bottom")
    item.setAxisItems({"bottom": axis})

    cols = list(df.columns)
    n_cols = len(cols)
    use_stack = n_cols <= 3

    # 累积值（堆叠用）
    cum_upper = np.zeros(len(df), dtype=float)
    curves = []  # (col, curve_item, lower_curve_item)

    for i, col in enumerate(cols):
        y = pd.to_numeric(df[col], errors="coerce").fillna(0).values.astype(float)
        color = factor_color(i)
        pen = pg.mkPen(color=qcolor_to_rgba(color), width=2)
        if use_stack:
            lower = cum_upper.copy()
            upper = lower + y
            # 主线（上界）
            upper_curve = item.plot(x, upper, pen=pen, name=str(col))
            # 下界（透明线，用于 FillBetweenItem）
            lower_curve = item.plot(x, lower, pen=None)
            fill = pg.FillBetweenItem(
                upper_curve, lower_curve,
                brush=pg.mkBrush(*qcolor_to_rgba(color, alpha=80)),
            )
            item.addItem(fill)
            curves.append((col, upper_curve, lower_curve))
            cum_upper = upper
        else:
            item.plot(x, y, pen=pen, name=str(col))

    if n_cols > 0:
        item.addLegend(offset=(10, 10))
        try:
            item.legend.setLabelTextColor(COLOR_FOREGROUND)
        except Exception:
            pass

    return pw
