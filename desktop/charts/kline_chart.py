"""
desktop/charts/kline_chart — K线图 + 成交量 + 均线（中国配色）

样式约定（v2 设计稿）：
- 阳线红框空心、阴线绿色实心，影线恒 1px
- 白底、仅横向淡网格、标题由页面层提供（图内不重复）
- 均线 MA5 琥珀 / MA10 蓝 / MA20 紫 / MA60 灰
- 十字光标 + 左上角信息卡片 + 右轴价位标签
"""
import numpy as np
import pandas as pd
import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor

from desktop.charts.theme import (
    apply_plot_style, COLOR_UP, COLOR_DOWN, COLOR_FOREGROUND,
    COLOR_BACKGROUND, COLOR_CARD_BORDER, COLOR_TAG_BG,
    qcolor_to_rgba, make_legend_font,
)
from desktop.charts.candlestick import CandlestickItem, AxisTime

# MA 周期对应配色（克制的中性色板）
_MA_COLORS = {
    "MA3":  QColor("#BA7517"),
    "MA5":  QColor("#BA7517"),   # 琥珀
    "MA6":  QColor("#378ADD"),
    "MA10": QColor("#378ADD"),   # 蓝
    "MA12": QColor("#7F77DD"),
    "MA20": QColor("#7F77DD"),   # 紫
    "MA60": QColor("#5F5E5A"),   # 灰
}

# 不同周期对应的 MA 周期
_PERIOD_MA = {
    "D": [5, 10, 20, 60],
    "W": [5, 10, 20],
    "M": [3, 6, 12],
    "Y": [3, 5],
}
_PERIOD_NAMES = {"D": "日K", "W": "周K", "M": "月K", "Y": "年K"}

# 量柱透明度：阳(空心)浅、阴(实心)深
_VOL_ALPHA_UP = 90
_VOL_ALPHA_DOWN = 190


class NoWheelViewBox(pg.ViewBox):
    """禁用滚轮缩放的 ViewBox

    滚轮事件直接忽略（不缩放），并冒泡给外层滚动区域，
    页面仍可用滚轮上下滚动；缩放改由 UI 按钮触发（zoom_kline_x）。
    """

    def wheelEvent(self, ev, axis=None):
        ev.ignore()


def zoom_kline_x(glw, factor: float):
    """以可视中心为锚点缩放 K 线 X 轴

    Args:
        glw: build_kline_widget 返回的 GraphicsLayoutWidget
        factor: <1 放大（看到更少 K 线），>1 缩小（看到更多 K 线）
    """
    vb = getattr(glw, "kline_vb", None)
    n = getattr(glw, "kline_n", 0)
    if vb is None or n <= 0:
        return
    (xmin, xmax), _ = vb.viewRange()
    center = (xmin + xmax) / 2.0
    span = (xmax - xmin) * factor
    # 至少显示 10 根 K 线，最多显示全部
    span = max(min(10.0, float(n)), min(span, float(n)))
    half = span / 2.0
    lo, hi = center - half, center + half
    # 钳制在数据范围内（左右各留半根 K 线边距）
    if lo < -0.5:
        hi += -0.5 - lo
        lo = -0.5
    if hi > n - 0.5:
        lo -= hi - (n - 0.5)
        hi = n - 0.5
    vb.setXRange(lo, hi, padding=0)


