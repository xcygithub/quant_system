"""
desktop/charts/candlestick — K线 CandlestickItem 自定义图元

pyqtgraph 0.13 没有内置 CandlestickItem，参考官方 examples 自实现。

中国股市配色：涨红跌绿（OHLC 一根 K 线包含 open/high/low/close）。
"""
import numpy as np
from PySide6.QtGui import QPainter, QPicture, QColor, QPen, QBrush
from PySide6.QtCore import QRectF, QPointF

import pyqtgraph as pg

from desktop.charts.theme import COLOR_UP, COLOR_DOWN, COLOR_FLAT


class CandlestickItem(pg.GraphicsObject):
    """K 线图元

    Args:
        data: (N, 5) ndarray，列依次为 [time_idx, open, high, low, close]
              time_idx 用整数索引（0,1,2...），X 轴通过 AxisTime 设置为日期刻度
    """

    def __init__(self, data=None):
        super().__init__()
        # 内部以 QPicture 缓存绘制命令，paint 时直接 drawPicture
        self._picture = QPicture()
        self._bound = QRectF()
        if data is not None:
            self.set_data(data)

    # ---- 数据接口 ----
    def set_data(self, data):
        """data: (N,5) array-like [time_idx, open, high, low, close]"""
        arr = np.asarray(data, dtype=float)
        if arr.size == 0:
            self._picture = QPicture()
            self._bound = QRectF()
            self.update()
            self.informViewBoundsChanged()
            return

        if arr.ndim != 2 or arr.shape[1] != 5:
            raise ValueError(
                f"CandlestickItem.set_data 需要 (N,5) 数组，收到 shape={arr.shape}"
            )

        p = QPainter(self._picture)
        # K 线宽度（数据单位），相对 1 个时间格的 60%
        w = 0.6

        for row in arr:
            t, o, h, l, c = row
            if not np.isfinite([t, o, h, l, c]).all():
                continue

            if c > o:
                color = COLOR_UP          # 涨：红实体（空心）
                pen = QPen(color, 1.0)
                brush = QBrush(color)
            elif c < o:
                color = COLOR_DOWN        # 跌：绿实体（实心）
                pen = QPen(color, 1.0)
                brush = QBrush(color)
            else:
                color = COLOR_FLAT
                pen = QPen(color, 1.0)
                brush = QBrush(color)

            # 1) 影线：从 low 到 high 的竖线
            p.setPen(pen)
            p.drawLine(QPointF(t, l), QPointF(t, h))

            # 2) 实体：open-close 构成的矩形
            body_top = max(o, c)
            body_bot = min(o, c)
            body_h = max(body_top - body_bot, w * 0.01)  # 防止 0 高度
            rect = QRectF(t - w / 2, body_bot, w, body_h)
            p.setBrush(brush)
            p.setPen(pen)
            p.drawRect(rect)

        p.end()

        # 计算 boundingRect（用于 view 自适应缩放）
        if arr.size:
            t_min = float(np.nanmin(arr[:, 0]))
            t_max = float(np.nanmax(arr[:, 0]))
            l_min = float(np.nanmin(arr[:, 3]))
            h_max = float(np.nanmax(arr[:, 2]))
            self._bound = QRectF(t_min - 1, l_min, (t_max - t_min) + 2, h_max - l_min)
        else:
            self._bound = QRectF()

        self.update()
        self.informViewBoundsChanged()
        self.prepareGeometryChange()

    # ---- GraphicsObject 必须实现 ----
    def paint(self, painter, option, widget=None):
        painter.drawPicture(0, 0, self._picture)

    def boundingRect(self) -> QRectF:
        return self._bound


class AxisTime(pg.AxisItem):
    """把整数索引转成日期字符串的 X 轴刻度

    Usage:
        axis = AxisTime(dates)   # dates: list[str] 'YYYY-MM-DD'
        plot_item.setAxisItems({'bottom': axis})
    """

    def __init__(self, dates, orientation="bottom", **kw):
        super().__init__(orientation, **kw)
        # dates[i] 对应 X=i 的日期；超出索引范围显示空
        self._dates = list(dates) if dates is not None else []

    def set_dates(self, dates):
        self._dates = list(dates) if dates is not None else []
        self.update()

    def tickStrings(self, values, scale, spacing):
        out = []
        for v in values:
            i = int(round(v))
            if 0 <= i < len(self._dates):
                out.append(self._dates[i])
            else:
                out.append("")
        return out
