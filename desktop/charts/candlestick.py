"""
desktop/charts/candlestick — K线 CandlestickItem 自定义图元

pyqtgraph 0.13 没有内置 CandlestickItem，参考官方 examples 自实现。

中国股市配色：涨红跌绿（OHLC 一根 K 线包含 open/high/low/close）。
"""
import numpy as np
from PySide6.QtGui import QPainter, QPicture, QColor, QPen, QBrush
from PySide6.QtCore import QRectF, QPointF, Qt

import pyqtgraph as pg

from desktop.charts.theme import COLOR_UP, COLOR_DOWN, COLOR_FLAT, COLOR_BACKGROUND


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
        p.setRenderHint(QPainter.Antialiasing, False)
        # K 线宽度（数据单位），相对 1 个时间格的 65%
        w = 0.65

        for row in arr:
            t, o, h, l, c = row
            if not np.isfinite([t, o, h, l, c]).all():
                continue

            if c > o:
                color = COLOR_UP
                hollow = True           # 阳线：红框空心
            elif c < o:
                color = COLOR_DOWN
                hollow = False          # 阴线：绿色实心
            else:
                color = COLOR_FLAT
                hollow = True

            # cosmetic pen：恒 1px，不随缩放变粗
            pen = QPen(color)
            pen.setWidth(1)
            pen.setCosmetic(True)

            # 1) 影线：从 low 到 high 的竖线
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            p.drawLine(QPointF(t, l), QPointF(t, h))

            # 2) 实体：open-close 构成的矩形
            body_top = max(o, c)
            body_bot = min(o, c)
            body_h = max(body_top - body_bot, w * 0.01)  # 防止 0 高度
            rect = QRectF(t - w / 2, body_bot, w, body_h)
            p.setPen(pen)
            if hollow:
                p.setBrush(QBrush(COLOR_BACKGROUND))   # 空心：白底
            else:
                p.setBrush(QBrush(color))              # 实心
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
        # 按刻度间距选日期格式：跨度大显示年月，密集时只显月日
        if spacing >= 250:
            fmt = lambda s: s[:7]        # YYYY-MM
        elif spacing >= 40:
            fmt = lambda s: s[:10]       # YYYY-MM-DD
        else:
            fmt = lambda s: s[5:10]      # MM-DD

        out = []
        prev = None
        for v in values:
            i = int(round(v))
            if 0 <= i < len(self._dates):
                s = fmt(self._dates[i])
                # 连续相同标签去重，避免一排重复文字
                if s == prev:
                    s = ""
                else:
                    prev = s
                out.append(s)
            else:
                out.append("")
        return out
