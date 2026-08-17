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
from desktop.widgets.metric_card import MetricCard, create_metric_row, COLOR_NEUTRAL
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
        assert brush.color().name().lower() == COLOR_UP.lower()

    def test_color_rule_down(self, qapp):
        df = pd.DataFrame({'涨幅': [-1.5]})
        model = PandasTableModel(df, color_rules={'涨幅': make_change_color_rule()})
        brush = model.data(model.index(0, 0), Qt.ForegroundRole)
        assert brush.color().name().lower() == COLOR_DOWN.lower()

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

    def test_default_auto_clear_for_info(self, qapp):
        """info 默认 5s 自动清除，应启动 timer"""
        bar = MessageBar(closable=False)
        bar.info('loading...')
        assert bar._auto_clear_timer is not None
        assert bar._auto_clear_timer.isActive()

    def test_default_auto_clear_for_success(self, qapp):
        """success 默认 3s 自动清除，应启动 timer"""
        bar = MessageBar(closable=False)
        bar.success('done')
        assert bar._auto_clear_timer is not None
        assert bar._auto_clear_timer.isActive()

    def test_no_auto_clear_for_error(self, qapp):
        """error 默认持续显示，不应启动 timer"""
        bar = MessageBar(closable=False)
        bar.error('failed')
        assert bar._auto_clear_timer is None

    def test_no_auto_clear_for_warning(self, qapp):
        """warning 默认持续显示，不应启动 timer"""
        bar = MessageBar(closable=False)
        bar.warning('warn')
        assert bar._auto_clear_timer is None

    def test_explicit_auto_clear_zero_disables(self, qapp):
        """auto_clear_ms=0 显式禁用自动清除"""
        bar = MessageBar(closable=False)
        bar.info('persistent', auto_clear_ms=0)
        assert bar._auto_clear_timer is None

    def test_explicit_auto_clear_for_error(self, qapp):
        """error 也能显式开启自动清除"""
        bar = MessageBar(closable=False)
        bar.error('temp error', auto_clear_ms=3000)
        assert bar._auto_clear_timer is not None
        assert bar._auto_clear_timer.isActive()

    def test_clear_cancels_auto_clear_timer(self, qapp):
        """clear() 应取消已调度的自动清除 timer"""
        bar = MessageBar(closable=False)
        bar.info('will be cleared')
        assert bar._auto_clear_timer is not None
        bar.clear()
        assert bar._auto_clear_timer is None

    def test_new_message_resets_timer(self, qapp):
        """连续调用 show_message 应取消旧 timer 并启动新 timer"""
        bar = MessageBar(closable=False)
        bar.info('first')
        old_timer = bar._auto_clear_timer
        bar.info('second')
        assert bar._auto_clear_timer is not None
        assert bar._auto_clear_timer is not old_timer
        assert not old_timer.isActive()  # 旧 timer 已停止


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

    def test_value_color_up(self, qapp):
        """数值着色：上涨→红（涨红跌绿，A股惯例）"""
        card = MetricCard('上涨', '10', value_color='up')
        assert COLOR_UP in card._value_label.styleSheet()

    def test_value_color_down(self, qapp):
        """数值着色：下跌→绿"""
        card = MetricCard('下跌', '4', value_color='down')
        assert COLOR_DOWN in card._value_label.styleSheet()

    def test_value_color_neutral(self, qapp):
        """数值着色：平盘→灰"""
        card = MetricCard('平盘', '0', value_color='neutral')
        assert COLOR_NEUTRAL in card._value_label.styleSheet()

    def test_value_color_none_default(self, qapp):
        """默认不着色"""
        card = MetricCard('总数', '15')
        assert card._value_label.styleSheet() == ''

    def test_set_value_color_reset(self, qapp):
        """set_value_color('none') 恢复默认色"""
        card = MetricCard('上涨', '10', value_color='up')
        assert COLOR_UP in card._value_label.styleSheet()
        card.set_value_color('none')
        assert card._value_label.styleSheet() == ''


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

    def test_set_message_exists(self, qapp):
        """回归：4个页面共13处调用 set_message，该 API 必须存在"""
        c = ChartContainer()
        assert hasattr(c, 'set_message')
        c.set_message('暂无回测数据')          # 不应抛异常

    def test_set_message_levels(self, qapp):
        c = ChartContainer()
        for level in ('info', 'warning', 'error', '未知级别'):
            c.set_message('提示文本', level=level)

    def test_set_message_escapes_html(self, qapp):
        """文本里的 < > & 需要转义，避免破坏占位 HTML"""
        c = ChartContainer()
        c.set_message('渲染失败: <script> & "x"')

    def test_pages_calling_set_message_are_covered(self, qapp):
        """静态校验：页面里调用的 ChartContainer 方法都真实存在"""
        used = {'set_figure', 'set_html', 'set_message', 'set_plot_widget', 'clear'}
        missing = [m for m in used if not hasattr(ChartContainer, m)]
        assert not missing, f'ChartContainer 缺少方法: {missing}'

    def test_set_plot_widget_replaces_content(self, qapp):
        """阶段4：set_plot_widget 切到 pyqtgraph 路径"""
        import pyqtgraph as pg
        import numpy as np
        c = ChartContainer()
        c.set_message('初始占位')
        assert c.content_kind == 'message'
        w = pg.PlotWidget()
        w.plot(np.arange(20), np.random.random(20))
        c.set_plot_widget(w)
        assert c.content_kind == 'pyqtgraph'

    def test_set_plot_widget_releases_webengine(self, qapp):
        """从 WebEngine 路径切到 pyqtgraph 后，_web_view 应被释放"""
        import pyqtgraph as pg
        c = ChartContainer()

        class _MockFig:
            def to_html(self, **kw):
                return '<p>mock</p>'
        c.set_figure(_MockFig())    # 走 WebEngine（如可用）
        # 切到 pyqtgraph
        c.set_plot_widget(pg.PlotWidget())
        assert c.content_kind == 'pyqtgraph'
        assert c._web_view is None, '切到 pyqtgraph 后 _web_view 应释放'

    def test_clear_resets_content_kind(self, qapp):
        c = ChartContainer()
        c.set_message('占位')
        c.clear()
        assert c.content_kind == ''
