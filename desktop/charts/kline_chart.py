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
    # 至少显示 10 根 K 线，最多显示全部（右侧多留一根空白给日期标签）
    max_span = float(n) + 1.0
    span = max(min(10.0, max_span), min(span, max_span))
    half = span / 2.0
    lo, hi = center - half, center + half
    # 钳制在数据范围内
    if lo < -0.5:
        hi += -0.5 - lo
        lo = -0.5
    if hi > n + 0.5:
        lo -= hi - (n + 0.5)
        hi = n + 0.5
    vb.setXRange(lo, hi, padding=0)


def build_kline_widget(
    df: pd.DataFrame,
    symbol: str,
    period: str = "D",
    *,
    height: int = 420,
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

    # 默认 view 铺满数据范围，左右各留半根 K 线的边距，
    # 右侧额外再多留一根，确保最右端日期标签不被裁切。
    def _init_x_range(vb, n_bars: int):
        if n_bars > 0:
            vb.setXRange(-0.5, n_bars + 0.5, padding=0)

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
    # 主图左侧不显示标签也要占位，否则与成交量子图左右不齐
    price_item.getAxis("left").setWidth(55)
    price_item.getAxis("right").setWidth(0)

    axis = AxisTime(date_str, orientation="bottom")
    axis.setTickFont(make_legend_font(8))      # 小字号，避免拥挤
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
    vol_item.showAxis("bottom", True)   # 显式开启横轴日期
    vol_item.setXLink(price_item)       # 共享 X 轴
    vol_item.setMaximumHeight(110)
    # 与主图保持同样的左侧/右侧轴宽，保证 K 线与成交量在 X 轴上严格对齐
    vol_item.getAxis("left").setWidth(55)
    vol_item.getAxis("right").setWidth(0)

    # 限制子图高度，避免在 420px 容器里底部横轴被裁掉
    price_item.setMinimumHeight(220)

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

    # 准备信息卡需要的额外字段（前收、成交额、换手率）
    prev_close = df["close"].shift(1).values.astype(float) if "close" in df.columns else None
    amount_arr = pd.to_numeric(df.get("amount"), errors="coerce").values if "amount" in df.columns else None
    turnover_arr = pd.to_numeric(df.get("turnover"), errors="coerce").values if "turnover" in df.columns else None

    # 初始化 X 轴范围，让首尾 K 线都完整显示在视口内
    _init_x_range(price_item.vb, n)
    # 关闭 X 轴自动缩放，避免 setXRange 被 pyqtgraph 自动 range 覆盖
    price_item.vb.disableAutoRange(pg.ViewBox.XAxis)
    vol_item.vb.disableAutoRange(pg.ViewBox.XAxis)

    # 行高比例 7:3
    glw.ci.layout.setRowStretchFactor(0, 7)
    glw.ci.layout.setRowStretchFactor(1, 3)
    glw.ci.layout.setRowSpacing(0, 2)     # 子图间隙收紧
    # 左右留空，避免首尾日期标签被裁切
    glw.ci.layout.setContentsMargins(6, 2, 40, 2)

    # 十字光标（主图 + 信息卡片 + 右轴价位标签 + 点击选中）
    _install_kline_crosshair(
        price_item, vol_item, x, df, date_str,
        prev_close=prev_close, amount_arr=amount_arr, turnover_arr=turnover_arr,
    )

    # 暴露给页面层：缩放按钮通过 zoom_kline_x(glw, factor) 操作
    glw.kline_vb = price_item.vb
    glw.kline_n = n

    return glw


def _install_kline_crosshair(
    price_item, vol_item, x, df, date_str,
    prev_close=None, amount_arr=None, turnover_arr=None,
):
    """主图 + 成交量子图联动的十字光标、信息卡片、右轴价位标签与点击选中。

    信息卡（OHLCV + 涨跌/振幅/成交额/换手率）默认始终显示最后一根 K 线数据；
    鼠标移动时更新为悬停位置的 K 线（不刷新信息卡），点击 K 线时锁定信息卡到
    该 K 线，并显示一条红色选中竖线，移出图表时选中态保持。
    """
    line_pen = pg.mkPen(color=(150, 150, 150, 140), width=1, style=Qt.DashLine)
    vline = pg.InfiniteLine(angle=90, pen=line_pen)
    hline = pg.InfiniteLine(angle=0, pen=line_pen)
    price_item.addItem(vline, ignoreBounds=True)
    price_item.addItem(hline, ignoreBounds=True)

    vline_vol = pg.InfiniteLine(angle=90, pen=line_pen)
    vol_item.addItem(vline_vol, ignoreBounds=True)

    # 选中竖线（点击后常驻）
    sel_pen = pg.mkPen(color=(229, 90, 78, 200), width=1, style=Qt.SolidLine)
    selected_vline = pg.InfiniteLine(angle=90, pen=sel_pen)
    selected_vline.setZValue(50)
    price_item.addItem(selected_vline, ignoreBounds=True)
    selected_vline_vol = pg.InfiniteLine(angle=90, pen=sel_pen)
    selected_vline_vol.setZValue(50)
    vol_item.addItem(selected_vline_vol, ignoreBounds=True)
    selected_vline.hide()
    selected_vline_vol.hide()

    # 信息卡片：白底圆角边框，固定在主图左上角
    tip = pg.TextItem(
        anchor=(0, 1), color=COLOR_FOREGROUND,
        fill=pg.mkBrush(255, 255, 255, 240),
        border=pg.mkPen(qcolor_to_rgba(COLOR_CARD_BORDER)),
    )
    tip.setFont(make_legend_font(9))
    tip.setZValue(100)
    price_item.addItem(tip, ignoreBounds=True)

    # 右轴价位标签：深底白字，跟随十字线横线
    tag = pg.TextItem(
        anchor=(1, 0.5), color=QColor("#ffffff"),
        fill=pg.mkBrush(qcolor_to_rgba(COLOR_TAG_BG)),
    )
    tag.setFont(make_legend_font(9))
    tag.setZValue(100)
    price_item.addItem(tag, ignoreBounds=True)

    x_arr = np.asarray(x, dtype=float)
    n = len(x_arr)
    opens = df["open"].values.astype(float) if "open" in df.columns else None
    highs = df["high"].values.astype(float) if "high" in df.columns else None
    lows = df["low"].values.astype(float) if "low" in df.columns else None
    closes = df["close"].values.astype(float) if "close" in df.columns else None
    vols = df["volume"].values.astype(float) if "volume" in df.columns else None
    if prev_close is None and closes is not None:
        prev_close = np.concatenate([[np.nan], closes[:-1]])

    def _fmt_volume(v):
        if v is None or not np.isfinite(v):
            return "-"
        if v >= 1e8:
            return f"{v / 1e8:.2f}亿"
        if v >= 1e4:
            return f"{v / 1e4:.0f}万"
        return f"{v:,.0f}"

    def _fmt_amount(v):
        if v is None or not np.isfinite(v):
            return "-"
        if v >= 1e8:
            return f"{v / 1e8:.2f}亿"
        if v >= 1e4:
            return f"{v / 1e4:.0f}万"
        return f"{v:,.0f}"

    def _fmt_pct(v):
        if v is None or not np.isfinite(v):
            return "-"
        return f"{v:+.2f}%"

    def _fmt_pct_unsigned(v):
        if v is None or not np.isfinite(v):
            return "-"
        return f"{v:.2f}%"

    def _build_html(idx: int) -> str:
        if closes is None or not (0 <= idx < n):
            return ""
        up = opens is None or closes[idx] >= opens[idx]
        col = "#E24B4A" if up else "#639922"
        date_label = date_str[idx] if 0 <= idx < len(date_str) else ""
        # 衍生指标
        pc = prev_close[idx] if prev_close is not None and idx < len(prev_close) else np.nan
        change = closes[idx] - pc if np.isfinite(pc) else np.nan
        change_pct = (change / pc * 100) if np.isfinite(pc) and pc != 0 else np.nan
        amp = ((highs[idx] - lows[idx]) / pc * 100) if (np.isfinite(pc) and pc != 0
                                                     and highs is not None and lows is not None) else np.nan
        if not np.isfinite(amp) and highs is not None and lows is not None and opens is not None and opens[idx] != 0:
            amp = (highs[idx] - lows[idx]) / opens[idx] * 100
        # OHLC/量/额
        lines = [f"<b>{date_label}</b>"]
        if opens is not None:
            lines.append(f'开 <span style="color:{col}">{opens[idx]:.2f}</span>')
        if highs is not None:
            lines.append(f"高 {highs[idx]:.2f}")
        if lows is not None:
            lines.append(f"低 {lows[idx]:.2f}")
        lines.append(f'收 <span style="color:{col}">{closes[idx]:.2f}</span>')
        if np.isfinite(change):
            chg_col = "#E24B4A" if change >= 0 else "#639922"
            lines.append(f'涨跌额 <span style="color:{chg_col}">{change:+.2f}</span>')
        if np.isfinite(change_pct):
            chg_col = "#E24B4A" if change_pct >= 0 else "#639922"
            lines.append(f'涨跌幅 <span style="color:{chg_col}">{change_pct:+.2f}%</span>')
        if np.isfinite(amp):
            lines.append(f"振幅 {amp:.2f}%")
        if vols is not None:
            lines.append(f"成交量 {_fmt_volume(vols[idx])}")
        if amount_arr is not None and idx < len(amount_arr):
            lines.append(f"成交额 {_fmt_amount(amount_arr[idx])}")
        if turnover_arr is not None and idx < len(turnover_arr) and np.isfinite(turnover_arr[idx]):
            lines.append(f"换手率 {turnover_arr[idx]:.2f}%")
        return "<br>".join(lines)

    def _reposition(price_y=None):
        """把卡片钉在可视区左上角、价位标签钉在右缘"""
        (xmin, xmax), (ymin, ymax) = price_item.vb.viewRange()
        pad = (xmax - xmin) * 0.012
        tip.setPos(xmin + pad, ymax)
        if price_y is not None:
            tag.setPos(xmax - pad, price_y)

    def _update_crosshair(idx: int):
        """仅更新悬停十字线、信息卡和价位标签（不改变选中态）"""
        if closes is None or not (0 <= idx < n):
            return
        price = closes[idx]
        vline.setPos(x_arr[idx])
        vline_vol.setPos(x_arr[idx])
        hline.setPos(price)
        tip.setHtml(_build_html(idx))
        tip.show()
        tag.setText(f"{price:.2f}")
        tag.show()
        _reposition(price)

    def _update_selected(idx: int):
        """点击选中：在 K 线上锁定信息卡与红色选中线"""
        if closes is None or not (0 <= idx < n):
            return
        selected_vline.setPos(x_arr[idx])
        selected_vline.show()
        selected_vline_vol.setPos(x_arr[idx])
        selected_vline_vol.show()
        _update_crosshair(idx)

    # 初始默认显示最后一根 K 线的明细（无需用户悬停）
    if n > 0:
        _update_crosshair(n - 1)

    def on_mouse_moved(evt_pos):
        if not price_item.sceneBoundingRect().contains(evt_pos):
            return
        mp = price_item.vb.mapSceneToView(evt_pos)
        xv = mp.x()
        if n == 0:
            return
        idx = int(np.clip(round(xv), 0, n - 1))
        _update_crosshair(idx)

    def on_mouse_clicked(evt):
        if not price_item.sceneBoundingRect().contains(evt.scenePos()):
            return
        mp = price_item.vb.mapSceneToView(evt.scenePos())
        xv = mp.x()
        if n == 0:
            return
        idx = int(np.clip(round(xv), 0, n - 1))
        _update_selected(idx)

    price_item.scene().sigMouseMoved.connect(on_mouse_moved)
    price_item.scene().sigMouseClicked.connect(on_mouse_clicked)
