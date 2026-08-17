"""
desktop/charts/theme — pyqtgraph 图表统一配色与样式

中国股市配色约定：涨红跌绿（与欧美相反）。
所有 chart 模块必须从这里取色，不得硬编码十六进制值。
"""
from PySide6.QtGui import QColor, QFont

# ========== 中国股市配色：涨红跌绿 ==========
# 与 theme.qss v2.0 设计系统对齐
COLOR_UP = QColor("#E24B4A")          # 涨：红色
COLOR_DOWN = QColor("#639922")        # 跌：绿色
COLOR_FLAT = QColor("#6b7280")        # 平：灰色

# 信号标注
COLOR_BUY = QColor("#E24B4A")         # 买入：红
COLOR_SELL = QColor("#639922")        # 卖出：绿
COLOR_HOLD = QColor("#9ca3af")        # 持仓：浅灰

# 曲线 / 数据系列
COLOR_EQUITY = QColor("#3b82f6")      # 权益曲线：蓝
COLOR_BENCHMARK = QColor("#f59e0b")   # 基准：橙
COLOR_FILL = QColor("#3b82f6")        # 填充：蓝（半透明）

# 因子系列（用于多因子对比，循环使用）
COLOR_FACTOR_SERIES = [
    QColor("#3b82f6"),   # 蓝
    QColor("#f59e0b"),   # 橙
    QColor("#8b5cf6"),   # 紫
    QColor("#14b8a6"),   # 青
    QColor("#ec4899"),   # 粉
    QColor("#84cc16"),   # 黄绿
    QColor("#06b6d4"),   # 天蓝
    QColor("#f97316"),   # 深橙
]

# 网格 / 坐标轴
COLOR_AXIS = QColor("#374151")        # 坐标轴：深灰
COLOR_GRID = QColor(229, 231, 235)    # 网格线：浅灰
COLOR_BACKGROUND = QColor("#ffffff")  # 背景：白
COLOR_FOREGROUND = QColor("#1f2937")  # 文字：近黑

# 热力图色阶（绿-灰-红，对应 持仓-空-买入）
COLOR_HEATMAP_STOPS = [
    (0.0,  QColor("#639922")),    # -1 卖出
    (0.5,  QColor("#f3f4f6")),    #  0 空仓
    (1.0,  QColor("#E24B4A")),    #  1 买入
]

# 卡片/提示框
COLOR_CARD_BORDER = QColor("#D3D1C7")  # 提示卡片边框
COLOR_TAG_BG = QColor("#444441")       # 轴价位标签底色


def apply_plot_style(plot_item, *, show_grid=True):
    """统一应用 pyqtgraph PlotItem 样式：白底、浅灰网格、深色字。

    Args:
        plot_item: pg.PlotItem
        show_grid: 是否显示网格
    """
    # 背景要设到 ViewBox 上（PlotItem 本身没有 setBackground）
    try:
        plot_item.getViewBox().setBackgroundColor(COLOR_BACKGROUND)
    except Exception:
        pass

    axis_color = COLOR_AXIS
    for axis_name in ("left", "bottom"):
        ax = plot_item.getAxis(axis_name)
        ax.setPen(axis_color)
        ax.setTextPen(COLOR_FOREGROUND)

    # pg 0.13.7 的 AxisItem.setGrid 只接受 bool，网格颜色由 ViewBox 控制
    if show_grid:
        plot_item.showGrid(x=True, y=True, alpha=0.25)
    else:
        plot_item.showGrid(x=False, y=False)

    font = QFont("Microsoft YaHei", 9)
    for axis_name in ("left", "bottom"):
        plot_item.getAxis(axis_name).setTickFont(font)


def make_legend_font(size: int = 10) -> QFont:
    return QFont("Microsoft YaHei", size)


def factor_color(index: int) -> QColor:
    """按索引取因子系列颜色（循环）"""
    return COLOR_FACTOR_SERIES[index % len(COLOR_FACTOR_SERIES)]


def qcolor_to_rgba(qc: QColor, alpha: int = 255) -> tuple:
    """QColor -> (r, g, b, a) 0-255 整数，pyqtgraph pen/brush 用"""
    return (qc.red(), qc.green(), qc.blue(), alpha)
