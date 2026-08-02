"""
desktop/charts/kline_chart — K线图 + 成交量 + 均线（中国配色）

支持：
- CandlestickItem K 线（红涨绿跌）
- 成交量子图（按涨跌着色）
- MA3/5/10/20/60 均线
- 日期 X 轴 + 共享缩放
- 鼠标十字光标
"""
import numpy as np
import pandas as pd
import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor

from desktop.charts.theme import (
    apply_plot_style, COLOR_UP, COLOR_DOWN, COLOR_FOREGROUND,
    qcolor_to_rgba,
)
from desktop.charts.candlestick import CandlestickItem, AxisTime

# MA 周期对应配色
_MA_COLORS = {
    "MA3":  QColor("#6366f1"),
    "MA5":  QColor("#2563eb"),
    "MA6":  QColor("#0ea5e9"),
    "MA10": QColor("#ef4444"),
    "MA12": QColor("#f59e0b"),
    "MA20": QColor("#10b981"),
    "MA60": QColor("#14b8a6"),
}

# 不同周期对应的 MA 周期
_PERIOD_MA = {
    "D": [5, 10, 20, 60],
    "W": [5, 10, 20],
    "M": [3, 6, 12],
    "Y": [3, 5],
}
_PERIOD_NAMES = {"D": "日K", "W": "周K", "M": "月K", "Y": "年K"}


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
    price_item = glw.addPlot(row=0, col=0)
    apply_plot_style(price_item)
    title = f"{symbol} {_PERIOD_NAMES.get(period, 'K线')}走势"
    price_item.setTitle(title)
    price_item.setLabel("left", "价格")

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
                pen=pg.mkPen(color=qcolor_to_rgba(color), width=1.4),
                name=label,
            )

    # 图例
    price_item.addLegend(offset=(10, 10))
    try:
        price_item.legend.setLabelTextColor(COLOR_FOREGROUND)
    except Exception:
        pass

    # 成交量子图 —— 占 30%
    vol_item = glw.addPlot(row=1, col=0)
    apply_plot_style(vol_item)
    vol_item.setLabel("left", "成交量")
    vol_item.setLabel("bottom", "日期")
    vol_item.setAxisItems({"bottom": axis})
    vol_item.setXLink(price_item)   # 共享 X 轴

    if "volume" in df.columns:
        vol = df["volume"].values.astype(float)
        # 按当日涨跌着色
        opens = df["open"].values.astype(float)
        closes = df["close"].values.astype(float)
        brushes = []
        for o, c in zip(opens, closes):
            col = COLOR_UP if c >= o else COLOR_DOWN
            brushes.append(pg.mkBrush((col.red(), col.green(), col.blue(), 180)))
        bar = pg.BarGraphItem(
            x=x, height=vol, width=0.6,
            brushes=brushes,
            pen=pg.mkPen(color=(0, 0, 0, 0)),
        )
        vol_item.addItem(bar)

    # 行高比例 7:3
    glw.ci.layout.setRowStretchFactor(0, 7)
    glw.ci.layout.setRowStretchFactor(1, 3)

    # 十字光标（主图）
    _install_kline_crosshair(price_item, vol_item, x, df, date_str)

    return glw


def _install_kline_crosshair(price_item, vol_item, x, df, date_str):
    """主图 + 成量子图联动的十字光标 + 数据提示"""
    vline = pg.InfiniteLine(angle=90,
        pen=pg.mkPen(color=(150, 150, 150, 180), width=1, style=Qt.DashLine))
    hline = pg.InfiniteLine(angle=0,
        pen=pg.mkPen(color=(150, 150, 150, 180), width=1, style=Qt.DashLine))
    price_item.addItem(vline, ignoreBounds=True)
    price_item.addItem(hline, ignoreBounds=True)

    vline_vol = pg.InfiniteLine(angle=90,
        pen=pg.mkPen(color=(150, 150, 150, 180), width=1, style=Qt.DashLine))
    vol_item.addItem(vline_vol, ignoreBounds=True)

    tip = pg.TextItem(anchor=(0, 1), color=COLOR_FOREGROUND)
    tip.setZValue(100)
    tip.hide()
    price_item.addItem(tip)

    x_arr = np.asarray(x, dtype=float)
    n = len(x_arr)
    opens = df["open"].values.astype(float) if "open" in df.columns else None
    highs = df["high"].values.astype(float) if "high" in df.columns else None
    lows = df["low"].values.astype(float) if "low" in df.columns else None
    closes = df["close"].values.astype(float) if "close" in df.columns else None
    vols = df["volume"].values.astype(float) if "volume" in df.columns else None

    def on_mouse_moved(evt_pos):
        if not price_item.sceneBoundingRect().contains(evt_pos):
            tip.hide()
            return
        mp = price_item.vb.mapSceneToView(evt_pos)
        xv = mp.x()
        if n == 0:
            return
        idx = int(np.clip(round(xv), 0, n - 1))
        vline.setPos(x_arr[idx])
        vline_vol.setPos(x_arr[idx])
        if closes is not None:
            hline.setPos(closes[idx])
        date_label = date_str[idx] if 0 <= idx < len(date_str) else ""

        parts = [date_label]
        if opens is not None:
            parts.append(f"开:{opens[idx]:.2f}")
        if highs is not None:
            parts.append(f"高:{highs[idx]:.2f}")
        if lows is not None:
            parts.append(f"低:{lows[idx]:.2f}")
        if closes is not None:
            parts.append(f"收:{closes[idx]:.2f}")
        if vols is not None:
            parts.append(f"量:{vols[idx]:,.0f}")
        if closes is not None:
            tip.setPos(x_arr[idx], closes[idx])
        tip.setText("\n".join(parts))
        tip.show()

    price_item.scene().sigMouseMoved.connect(on_mouse_moved)
