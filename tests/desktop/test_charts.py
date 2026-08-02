"""
desktop/charts 单元测试 — 阶段4 pyqtgraph 原生图表

覆盖 7 个图表模块的构建 + 边界条件：
- candlestick.CandlestickItem
- equity_chart.build_equity_widget
- exposure_chart.build_exposure_widget
- heatmap_chart.build_heatmap_widget / build_signal_heatmap_widget
- multi_stock_chart.build_multi_stock_widget
- attribution_chart.build_attribution_widget
- kline_chart.build_kline_widget
- radar_chart.RadarChartWidget
"""
import sys
import os
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pyqtgraph as pg
from PySide6.QtGui import QColor

from desktop.charts.candlestick import CandlestickItem, AxisTime
from desktop.charts.equity_chart import build_equity_widget
from desktop.charts.exposure_chart import build_exposure_widget
from desktop.charts.heatmap_chart import build_heatmap_widget, build_signal_heatmap_widget
from desktop.charts.multi_stock_chart import build_multi_stock_widget
from desktop.charts.attribution_chart import build_attribution_widget
from desktop.charts.kline_chart import build_kline_widget
from desktop.charts.radar_chart import RadarChartWidget, build_radar_widget
from desktop.charts.theme import (
    COLOR_UP, COLOR_DOWN, apply_plot_style, factor_color, qcolor_to_rgba,
)


# ========== 共用 fixtures ==========

@pytest.fixture
def sample_ohlcv():
    """60 根模拟 K 线"""
    np.random.seed(42)
    n = 60
    dates = pd.date_range("2024-01-01", periods=n, freq="B").strftime("%Y-%m-%d")
    close = 10 + np.cumsum(np.random.randn(n) * 0.3)
    opens = close - np.random.randn(n) * 0.2
    highs = np.maximum(opens, close) + np.random.rand(n) * 0.3
    lows = np.minimum(opens, close) - np.random.rand(n) * 0.3
    vols = np.random.randint(100000, 500000, n).astype(float)
    return pd.DataFrame({
        "date": dates, "open": opens, "high": highs,
        "low": lows, "close": close, "volume": vols,
    })


@pytest.fixture
def sample_equity():
    n = 60
    dates = pd.date_range("2024-01-01", periods=n, freq="B").strftime("%Y-%m-%d")
    return pd.DataFrame({
        "date": dates,
        "total_value": 1_000_000 * np.cumprod(1 + np.random.randn(n) * 0.012 + 0.0008),
        "benchmark": 1_000_000 * np.cumprod(1 + np.random.randn(n) * 0.01 + 0.0005),
    })


# ========== theme ==========

class TestTheme:
    def test_up_color_is_red(self):
        assert COLOR_UP.red() > COLOR_UP.green(), "涨色应为红"

    def test_down_color_is_green(self):
        assert COLOR_DOWN.green() > COLOR_DOWN.red(), "跌色应为绿"

    def test_qcolor_to_rgba(self):
        assert qcolor_to_rgba(COLOR_UP) == (239, 68, 68, 255)

    def test_factor_color_cycles(self):
        c0 = factor_color(0)
        c8 = factor_color(8)
        assert c0 == c8  # 8 色循环

    def test_apply_plot_style_no_raise(self, qapp):
        w = pg.PlotWidget()
        apply_plot_style(w.getPlotItem())  # 不应抛异常


# ========== CandlestickItem ==========

class TestCandlestickItem:
    def test_basic_construction(self, qapp):
        data = np.array([
            [0, 10, 12, 9, 11],     # 涨
            [1, 11, 12, 9, 10],     # 跌
        ], dtype=float)
        item = CandlestickItem(data)
        br = item.boundingRect()
        assert br.width() > 0 and br.height() > 0

    def test_empty_data(self, qapp):
        item = CandlestickItem(np.zeros((0, 5)))
        br = item.boundingRect()
        # 空数据的 boundingRect 应是无效或零宽
        assert br.isNull() or br.width() == 0

    def test_invalid_shape_raises(self, qapp):
        with pytest.raises(ValueError):
            CandlestickItem(np.zeros((5, 3)))


# ========== AxisTime ==========

