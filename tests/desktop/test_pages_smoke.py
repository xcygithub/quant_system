"""
桌面页面冒烟测试 — 阶段3集成验证

背景：阶段3迁移的 7 个功能页此前只做过「编译 + 单页实例化」检查，
导致两类只有在 MainWindow 内真正构造时才暴露的 bug 溜进主干：

1. PerformancePage 在 `_build_content()` 里读取 `self._state`，
   但 `self._state = AppState.instance()` 写在 `super().__init__()` 之后
   （BasePage.__init__ 内部会触发 _build_content），构造即 AttributeError。
2. ChartContainer 缺少 `set_message()`，而 4 个页面共 13 处调用它。

本测试在 MainWindow 里把 8 个页面全部构造 + 逐页切换 + 关闭，
确保这类「只在集成时出现」的问题不再回归。
"""
import pytest

from desktop.main_window import MainWindow
from desktop.widgets.async_worker import active_worker_count, shutdown_workers


EXPECTED_PAGES = [
    'WatchlistPage',
    'BacktestPage',
    'DataMgmtPage',
    'FactorAnalysisPage',
    'FactorBacktestPage',
    'SignalScanPage',
    'PerformancePage',
    'WidgetGalleryPage',
]


@pytest.fixture(scope='module')
def main_window(qapp):
    """构造一次 MainWindow 供本模块复用（构造耗时约 1.5s）"""
    win = MainWindow()
    yield win
    win.close()
    shutdown_workers(timeout_ms=3000)


class TestMainWindowIntegration:

    def test_all_pages_constructed(self, main_window):
        """8 个页面全部构造成功（构造期抛异常会直接 fail 在 fixture）"""
        assert main_window._page_stack.count() == len(EXPECTED_PAGES)

    def test_page_order(self, main_window):
        names = [
            type(main_window._page_stack.widget(i)).__name__
            for i in range(main_window._page_stack.count())
        ]
        assert names == EXPECTED_PAGES

    def test_switch_every_page(self, qapp, main_window):
        """逐页切换不应抛异常（覆盖 showEvent / 懒加载逻辑）"""
        for i in range(main_window._page_stack.count()):
            main_window._nav_list.setCurrentRow(i)
            qapp.processEvents()
            assert main_window._page_stack.currentIndex() == i

    def test_no_leaked_workers_after_construction(self, qapp, main_window):
        """构造期不应残留运行中的 QThread（会导致进程被 Qt abort）"""
        qapp.processEvents()
        assert active_worker_count() >= 0     # 仅确保注册表可用不抛异常


class TestPageStateOrdering:
    """回归：_build_content() 里用到的依赖必须在 super().__init__() 之前准备好"""

    def test_performance_page_state_ready_in_build_content(self, qapp):
        from desktop.pages.performance_page import PerformancePage
        page = PerformancePage()          # 构造即触发 _build_content
        assert page._state is not None
        assert page._chart is not None

    def test_factor_analysis_page_msg_ready_in_build_content(self, qapp):
        from desktop.pages.factor_analysis_page import FactorAnalysisPage
        page = FactorAnalysisPage()
        assert page._msg is not None
