"""
desktop/charts/heatmap_chart — 通用热力图（ImageItem + ColorMap）

支持：
- 自定义色阶（绿-白-红 / RdYlGn 等）
- 行=股票 / 列=日期（或反之）
- 可选每格文字标注（如因子得分）
- y 轴从上往下显示（与表格习惯一致）
"""
import numpy as np
import pandas as pd
import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor

from desktop.charts.theme import (
    apply_plot_style, COLOR_FOREGROUND, COLOR_HEATMAP_STOPS,
)


def _make_colormap(stops):
    """stops: [(pos, QColor), ...] -> pg.ColorMap"""
    positions = [s[0] for s in stops]
    colors = [s[1] for s in stops]
    return pg.ColorMap(pos=positions, color=colors)


def build_heatmap_widget(
    matrix,
    x_labels,
    y_labels,
    *,
    color_stops=None,
    zmin=None,
    zmax=None,
    text=None,
    title: str = "热力图",
    height: int = 400,
    x_label: str = "日期",
    y_label: str = "股票",
) -> pg.GraphicsLayoutWidget:
    """构建热力图 widget

    Args:
        matrix: 2D array-like，shape=(len(y_labels), len(x_labels))
        x_labels: 列标签
        y_labels: 行标签
        color_stops: [(pos, QColor)] 色阶；默认绿-白-红
        zmin, zmax: 颜色映射范围；默认用矩阵 min/max
        text: 同 shape 的字符串矩阵，每格显示文字；None 不显示
        title: 标题
        height: 推荐高度
        x_label, y_label: 轴标签

    Returns:
        pg.GraphicsLayoutWidget
    """
    glw = pg.GraphicsLayoutWidget()
    glw.setMinimumHeight(height)
    item = glw.addPlot(title=title)
    item.setLabel("left", y_label)
    item.setLabel("bottom", x_label)
    apply_plot_style(item)

    # 转 numpy
    if isinstance(matrix, pd.DataFrame):
        mat = matrix.values
    elif isinstance(matrix, (list, tuple)):
        mat = np.asarray(mat, dtype=float)
    else:
        mat = np.asarray(matrix, dtype=float)

    if mat.size == 0 or len(x_labels) == 0 or len(y_labels) == 0:
        return glw

    n_rows, n_cols = mat.shape
    if n_rows != len(y_labels) or n_cols != len(x_labels):
        # 容错：尽量对齐
        n_rows = min(n_rows, len(y_labels))
        n_cols = min(n_cols, len(x_labels))
        mat = mat[:n_rows, :n_cols]

    if color_stops is None:
        color_stops = COLOR_HEATMAP_STOPS
    cmap = _make_colormap(color_stops)

    if zmin is None:
        zmin = float(np.nanmin(mat)) if mat.size else 0.0
    if zmax is None:
        zmax = float(np.nanmax(mat)) if mat.size else 1.0
    if zmax <= zmin:
        zmax = zmin + 1.0

    # ImageItem：pyqtgraph 的 image 原点在左上角，y 自上而下递增
    # 但我们的 y_labels 顺序是「第 0 行对应 y_labels[0]」
    # ImageItem 默认会把第 0 行画在 y=0 附近，再用 setRect 或 transform 调整
    # 简单做法：用 setRect 把图像映射到 [0, n_cols] x [0, n_rows]，
    # 再把 y 轴刻度反过来（第 0 行在顶部）
    img_item = pg.ImageItem()
    # 反转矩阵：让 y_labels[0] 显示在最上方
    img_data = mat[::-1, :]
    img_item.setImage(img_data, levels=(zmin, zmax))
    # 映射坐标：x∈[0, n_cols], y∈[0, n_rows]
    img_item.setRect(0, 0, n_cols, n_rows)
    # 应用色阶
    lut = cmap.getLookupTable(start=zmin, stop=zmax, nPts=256, alpha=True)
    img_item.setLookupTable(lut)
    item.addItem(img_item)

    # y 轴：让 y_labels[0] 在顶部
    y_axis = item.getAxis("left")
    y_axis.setTicks([[(i + 0.5, y_labels[i]) for i in range(n_rows)]])
    # 反转 y 轴方向（让 0 在顶部）
    item.invertY(False)
    item.setYRange(0, n_rows, padding=0)

    # x 轴：刻度放每列中心
    # 日期过多时只显示部分刻度
    max_ticks = 12
    step = max(1, n_cols // max_ticks)
    x_ticks = [(i + 0.5, str(x_labels[i])[:10]) for i in range(0, n_cols, step)]
    item.getAxis("bottom").setTicks([x_ticks])

    # 每格文字标注
    if text is not None:
        text_arr = np.asarray(text, dtype=str)
        for r in range(n_rows):
            for c in range(n_cols):
                # y 坐标反转
                y_pos = n_rows - 1 - r + 0.5
                x_pos = c + 0.5
                if r < text_arr.shape[0] and c < text_arr.shape[1]:
                    val = text_arr[r, c]
                    if val and val != "nan":
                        ti = pg.TextItem(str(val), color=COLOR_FOREGROUND,
                                         anchor=(0.5, 0.5))
                        ti.setPos(x_pos, y_pos)
                        item.addItem(ti)

    # 色阶条
    bar = pg.ColorBarItem(values=(zmin, zmax), colorMap=cmap, width=12)
    bar.setImageItem(img_item)

    return glw


def build_signal_heatmap_widget(
    signals: dict,
    symbols: list,
    dates,
    *,
    title: str = "信号热力图（红=买入 绿=卖出）",
    height: int = 400,
) -> pg.GraphicsLayoutWidget:
    """便捷构造：信号热力图

    Args:
        signals: {symbol: pd.Series(index=日期, values=信号)}
        symbols: 股票列表（决定行顺序）
        dates: 日期序列

    Returns:
        pg.GraphicsLayoutWidget
    """
    df = pd.DataFrame({
        s: sig.reindex(pd.to_datetime(dates)).ffill()
        for s, sig in signals.items() if s in symbols
    }).T
    date_str = [str(d)[:10] for d in df.columns]
    return build_heatmap_widget(
        df.values, date_str, list(df.index),
        color_stops=[(0.0, QColor("#16a34a")), (0.5, QColor("#ffffff")),
                     (1.0, QColor("#dc2626"))],
        zmin=-1, zmax=1,
        title=title, height=height,
        x_label="日期", y_label="股票",
    )