class TestAxisTime:
    def test_tick_strings(self, qapp):
        dates = ["2024-01-01", "2024-01-02", "2024-01-03"]
        axis = AxisTime(dates)
        assert axis.tickStrings([0, 1, 2], 1, 1) == dates
        assert axis.tickStrings([-1, 99], 1, 1) == ["", ""]

    def test_set_dates(self, qapp):
        axis = AxisTime([])
        axis.set_dates(["a", "b"])
        assert axis.tickStrings([0], 1, 1) == ["a"]


# ========== equity_chart ==========

class TestEquityChart:
    def test_basic(self, qapp, sample_equity):
        w = build_equity_widget(sample_equity)
        assert isinstance(w, pg.PlotWidget)

    def test_with_benchmark(self, qapp, sample_equity):
        w = build_equity_widget(sample_equity, benchmark_col="benchmark")
        assert isinstance(w, pg.PlotWidget)

    def test_no_benchmark_col(self, qapp, sample_equity):
        df = sample_equity.drop(columns=["benchmark"])
        w = build_equity_widget(df)
        assert isinstance(w, pg.PlotWidget)

    def test_empty_df(self, qapp):
        w = build_equity_widget(pd.DataFrame({"date": [], "total_value": []}))
        assert isinstance(w, pg.PlotWidget)

    def test_none(self, qapp):
        w = build_equity_widget(None)
        assert isinstance(w, pg.PlotWidget)


# ========== exposure_chart ==========

class TestExposureChart:
    def test_three_columns_stack(self, qapp):
        n = 30
        df = pd.DataFrame(
            np.random.rand(n, 3),
            index=pd.date_range("2024-01-01", periods=n, freq="B"),
            columns=["市值", "动量", "质量"],
        )
        w = build_exposure_widget(df)
        assert isinstance(w, pg.PlotWidget)

    def test_five_columns_lines(self, qapp):
        n = 20
        df = pd.DataFrame(
            np.random.rand(n, 5),
            index=pd.date_range("2024-01-01", periods=n, freq="B"),
        )
        w = build_exposure_widget(df)
        assert isinstance(w, pg.PlotWidget)

    def test_empty(self, qapp):
        w = build_exposure_widget(pd.DataFrame())
        assert isinstance(w, pg.PlotWidget)

    def test_none(self, qapp):
        w = build_exposure_widget(None)
        assert isinstance(w, pg.PlotWidget)


# ========== heatmap_chart ==========

class TestHeatmapChart:
    def test_basic_with_text(self, qapp):
        mat = np.random.randint(0, 100, (3, 5))
        w = build_heatmap_widget(
            mat, ["d1", "d2", "d3", "d4", "d5"], ["s1", "s2", "s3"],
            color_stops=[(0, QColor("#dc2626")), (1, QColor("#16a34a"))],
            zmin=0, zmax=100, text=mat.astype(str),
        )
        assert isinstance(w, pg.GraphicsLayoutWidget)

    def test_empty(self, qapp):
        w = build_heatmap_widget(np.zeros((0, 0)), [], [])
        assert isinstance(w, pg.GraphicsLayoutWidget)

    def test_signal_heatmap(self, qapp):
        dates = pd.date_range("2024-01-01", periods=10, freq="B")
        syms = ["000001.SZ", "000002.SZ", "600000.SH"]
        sigs = {s: pd.Series(np.random.choice([-1, 0, 1], 10), index=dates) for s in syms}
        w = build_signal_heatmap_widget(sigs, syms, dates)
        assert isinstance(w, pg.GraphicsLayoutWidget)


# ========== multi_stock_chart ==========

class TestMultiStockChart:
    def test_basic(self, qapp):
        np.random.seed(0)
        n = 30
        dates = pd.date_range("2024-01-01", periods=n, freq="B").strftime("%Y-%m-%d")
        syms = ["000001.SZ", "000002.SZ", "600000.SH"]
        stock_data = {}
        signals = {}
        for s in syms:
            close = 10 + np.cumsum(np.random.randn(n) * 0.3)
            stock_data[s] = pd.DataFrame({"date": dates, "close": close})
            signals[s] = pd.Series(np.random.choice([-1, 0, 1], n), index=dates)
        w = build_multi_stock_widget(stock_data, signals, syms)
        assert isinstance(w, pg.GraphicsLayoutWidget)

    def test_empty(self, qapp):
        w = build_multi_stock_widget({}, {}, [])
        assert isinstance(w, pg.GraphicsLayoutWidget)


