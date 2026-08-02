"""
桌面组件单元测试 — PandasTable / MessageBar / MetricCard / SectionTitle / StockSelector / ChartContainer
"""
import pandas as pd
import numpy as np
from PySide6.QtCore import Qt, QAbstractTableModel

from desktop.widgets.pandas_table import (
    PandasTableModel, PandasTableView, make_change_color_rule,
    COLOR_UP, COLOR_DOWN, COLOR_FLAT,
)
from desktop.widgets.message_bar import MessageBar, MessageHelper
from desktop.widgets.metric_card import MetricCard, create_metric_row
from desktop.widgets.section_title import SectionTitle, PageTitle, PageHero
from desktop.widgets.stock_selector import StockSelector, StockPoolSelector
from desktop.widgets.chart_container import ChartContainer, check_webengine_available


# ===== PandasTableModel =====

class TestPandasTableModel:

    def test_basic_dimensions(self, qapp):
        df = pd.DataFrame({'A': [1, 2, 3], 'B': ['x', 'y', 'z']})
        model = PandasTableModel(df)
        assert model.rowCount() == 3
        assert model.columnCount() == 2

    def test_display_data(self, qapp):
        df = pd.DataFrame({'股票': ['000001.SZ']})
        model = PandasTableModel(df)
        assert model.data(model.index(0, 0)) == '000001.SZ'

    def test_formatter(self, qapp):
        df = pd.DataFrame({'价格': [10.567]})
        model = PandasTableModel(df, formatters={'价格': '{:.2f}'})
        assert model.data(model.index(0, 0)) == '10.57'

    def test_formatter_percent(self, qapp):
        df = pd.DataFrame({'涨幅': [2.3]})
        model = PandasTableModel(df, formatters={'涨幅': '{:+.2f}%'})
        assert model.data(model.index(0, 0)) == '+2.30%'

    def test_nan_display(self, qapp):
        df = pd.DataFrame({'A': [float('nan')]})
        model = PandasTableModel(df)
        assert model.data(model.index(0, 0)) == ''

    def test_nan_with_formatter(self, qapp):
        df = pd.DataFrame({'A': [float('nan')]})
        model = PandasTableModel(df, formatters={'A': '{:.2f}'})
        assert model.data(model.index(0, 0)) == '-'

    def test_color_rule_up(self, qapp):
        df = pd.DataFrame({'涨幅': [2.3]})
        model = PandasTableModel(df, color_rules={'涨幅': make_change_color_rule()})
        brush = model.data(model.index(0, 0), Qt.ForegroundRole)
        assert brush is not None
        assert brush.color().name() == COLOR_UP

    def test_color_rule_down(self, qapp):
        df = pd.DataFrame({'涨幅': [-1.5]})
        model = PandasTableModel(df, color_rules={'涨幅': make_change_color_rule()})
        brush = model.data(model.index(0, 0), Qt.ForegroundRole)
        assert brush.color().name() == COLOR_DOWN

    def test_color_rule_nan(self, qapp):
        df = pd.DataFrame({'涨幅': [float('nan')]})
        model = PandasTableModel(df, color_rules={'涨幅': make_change_color_rule()})
        brush = model.data(model.index(0, 0), Qt.ForegroundRole)
        assert brush is None

    def test_header_data(self, qapp):
        df = pd.DataFrame({'股票': [1], '价格': [2]})
        model = PandasTableModel(df)
        assert model.headerData(0, Qt.Horizontal) == '股票'
        assert model.headerData(1, Qt.Horizontal) == '价格'
        # 默认隐藏行索引
        assert model.headerData(0, Qt.Vertical) is None

    def test_sort_ascending(self, qapp):
        df = pd.DataFrame({'A': [3, 1, 2]})
        model = PandasTableModel(df)
        model.sort(0, Qt.AscendingOrder)
        assert model.data(model.index(0, 0)) == '1'
        assert model.data(model.index(2, 0)) == '3'

    def test_update_data(self, qapp):
        df1 = pd.DataFrame({'A': [1]})
        model = PandasTableModel(df1)
        assert model.rowCount() == 1
        df2 = pd.DataFrame({'A': [1, 2, 3, 4]})
        model.update_data(df2)
        assert model.rowCount() == 4

    def test_get_row_data(self, qapp):
        df = pd.DataFrame({'A': [10, 20]})
        model = PandasTableModel(df)
        row = model.get_row_data(0)
        assert row['A'] == 10
        assert model.get_row_data(99) is None


# ===== PandasTableView =====

class TestPandasTableView:

    def test_set_dataframe(self, qapp):
        df = pd.DataFrame({'A': [1, 2], 'B': ['x', 'y']})
        view = PandasTableView()
        view.set_dataframe(df)
        assert view.model().rowCount() == 2

    def test_get_selected_row_default(self, qapp):
        view = PandasTableView()
        view.set_dataframe(pd.DataFrame({'A': [1]}))
        assert view.get_selected_row() == -1


