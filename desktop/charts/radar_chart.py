"""
desktop/charts/radar_chart — 交易雷达图（QPainter 自绘）

pyqtgraph 没有原生极坐标/雷达图。这里用 QPainter 在 QWidget 上自绘：
- N 边形参考网格（5 圈，对应 20/40/60/80/100 分）
- 数据多边形（半透明填充 + 边线）
- 轴标签（因子名）+ 顶点数值
"""
import math
import numpy as np
from PySide6.QtWidgets import QWidget, QSizePolicy
from PySide6.QtGui import (QPainter, QPen, QBrush, QColor, QPainterPath,
                            QPolygonF, QFont, QFontMetrics)
from PySide6.QtCore import QPointF, QRectF, Qt

from desktop.charts.theme import COLOR_EQUITY, COLOR_FOREGROUND, COLOR_GRID


class RadarChartWidget(QWidget):
    """雷达图 widget

    Args:
        labels: 各轴标签（因子名）
        values: 各轴数值（0-100）
        value_max: 数值上限（默认 100）
    """

    def __init__(self, labels, values, value_max=100, parent=None):
        super().__init__(parent)
        self._labels = list(labels) if labels else []
        self._values = [float(v) for v in values] if values else []
        self._value_max = float(value_max) if value_max > 0 else 100.0
        self.setMinimumHeight(360)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def set_data(self, labels, values, value_max=None):
        self._labels = list(labels) if labels else []
        self._values = [float(v) for v in values] if values else []
        if value_max is not None:
            self._value_max = float(value_max) if value_max > 0 else 100.0
        self.update()

    # ---- paint ----
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w = self.width()
        h = self.height()
        cx, cy = w / 2, h / 2
        # 半径留出标签空间
        radius = min(w, h) / 2 - 60
        if radius < 50:
            painter.end()
            return

        n = len(self._labels)
        if n < 3:
            painter.setPen(QPen(COLOR_FOREGROUND))
            painter.drawText(QRectF(0, 0, w, h), Qt.AlignCenter,
                             "因子数据不足，无法绘制雷达图（至少 3 个）")
            painter.end()
            return

        # 每个轴的角度（从顶部开始，顺时针）
        # 顶部= -90°
        angles = [-90.0 + 360.0 * i / n for i in range(n)]

        # ----- 1) 参考网格：5 圈 N 边形 -----
        grid_levels = [0.2, 0.4, 0.6, 0.8, 1.0]
        grid_pen = QPen(COLOR_GRID, 1, Qt.SolidLine)
        painter.setPen(grid_pen)
        for level in grid_levels:
            r = radius * level
            poly = QPolygonF([
                QPointF(cx + r * math.cos(math.radians(a)),
                        cy + r * math.sin(math.radians(a)))
                for a in angles
            ])
            painter.drawPolygon(poly)

        # ----- 2) 轴线（从中心到顶点）-----
        axis_pen = QPen(QColor(156, 163, 175), 1)
        painter.setPen(axis_pen)
        for a in angles:
            painter.drawLine(
                QPointF(cx, cy),
                QPointF(cx + radius * math.cos(math.radians(a)),
                        cy + radius * math.sin(math.radians(a))),
            )

        # ----- 3) 网格刻度文字 -----
        scale_font = QFont("Microsoft YaHei", 8)
        painter.setFont(scale_font)
        painter.setPen(QPen(QColor(107, 114, 128)))
        fm = QFontMetrics(scale_font)
        for level in grid_levels:
            txt = f"{int(self._value_max * level)}"
            painter.drawText(
                QPointF(cx + 4, cy - radius * level + fm.ascent()),
                txt,
            )

        # ----- 4) 数据多边形 -----
        vmax = self._value_max
        points = []
        for i, v in enumerate(self._values):
            v_clipped = max(0.0, min(vmax, v))
            r = radius * (v_clipped / vmax)
            a = angles[i]
            points.append(QPointF(
                cx + r * math.cos(math.radians(a)),
                cy + r * math.sin(math.radians(a)),
            ))
        poly = QPolygonF(points + [points[0]])  # 闭合

        # 填充
        fill_color = QColor(COLOR_EQUITY)
        fill_color.setAlpha(80)
        painter.setBrush(QBrush(fill_color))
        painter.setPen(QPen(COLOR_EQUITY, 2))
        painter.drawPolygon(poly)

        # 顶点圆点
        painter.setBrush(QBrush(COLOR_EQUITY))
        painter.setPen(QPen(COLOR_EQUITY, 1))
        for p in points:
            painter.drawEllipse(p, 3, 3)

        # ----- 5) 轴标签 + 数值 -----
        label_font = QFont("Microsoft YaHei", 9, QFont.Bold)
        painter.setFont(label_font)
        painter.setPen(QPen(COLOR_FOREGROUND))
        fm = QFontMetrics(label_font)
        val_font = QFont("Microsoft YaHei", 8)
        painter.setFont(val_font)
        fm_val = QFontMetrics(val_font)

        for i, (label, value) in enumerate(zip(self._labels, self._values)):
            a = angles[i]
            # 标签位置：顶点外 18px
            label_r = radius + 18
            lx = cx + label_r * math.cos(math.radians(a))
            ly = cy + label_r * math.sin(math.radians(a))

            painter.setFont(label_font)
            painter.setPen(QPen(COLOR_FOREGROUND))
            tw = fm.horizontalAdvance(label)
            painter.drawText(
                QPointF(lx - tw / 2, ly + fm.ascent() / 2 - 4),
                label,
            )
            # 数值（在标签下方）
            painter.setFont(val_font)
            painter.setPen(QPen(QColor(107, 114, 128)))
            val_str = f"{value:.1f}"
            tw = fm_val.horizontalAdvance(val_str)
            painter.drawText(
                QPointF(lx - tw / 2, ly + fm.ascent() / 2 + 12),
                val_str,
            )

        painter.end()


def build_radar_widget(labels, values, value_max=100, *, height=360):
    """便捷构造：返回 RadarChartWidget

    与其它 build_*_widget 风格一致，可传给 ChartContainer.set_plot_widget
    """
    w = RadarChartWidget(labels, values, value_max=value_max)
    w.setMinimumHeight(height)
    return w