# ========== attribution_chart ==========

class TestAttributionChart:
    def test_basic(self, qapp):
        attr = {
            "roe": {"contribution": 0.05, "factor_return": 1.2},
            "pe": {"contribution": -0.03, "factor_return": -0.8},
            "pb": {"contribution": 0.02, "factor_return": 0.5},
        }
        w = build_attribution_widget(attr)
        assert isinstance(w, pg.GraphicsLayoutWidget)

    def test_empty(self, qapp):
        w = build_attribution_widget({})
        assert isinstance(w, pg.GraphicsLayoutWidget)


# ========== kline_chart ==========

class TestKlineChart:
    def test_daily(self, qapp, sample_ohlcv):
        w = build_kline_widget(sample_ohlcv, "000001.SZ", "D")
        assert isinstance(w, pg.GraphicsLayoutWidget)

    def test_weekly(self, qapp, sample_ohlcv):
        w = build_kline_widget(sample_ohlcv, "000001.SZ", "W")
        assert isinstance(w, pg.GraphicsLayoutWidget)

    def test_monthly(self, qapp, sample_ohlcv):
        w = build_kline_widget(sample_ohlcv, "000001.SZ", "M")
        assert isinstance(w, pg.GraphicsLayoutWidget)

    def test_empty(self, qapp):
        w = build_kline_widget(pd.DataFrame(), "X", "D")
        assert isinstance(w, pg.GraphicsLayoutWidget)

    def test_none(self, qapp):
        w = build_kline_widget(None, "X", "D")
        assert isinstance(w, pg.GraphicsLayoutWidget)

    def test_large_dataset_performance(self, qapp):
        """10000 根 K 线构建应在 3 秒内完成（验收标准）"""
        import time
        np.random.seed(0)
        n = 10000
        dates = pd.date_range("1990-01-01", periods=n, freq="B").strftime("%Y-%m-%d")
        close = 10 + np.cumsum(np.random.randn(n) * 0.3)
        df = pd.DataFrame({
            "date": dates,
            "open": close - np.random.randn(n) * 0.2,
            "high": np.maximum(close, close - np.random.randn(n) * 0.2) + np.random.rand(n) * 0.3,
            "low": np.minimum(close, close - np.random.randn(n) * 0.2) - np.random.rand(n) * 0.3,
            "close": close,
            "volume": np.random.randint(100000, 500000, n).astype(float),
        })
        t0 = time.time()
        w = build_kline_widget(df, "BIG", "D")
        elapsed = time.time() - t0
        assert isinstance(w, pg.GraphicsLayoutWidget)
        assert elapsed < 3.0, f"10000 根 K 线构建耗时 {elapsed:.2f}s 超标"


# ========== radar_chart ==========

class TestRadarChart:
    def test_basic_five_factors(self, qapp):
        w = build_radar_widget(["ROE", "营收增长", "PE", "PB", "动量"],
                                [85, 60, 45, 70, 90])
        assert isinstance(w, RadarChartWidget)

    def test_minimum_three_factors(self, qapp):
        w = build_radar_widget(["A", "B", "C"], [50, 60, 70])
        assert isinstance(w, RadarChartWidget)

    def test_less_than_three_falls_back(self, qapp):
        """<3 因子时应能正常构造（paint 时显示提示）"""
        w = build_radar_widget(["A", "B"], [50, 60])
        assert isinstance(w, RadarChartWidget)

    def test_set_data_updates(self, qapp):
        w = build_radar_widget(["A", "B", "C"], [50, 60, 70])
        w.set_data(["X", "Y", "Z", "W"], [40, 50, 60, 70])
        assert len(w._labels) == 4

    def test_paint_does_not_raise(self, qapp):
        w = build_radar_widget(["A", "B", "C", "D"], [40, 50, 60, 70])
        w.resize(400, 400)
        w.grab()      # 触发 paintEvent
