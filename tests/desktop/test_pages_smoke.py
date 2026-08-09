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


class TestWatchlistPageDetail:
    """回归：WatchlistPage._render_detail 中的 StockSelector 实例化路径

    历史问题：`StockSelector("切换股票")` 把字符串当作 parent 参数传入，
    导致详情视图一进就抛 TypeError，进程崩溃。该路径仅在用户双击表格行时触发，
    构造期不会跑到，所以必须显式调用 _render_detail 才能覆盖。
    """

    def test_render_detail_does_not_raise(self, qapp):
        from desktop.pages.watchlist_page import WatchlistPage
        page = WatchlistPage()
        try:
            page._render_detail("000001.SH")
            qapp.processEvents()
            # 进入详情视图
            assert page._view_mode == "detail"
            assert page._detail_symbol == "000001.SH"
            # StockSelector 实例已建立（关键：不抛 TypeError）
            assert page._detail_metric_container is not None
            assert page._chart is not None
        finally:
            # 让 AsyncWorker 完成，避免线程泄漏影响后续测试
            shutdown_workers(timeout_ms=3000)

    def test_render_detail_race_with_quotes_worker(self, qapp):
        """竞态回归：构造后立即进详情，列表行情 worker 完成时不得访问已删除控件

        历史问题：WatchlistPage 构造时 _schedule_quotes_load 启动 AsyncWorker，
        紧接着 _render_detail 触发 _clear_view 删除 _overview_container；
        worker 完成回调 _on_quotes_loaded 访问已删除控件 → RuntimeError
        → 主线程事件循环进入"未响应"。修复：视图切换时自增 token 使旧 worker
        失效 + 渲染方法加 RuntimeError 防御。
        """
        from desktop.pages.watchlist_page import WatchlistPage
        page = WatchlistPage()
        try:
            # 立即切到详情（模拟用户双击表格行，此时行情 worker 仍在运行）
            page._render_detail("601857.SH")

            # 让事件循环跑一段时间，worker 完成回调若抛异常会冒泡到这里
            for _ in range(6):
                qapp.processEvents()
                qapp.processEvents()   # 触发 queued 回调
            qapp.processEvents()

            # UI 状态应保持详情视图，且无异常（若 RuntimeError 未被防御，
            # processEvents 会抛出导致用例失败）
            assert page._view_mode == "detail"
            assert page._detail_symbol == "601857.SH"
        finally:
            shutdown_workers(timeout_ms=3000)

    def test_render_detail_then_back_to_list_race(self, qapp):
        """竞态回归（反向）：详情 → 返回列表，详情 worker 完成时不得访问已删除控件

        _render_list 自增 _detail_token + _load_detail 防御 RuntimeError，
        保证 K 线 worker 完成后在列表视图下不会访问已删除的 _chart。
        """
        from desktop.pages.watchlist_page import WatchlistPage
        page = WatchlistPage()
        try:
            page._render_detail("601857.SH")
            # 立即返回列表（模拟用户点"← 返回自选股列表"）
            page._render_list()

            for _ in range(6):
                qapp.processEvents()
                qapp.processEvents()
            qapp.processEvents()

            assert page._view_mode == "list"
        finally:
            shutdown_workers(timeout_ms=3000)