# ===== MessageBar =====

class TestMessageBar:

    def test_show_success(self, qapp):
        bar = MessageBar(closable=False)
        bar.success('ok')
        assert bar._text_label.text() == 'ok'

    def test_show_error(self, qapp):
        bar = MessageBar(closable=False)
        bar.error('fail')
        assert bar._text_label.text() == 'fail'

    def test_show_warning(self, qapp):
        bar = MessageBar(closable=False)
        bar.warning('warn')
        assert bar._text_label.text() == 'warn'

    def test_show_info(self, qapp):
        bar = MessageBar(closable=False)
        bar.info('info')
        assert bar._text_label.text() == 'info'

    def test_clear(self, qapp):
        bar = MessageBar(closable=False)
        bar.info('test')
        bar.clear()
        assert bar._text_label.text() == ''


# ===== MetricCard =====

class TestMetricCard:

    def test_basic(self, qapp):
        card = MetricCard('收益率', '12.5%', delta='📈')
        assert card._label_label.text() == '收益率'
        assert card._value_label.text() == '12.5%'
        assert card._delta_label.text() == '📈'

    def test_no_delta(self, qapp):
        card = MetricCard('数量', '4523')
        assert card._delta_label is None

    def test_auto_color_up(self):
        assert MetricCard._auto_color('+2.3%') == COLOR_UP

    def test_auto_color_down(self):
        assert MetricCard._auto_color('-1.5%') == COLOR_DOWN

    def test_auto_color_emoji(self):
        assert MetricCard._auto_color('📈') is None

    def test_auto_color_empty(self):
        assert MetricCard._auto_color('') is None

    def test_update(self, qapp):
        card = MetricCard('A', '1')
        card.update(value='2', delta='+5%')
        assert card._value_label.text() == '2'
        assert card._delta_label is not None

    def test_set_value(self, qapp):
        card = MetricCard('A', '1')
        card.set_value('99')
        assert card._value_label.text() == '99'


# ===== SectionTitle 组件族 =====

class TestSectionTitle:

    def test_section_title(self, qapp):
        t = SectionTitle('📊 测试', '描述')
        assert t is not None

    def test_section_title_no_desc(self, qapp):
        t = SectionTitle('标题')
        assert t is not None

    def test_page_title_dark(self, qapp):
        t = PageTitle('测试', theme='dark')
        assert t is not None

    def test_page_title_light(self, qapp):
        t = PageTitle('测试', '描述', theme='light')
        assert t is not None

    def test_page_hero(self, qapp):
        h = PageHero('标题', '副标题', ['徽章1', '徽章2'])
        assert h is not None

    def test_page_hero_no_badges(self, qapp):
        h = PageHero('标题')
        assert h is not None


# ===== StockSelector =====

class TestStockSelector:

    def test_set_stocks(self, qapp):
        sel = StockSelector()
        sel.set_stocks(['000001.SZ', '600000.SH'],
                       {'000001.SZ': '000001.SZ - 平安银行'})
        assert sel.get_selected_stock() == '000001.SZ'

    def test_set_selected(self, qapp):
        sel = StockSelector()
        sel.set_stocks(['000001.SZ', '600000.SH'])
        sel.set_selected_stock('600000.SH')
        assert sel.get_selected_stock() == '600000.SH'

    def test_signal(self, qapp):
        sel = StockSelector()
        received = []
        sel.stock_changed.connect(lambda s: received.append(s))
        sel.set_stocks(['000001.SZ', '600000.SH'])
        assert '000001.SZ' in received

    def test_clear(self, qapp):
        sel = StockSelector()
        sel.set_stocks(['000001.SZ'])
        sel.clear()
        assert sel.get_selected_stock() == ''


class TestStockPoolSelector:

    def test_watchlist_mode(self, qapp):
        pool = StockPoolSelector()
        pool.set_watchlist(['000001.SZ', '600000.SH'])
        assert pool.get_stocks() == ['000001.SZ', '600000.SH']

    def test_signal(self, qapp):
        pool = StockPoolSelector()
        received = []
        pool.stocks_changed.connect(lambda s: received.append(s))
        pool.set_watchlist(['000001.SZ'])
        assert len(received) >= 1


# ===== ChartContainer =====

class TestChartContainer:

    def test_instantiation(self, qapp):
        c = ChartContainer(title='测试')
        assert c is not None

    def test_no_title(self, qapp):
        c = ChartContainer()
        assert c is not None

    def test_check_webengine(self, qapp):
        result = check_webengine_available()
        assert isinstance(result, bool)

    def test_clear(self, qapp):
        c = ChartContainer()
        c.clear()  # 不应抛异常