def build_kline_widget(
    df: pd.DataFrame,
    symbol: str,
    period: str = "D",
    *,
    height: int = 820,
) -> pg.GraphicsLayoutWidget:
    """构建 K 线图 widget

    Args:
        df: OHLCV + date 列的 DataFrame
        symbol: 股票代码（标题用）
        period: 'D'/'W'/'M'/'Y'
        height: 推荐高度

    Returns:
        pg.GraphicsLayoutWidget
    """
    glw = pg.GraphicsLayoutWidget()
    glw.setMinimumHeight(height)
    glw.setBackground(COLOR_BACKGROUND)   # 整体铺白，消除默认黑底

    if df is None or df.empty:
        return glw

    df = df.reset_index(drop=True).copy()
    n = len(df)

    # 日期 X 轴
    if isinstance(df["date"].dtype, pd.DatetimeTZDtype) or pd.api.types.is_datetime64_any_dtype(df["date"]):
        date_str = [pd.Timestamp(d).strftime("%Y-%m-%d") for d in df["date"]]
    else:
        date_str = [str(d)[:10] for d in df["date"]]
    x = np.arange(n, dtype=float)

    # 主子图（K 线 + 均线）—— 占 70%
    # NoWheelViewBox：禁用滚轮缩放（缩放改由页面按钮触发）
    price_item = glw.addPlot(row=0, col=0, viewBox=NoWheelViewBox())
    apply_plot_style(price_item)
    price_item.showGrid(x=False, y=True, alpha=0.12)   # 只留横向淡网格

    axis = AxisTime(date_str, orientation="bottom")
    price_item.showAxis("bottom", show=False)  # 主图 X 轴刻度隐藏，让成交量子图显示

    # K 线
    ohlc = np.column_stack([
        x,
        df["open"].values.astype(float),
        df["high"].values.astype(float),
        df["low"].values.astype(float),
        df["close"].values.astype(float),
    ])
    candle = CandlestickItem(ohlc)
    price_item.addItem(candle)

    # 均线
    ma_periods = _PERIOD_MA.get(period, [3, 5])
    for mp in ma_periods:
        if n >= mp:
            label = f"MA{mp}"
            ma = df["close"].rolling(mp).mean().values.astype(float)
            color = _MA_COLORS.get(label, QColor("#64748b"))
            price_item.plot(
                x, ma,
                pen=pg.mkPen(color=qcolor_to_rgba(color), width=1.3),
                name=label,
            )

    # 图例（白底浅边框，不遮挡 K 线）
    legend = price_item.addLegend(
        offset=(10, 10),
        brush=pg.mkBrush(255, 255, 255, 180),
        pen=pg.mkPen(qcolor_to_rgba(COLOR_CARD_BORDER)),
        labelTextSize="9pt",
    )
    try:
        legend.setLabelTextColor(COLOR_FOREGROUND)
    except Exception:
        pass

    # 成交量子图 —— 占 30%
    vol_item = glw.addPlot(row=1, col=0, viewBox=NoWheelViewBox())
    apply_plot_style(vol_item)
    vol_item.showGrid(x=False, y=True, alpha=0.12)
    vol_item.setLabel("left", "成交量")
    vol_item.setAxisItems({"bottom": axis})
    vol_item.setXLink(price_item)   # 共享 X 轴
    vol_item.setMaximumHeight(220)

    if "volume" in df.columns:
        vol = df["volume"].values.astype(float)
        # 按当日涨跌着色：阳线量柱半透明、阴线量柱实色，与空心/实心 K 线呼应
        opens = df["open"].values.astype(float)
        closes = df["close"].values.astype(float)
        brushes = []
        for o, c in zip(opens, closes):
            col = COLOR_UP if c >= o else COLOR_DOWN
            alpha = _VOL_ALPHA_UP if c >= o else _VOL_ALPHA_DOWN
            brushes.append(pg.mkBrush((col.red(), col.green(), col.blue(), alpha)))
        bar = pg.BarGraphItem(
            x=x, height=vol, width=0.65,
            brushes=brushes,
            pen=pg.mkPen(color=(0, 0, 0, 0)),
        )
        vol_item.addItem(bar)

        # 量能 MA5
        if n >= 5:
            vma = df["volume"].rolling(5).mean().values.astype(float)
            vol_item.plot(x, vma, pen=pg.mkPen(color=(95, 94, 90, 200), width=1.2))

    # 行高比例 7:3
    glw.ci.layout.setRowStretchFactor(0, 7)
    glw.ci.layout.setRowStretchFactor(1, 3)
    glw.ci.layout.setRowSpacing(0, 2)     # 子图间隙收紧
    glw.ci.layout.setContentsMargins(2, 2, 2, 2)

    # 十字光标（主图 + 信息卡片 + 右轴价位标签）
    _install_kline_crosshair(price_item, vol_item, x, df, date_str)

    # 暴露给页面层：缩放按钮通过 zoom_kline_x(glw, factor) 操作
    glw.kline_vb = price_item.vb
    glw.kline_n = n

    return glw


