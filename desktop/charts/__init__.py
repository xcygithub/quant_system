"""
desktop/charts — pyqtgraph 原生图表层（阶段4）

阶段3 用 QtWebEngine 嵌 plotly 过渡，阶段4 全部换成 pyqtgraph 原生实现：
- 启动更快（无 Chromium 内核）、内存更省、打包体积小
- 10000+ 数据点流畅交互
- 配色统一中国股市惯例：涨红跌绿

模块组织：
- theme.py        — 统一配色 / 字体 / 网格样式
- candlestick.py  — K线 CandlestickItem 自定义图元
- kline_chart.py  — K线图 + 成交量子图 + 信号标注
- equity_chart.py — 权益曲线（带基准对比 + 填充）
- heatmap_chart.py— 信号热力图（ImageItem + ColorMap）
- multi_stock_chart.py — 多股票信号子图
- exposure_chart.py    — 因子暴露度堆叠面积
- attribution_chart.py — 因子归因 1x2 子图
- radar_chart.py — 交易雷达（QPainter 自绘）
"""
