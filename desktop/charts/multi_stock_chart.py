"""
desktop/charts/multi_stock_chart — 多股票信号子图

每只股票一个子图：收盘价折线 + 买入（红色▲）/卖出（绿色▼）标记。
共享 X 轴日期，便于横向对齐信号。
"""
import numpy as np
import pandas as pd
import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainterPath, QPolygonF
from PySide6.QtCore import QPointF

from desktop.charts.theme import (
    apply_plot_style, COLOR_BUY, COLOR_SELL, COLOR_EQUITY, COLOR_FOREGROUND,
    qcolor_to_rgba,
)
from desktop.charts.candlestick import AxisTime


def _to_datetime_x(dates):
    if isinstance(dates, pd.DatetimeIndex):
        date_str = [d.strftime("%Y-%m-%d") for d in dates]
    else:
        date_str = [str(d)[:10] for d in dates]
    x = np.arange(len(date_str), dtype=float)
    return x, date_str


def build_multi_stock_widget(
    stock_data: dict,
    signals: dict,
    symbols: list,
    *,
    title: str = "各股票信号（▲买入 ▼卖出）",
) -> pg.GraphicsLayoutWidget:
    """构建多股票信号子图

    Args:
        stock_data: {symbol: df(含 date/close 列)}
        signals: {symbol: pd.Series(index=日期, value=信号)}
        symbols: 子图顺序

    Returns:
        pg.GraphicsLayoutWidget
    """
    glw = pg.GraphicsLayoutWidget()
    n = len(symbols)
    if n == 0:
        return glw
    glw.setMinimumHeight(max(300, 180 * n))

    # 先收集所有日期，统一 X 轴
    all_dates = []
    for s in symbols:
        df = stock_data.get(s)
        if df is not None and not df.empty:
            for d in df["date"].tolist():
                all_dates.append(str(d)[:10])
    all_dates = sorted(set(all_dates))
    date_str = all_dates
    x_global = np.arange(len(date_str), dtype=float)
    date_to_idx = {d: i for i, d in enumerate(date_str)}

    plots = []
    for i, s in enumerate(symbols):
        df = stock_data.get(s)
        item = glw.addPlot(row=i, col=0, title=s)
        apply_plot_style(item)
        item.setLabel("left", "价格")
        if i == n - 1:
            axis = AxisTime(date_str, orientation="bottom")
            item.setAxisItems({"bottom": axis})
            item.setLabel("bottom", "日期")
        else:
            item.showAxis("bottom", show=False)
        plots.append(item)

        if df is None or df.empty:
            continue

        x, local_dates = _to_datetime_x(df["date"])
        close = np.asarray(df["close"].values, dtype=float)
        # 主折线
        item.plot(x, close,
                  pen=pg.mkPen(color=qcolor_to_rgba(COLOR_EQUITY), width=1.2))

        # 信号标记
        sig = signals.get(s)
        if sig is None:
            continue
        closes = df["close"].reset_index(drop=True)
        sig_vals = sig.reset_index(drop=True)
        if len(closes) != len(sig_vals):
            continue

        buy_idx = sig_vals[sig_vals == 1].index.tolist()
        sell_idx = sig_vals[sig_vals == -1].index.tolist()

        if buy_idx:
            bx = [x[j] for j in buy_idx]
            by = [close[j] for j in buy_idx]
            # 用 ScatterPlotItem 三角向上
            item.addItem(pg.ScatterPlotItem(
                x=bx, y=by,
                symbol="t",  # triangle up
                size=10,
                brush=pg.mkBrush(qcolor_to_rgba(COLOR_BUY)),
                pen=pg.mkPen(qcolor_to_rgba(COLOR_BUY)),
                name="买入",
            ))
        if sell_idx:
            sx = [x[j] for j in sell_idx]
            sy = [close[j] for j in sell_idx]
            item.addItem(pg.ScatterPlotItem(
                x=sx, y=sy,
                symbol="t1",  # triangle down
                size=10,
                brush=pg.mkBrush(qcolor_to_rgba(COLOR_SELL)),
                pen=pg.mkPen(qcolor_to_rgba(COLOR_SELL)),
                name="卖出",
            ))

    # 共享 X 轴：让所有子图的 X 范围联动
    if len(plots) > 1:
        primary = plots[0]
        for p in plots[1:]:
            p.setXLink(primary)

    # 顶部标题
    glw.ci.layout.setRowStretchFactor(n, 1)
    return glw
