"""Web 图表绘制层。

集中存放所有 plotly 绘图函数，便于阶段 3 整体替换为 pyqtgraph。
当前实现基于 plotly，保持与原 app.py 行为一致。
"""

from .signal_charts import (
    plot_kline,
    plot_kline_with_signals,
    plot_signals_only,
    plot_multi_stock_signals,
    plot_signals_heatmap,
)

__all__ = [
    "plot_kline",
    "plot_kline_with_signals",
    "plot_signals_only",
    "plot_multi_stock_signals",
    "plot_signals_heatmap",
]
