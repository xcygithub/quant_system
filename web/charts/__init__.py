"""Web 图表绘制层。

阶段0 曾在此集中 5 个 plotly 绘图函数（signal_charts.py）。
阶段3 桌面端迁移时，桌面端直接在 pages 内联了 plotly 辅助函数，未引用此模块；
阶段4 桌面端改用 pyqtgraph 原生绘图（desktop/charts/），Web 端也停用本模块。
signal_charts.py 已删除，本 __init__.py 保留为空包标记。
"""