def _install_kline_crosshair(price_item, vol_item, x, df, date_str):
    """主图 + 成交量子图联动的十字光标、信息卡片与右轴价位标签"""
    line_pen = pg.mkPen(color=(150, 150, 150, 140), width=1, style=Qt.DashLine)
    vline = pg.InfiniteLine(angle=90, pen=line_pen)
    hline = pg.InfiniteLine(angle=0, pen=line_pen)
    price_item.addItem(vline, ignoreBounds=True)
    price_item.addItem(hline, ignoreBounds=True)

    vline_vol = pg.InfiniteLine(angle=90, pen=line_pen)
    vol_item.addItem(vline_vol, ignoreBounds=True)

    # 信息卡片：白底圆角边框，固定在主图左上角
    tip = pg.TextItem(
        anchor=(0, 1), color=COLOR_FOREGROUND,
        fill=pg.mkBrush(255, 255, 255, 235),
        border=pg.mkPen(qcolor_to_rgba(COLOR_CARD_BORDER)),
    )
    tip.setFont(make_legend_font(9))
    tip.setZValue(100)
    tip.hide()
    price_item.addItem(tip, ignoreBounds=True)

    # 右轴价位标签：深底白字，跟随十字线横线
    tag = pg.TextItem(
        anchor=(1, 0.5), color=QColor("#ffffff"),
        fill=pg.mkBrush(qcolor_to_rgba(COLOR_TAG_BG)),
    )
    tag.setFont(make_legend_font(9))
    tag.setZValue(100)
    tag.hide()
    price_item.addItem(tag, ignoreBounds=True)

    x_arr = np.asarray(x, dtype=float)
    n = len(x_arr)
    opens = df["open"].values.astype(float) if "open" in df.columns else None
    highs = df["high"].values.astype(float) if "high" in df.columns else None
    lows = df["low"].values.astype(float) if "low" in df.columns else None
    closes = df["close"].values.astype(float) if "close" in df.columns else None
    vols = df["volume"].values.astype(float) if "volume" in df.columns else None

    def _reposition(price_y=None):
        """把卡片钉在可视区左上角、价位标签钉在右缘"""
        (xmin, xmax), (ymin, ymax) = price_item.vb.viewRange()
        pad = (xmax - xmin) * 0.012
        tip.setPos(xmin + pad, ymax)
        if price_y is not None:
            tag.setPos(xmax - pad, price_y)

    def on_mouse_moved(evt_pos):
        if not price_item.sceneBoundingRect().contains(evt_pos):
            tip.hide()
            tag.hide()
            return
        mp = price_item.vb.mapSceneToView(evt_pos)
        xv = mp.x()
        if n == 0:
            return
        idx = int(np.clip(round(xv), 0, n - 1))
        vline.setPos(x_arr[idx])
        vline_vol.setPos(x_arr[idx])
        if closes is None:
            return
        price = closes[idx]
        hline.setPos(price)
        date_label = date_str[idx] if 0 <= idx < len(date_str) else ""

        # 开/收按当日涨跌着色
        up = opens is None or closes[idx] >= opens[idx]
        col = "#E24B4A" if up else "#639922"
        lines = [f"<b>{date_label}</b>"]
        if opens is not None:
            lines.append(f'开 <span style="color:{col}">{opens[idx]:.2f}</span>')
        if highs is not None:
            lines.append(f"高 {highs[idx]:.2f}")
        if lows is not None:
            lines.append(f"低 {lows[idx]:.2f}")
        lines.append(f'收 <span style="color:{col}">{closes[idx]:.2f}</span>')
        if vols is not None:
            lines.append(f"量 {vols[idx]:,.0f}")
        tip.setHtml("<br>".join(lines))
        tip.show()

        tag.setText(f"{price:.2f}")
        tag.show()
        _reposition(price)

    price_item.scene().sigMouseMoved.connect(on_mouse_moved)
