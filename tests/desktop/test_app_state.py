"""
AppState 状态管理单元测试

测试单例、属性读写、信号通知、去重、通用键值存储。
"""
from desktop.models.app_state import AppState


class TestAppStateSingleton:

    def test_singleton(self, qapp):
        AppState.reset()
        s1 = AppState.instance()
        s2 = AppState.instance()
        assert s1 is s2

    def test_reset(self, qapp):
        AppState.reset()
        s1 = AppState.instance()
        s1.selected_stock = '000001.SZ'
        AppState.reset()
        s2 = AppState.instance()
        assert s2.selected_stock == ''


class TestAppStateSelectedStock:

    def test_set_and_get(self, qapp):
        AppState.reset()
        state = AppState.instance()
        state.selected_stock = '600000.SH'
        assert state.selected_stock == '600000.SH'

    def test_signal_emitted(self, qapp):
        AppState.reset()
        state = AppState.instance()
        received = []
        state.selected_stock_changed.connect(lambda s: received.append(s))
        state.selected_stock = '600000.SH'
        assert received == ['600000.SH']

    def test_no_duplicate_signal(self, qapp):
        """相同值不重复触发信号"""
        AppState.reset()
        state = AppState.instance()
        received = []
        state.selected_stock_changed.connect(lambda s: received.append(s))
        state.selected_stock = '000001.SZ'
        state.selected_stock = '000001.SZ'  # 相同值
        assert len(received) == 1


class TestAppStateBacktest:

    def test_backtest_result(self, qapp):
        AppState.reset()
        state = AppState.instance()
        received = []
        state.backtest_result_changed.connect(lambda r: received.append(r))
        state.backtest_result = {'total_return': 0.15}
        assert state.backtest_result == {'total_return': 0.15}
        assert len(received) == 1

    def test_backtest_params_merge(self, qapp):
        AppState.reset()
        state = AppState.instance()
        assert state.backtest_params['initial_capital'] == 1000000
        state.backtest_params = {'initial_capital': 500000}
        assert state.backtest_params['initial_capital'] == 500000
        # 其他默认参数应保留
        assert state.backtest_params['commission_rate'] == 0.0003

    def test_update_single_param(self, qapp):
        AppState.reset()
        state = AppState.instance()
        state.update_backtest_param('max_positions', 10)
        assert state.backtest_params['max_positions'] == 10

    def test_backtest_progress(self, qapp):
        AppState.reset()
        state = AppState.instance()
        received = []
        state.backtest_progress_changed.connect(lambda p, m: received.append((p, m)))
        state.set_backtest_progress(50, 'half done')
        assert received == [(50, 'half done')]

    def test_backtest_running(self, qapp):
        AppState.reset()
        state = AppState.instance()
        received = []
        state.backtest_running_changed.connect(lambda r: received.append(r))
        state.backtest_running = True
        assert state.backtest_running is True
        state.cancel_backtest()
        assert state.backtest_running is False
        assert received == [True, False]


class TestAppStateScan:

    def test_scan_result(self, qapp):
        AppState.reset()
        state = AppState.instance()
        received = []
        state.scan_result_changed.connect(lambda r: received.append(r))
        state.scan_result = {'buy': 5, 'sell': 3}
        assert state.scan_result == {'buy': 5, 'sell': 3}
        assert len(received) == 1

    def test_scan_selected_stocks(self, qapp):
        AppState.reset()
        state = AppState.instance()
        state.scan_selected_stocks = {'000001.SZ', '600000.SH'}
        assert '000001.SZ' in state.scan_selected_stocks


class TestAppStateGenericKV:

    def test_set_get(self, qapp):
        AppState.reset()
        state = AppState.instance()
        state.set('custom_key', 'value')
        assert state.get('custom_key') == 'value'

    def test_get_default(self, qapp):
        AppState.reset()
        state = AppState.instance()
        assert state.get('nonexistent', 'default') == 'default'

    def test_has(self, qapp):
        AppState.reset()
        state = AppState.instance()
        state.set('key', 1)
        assert state.has('key')
        assert not state.has('nope')

    def test_remove(self, qapp):
        AppState.reset()
        state = AppState.instance()
        state.set('key', 1)
        state.remove('key')
        assert not state.has('key')


class TestAppStateWatchlist:

    def test_watchlist_signal(self, qapp):
        AppState.reset()
        state = AppState.instance()
        received = []
        state.watchlist_changed.connect(lambda s: received.append(s))
        state.watchlist = ['000001.SZ', '600000.SH']
        assert state.watchlist == ['000001.SZ', '600000.SH']
        assert len(received) == 1
        assert received[0] == ['000001.SZ', '600000.SH']
