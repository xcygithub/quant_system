"""
desktop/charts/equity_chart — 权益曲线（pyqtgraph 原生）

支持：
- 单条权益曲线（蓝色 + 半透明填充）
- 可选基准对比（橙色虚线）
- 日期 X 轴（整数索引 + 自定义刻度）
- 十字光标 + 数值提示
- y 轴金额格式化（千分位）
"""
import numpy as np
import pandas as pd
import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor

from desktop.charts.theme import (
    apply_plot_style, COLOR_EQUITY, COLOR_BENCHMARK, COLOR_FILL,
    COLOR_FOREGROUND, make_legend_font, qcolor_to_rgba,
)
from desktop.charts.candlestick import AxisTime


def _to_datetime_x(dates):
    """日期列转数值 X + 刻度标签

    pyqtgraph 的 X 轴用 float，最简单是用整数索引 + 自定义日期刻度。
    这样能避免 matplotlib 风格的 datetime64 转秒数精度问题。
    """
    if isinstance(dates, pd.DatetimeIndex):
        date_str = [d.strftime("%Y-%m-%d") for d in dates]
    else:
        date_str = [str(d)[:10] for d in dates]   # 'YYYY-MM-DD' 截前 10 位
    x = np.arange(len(date_str), dtype=float)
    return x, date_str


def build_equity_widget(
    equity_df: pd.DataFrame,
    *,
    value_col: str = "total_value",
    benchmark_col: str = None,
    title: str = "权益曲线",
    height: int = 320,
    show_legend: bool = True,
) -> pg.PlotWidget:
    """构建权益曲线 PlotWidget

    Args:
        equity_df: 至少包含 ['date', value_col]；可选 benchmark_col
        value_col: 权益列名，默认 'total_value'
        benchmark_col: 基准列名，None 表示不画基准
        title: 图表标题（绘制在 PlotItem 上方）
        height: 推荐高度（px）
        show_legend: 是否显示图例

    Returns:
        pg.PlotWidget，可传入 ChartContainer.set_plot_widget()
    """
    if equity_df is None or len(equity_df) == 0:
        w = pg.PlotWidget()
        apply_plot_style(w.getPlotItem())
        w.getPlotItem().setTitle(title)
        return w

    df = equity_df.reset_index(drop=True) if hasattr(equity_df, "reset_index") else pd.DataFrame(equity_df)
    x, date_str = _to_datetime_x(df["date"])
    y = np.asarray(df[value_col].values, dtype=float)

    pw = pg.PlotWidget()
    pw.setMinimumHeight(height)
    item = pw.getPlotItem()
    apply_plot_style(item)
    item.setTitle(title)
    item.setLabel("left", "净值（元）")
    item.setLabel("bottom", "日期")

    # X 轴日期刻度
    axis = AxisTime(date_str, orientation="bottom")
    item.setAxisItems({"bottom": axis})

    # 主曲线 + 填充
    fill_rgba = qcolor_to_rgba(COLOR_FILL, alpha=40)
    pen = pg.mkPen(color=qcolor_to_rgba(COLOR_EQUITY), width=2)
    curve = item.plot(x, y, pen=pen, name="权益")
    # 填充：从曲线到 y=0
    fill_item = pg.FillBetweenItem(
        curve, item.plot(x, np.zeros_like(y), pen=None),
        brush=pg.mkBrush(*fill_rgba),
    )
    item.addItem(fill_item)

    # 基准对比
    if benchmark_col is None:
        benchmark_col = "benchmark" if "benchmark" in df.columns else None
    if benchmark_col and benchmark_col in df.columns:
        yb = np.asarray(df[benchmark_col].values, dtype=float)
        item.plot(
            x, yb,
            pen=pg.mkPen(color=qcolor_to_rgba(COLOR_BENCHMARK), width=1.2,
                         style=Qt.DashLine),
            name="基准",
        )

    if show_legend:
        item.addLegend(offset=(10, 10))
        # pg 0.13.7 的 LegendItem 没有 setTextFont，用 setLabelTextColor + 样式
        try:
            item.legend.setLabelTextColor(COLOR_FOREGROUND)
        except Exception:
            pass

    # 十字光标 + 数据提示
    _install_crosshair(item, x, y, date_str, value_col)

    return pw


def _install_crosshair(plot_item, x, y, date_str, value_col):
    """安装十字光标 + 数据提示标签"""
    vline = pg.InfiniteLine(angle=90, pen=pg.mkPen(color=(150, 150, 150, 180), width=1, style=Qt.DashLine))
    hline = pg.InfiniteLine(angle=0,  pen=pg.mkPen(color=(150, 150, 150, 180), width=1, style=Qt.DashLine))
    plot_item.addItem(vline, ignoreBounds=True)
    plot_item.addItem(hline, ignoreBounds=True)

    # 数据提示 TextItem
    tip = pg.TextItem(anchor=(0, 1), color=COLOR_FOREGROUND)
    tip.setZValue(100)
    tip.hide()
    plot_item.addItem(tip)

    y_arr = np.asarray(y, dtype=float)
    x_arr = np.asarray(x, dtype=float)

    def on_mouse_moved(evt_pos):
        if not plot_item.sceneBoundingRect().contains(evt_pos):
            tip.hide()
            return
        mouse_point = plot_item.vb.mapSceneToView(evt_pos)
        x_val = mouse_point.x()
        # 找最近的数据点
        if len(x_arr) == 0:
            return
        idx = int(np.clip(round(x_val), 0, len(x_arr) - 1))
        vline.setPos(x_arr[idx])
        hline.setPos(y_arr[idx])
        tip.setPos(x_arr[idx], y_arr[idx])
        date_label = date_str[idx] if 0 <= idx < len(date_str) else ""
        # y 值格式化千分位
        try:
            y_str = f"{y_arr[idx]:,.2f}"
        except Exception:
            y_str = str(y_arr[idx])
        tip.setText(f"{date_label}\n{y_str}")
        tip.show()

    plot_item.scene().sigMouseMoved.connect(on_mouse_moved)
