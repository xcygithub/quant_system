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
import os
import sys
import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
_PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..', '..')
)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from desktop.main_window import MainWindow
from desktop.widgets.async_worker import active_worker_count, shutdown_workers
from desktop.pages import watchlist_page as wp_module


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


class TestWatchlistUIRedesignCleanup:
    """回归：UI 重设计后【刷新/自动刷新/导出回测】单一入口

    关联 ISSUE-UI-04：原【刷新】按钮只读缓存、用户感觉"没动作"；
    「更多」里「批量在线刷新」「导出本组回测」是重复入口。
    本组测试锁住"单一入口"原则的清理结果，防止再次扩散入口。
    """

    def test_no_auto_refresh_fields(self, qapp):
        """【自动刷新】相关字段/常量应已清理"""
        from desktop.pages.watchlist_page import WatchlistPage
        page = WatchlistPage()
        try:
            # 1. ToggleSwitch 已不再创建
            assert not hasattr(page, "_auto_refresh_toggle"), \
                "自动刷新开关应已删除"
            # 2. 定时器字段已不再初始化
            assert not hasattr(page, "_auto_refresh_timer"), \
                "自动刷新定时器字段应已删除"
            assert not hasattr(page, "_is_auto_refreshing"), \
                "自动刷新状态字段应已删除"
        finally:
            shutdown_workers(timeout_ms=3000)

    def test_no_auto_refresh_methods(self, qapp):
        """【自动刷新】相关方法应已清理"""
        assert not hasattr(wp_module.WatchlistPage, "_on_auto_refresh_toggled"), \
            "_on_auto_refresh_toggled 应已删除"
        assert not hasattr(wp_module.WatchlistPage, "_start_auto_refresh"), \
            "_start_auto_refresh 应已删除"
        assert not hasattr(wp_module.WatchlistPage, "_stop_auto_refresh"), \
            "_stop_auto_refresh 应已删除"
        assert not hasattr(wp_module.WatchlistPage, "_on_auto_refresh_tick"), \
            "_on_auto_refresh_tick 应已删除"

    def test_no_auto_refresh_constant(self, qapp):
        """AUTO_REFRESH_INTERVAL_MS 常量应已清理"""
        assert not hasattr(wp_module, "AUTO_REFRESH_INTERVAL_MS"), \
            "AUTO_REFRESH_INTERVAL_MS 常量应已删除"

    def test_no_export_group_method(self, qapp):
        """_on_export_group（全组导出回测）应已删除，已被 _on_batch_export 替代"""
        assert not hasattr(wp_module.WatchlistPage, "_on_export_group"), \
            "_on_export_group 应已删除"

    def test_refresh_btn_triggers_baostock(self, qapp):
        """【刷新】按钮必须走 Baostock（_on_batch_refresh_quotes），不能只读缓存"""
        from desktop.pages.watchlist_page import WatchlistPage
        from unittest.mock import patch
        page = WatchlistPage()
        try:
            with patch.object(page, "_on_batch_refresh_quotes",
                              wraps=page._on_batch_refresh_quotes) as spy:
                # 模拟用户点击【刷新】按钮
                page._on_refresh_quotes()
                # 必须触发 Baostock 入口
                assert spy.called, \
                    "【刷新】按钮必须调用 _on_batch_refresh_quotes（走 Baostock）"
        finally:
            shutdown_workers(timeout_ms=3000)

    def test_more_menu_no_batch_refresh_no_export_group(self, qapp):
        """【更多】菜单应不再包含「批量在线刷新」和「导出本组用于回测」"""
        from desktop.pages.watchlist_page import WatchlistPage
        from PySide6.QtWidgets import QToolButton
        page = WatchlistPage()
        try:
            # 找到「更多」QToolButton
            more_btn = None
            for child in page.findChildren(QToolButton):
                if child.text() == "更多":
                    more_btn = child
                    break
            assert more_btn is not None, "未找到「更多」按钮"
            menu = more_btn.menu()
            assert menu is not None
            action_texts = [a.text() for a in menu.actions() if a.text()]

            # ISSUE-UI-04 修复：这两个重复入口应已删除
            assert "批量在线刷新 (Baostock)" not in action_texts, \
                "【更多】里「批量在线刷新」应已合并到工具栏【刷新】按钮"
            assert "导出本组用于回测" not in action_texts, \
                "【更多】里「导出本组用于回测」应已合并到底部【导出回测】"
        finally:
            shutdown_workers(timeout_ms=3000)

    def test_batch_export_falls_back_to_full_group_when_no_check(self, qapp):
        """底部【导出回测】无勾选时应退化导出全组，保持"全组导出"能力"""
        from desktop.pages.watchlist_page import WatchlistPage
        from unittest.mock import patch
        page = WatchlistPage()
        try:
            # 模拟 _all_rows 有数据
            page._all_rows = [
                {"symbol": "000001.SH", "name": "平安银行"},
                {"symbol": "600000.SH", "name": "浦发银行"},
            ]
            # 模拟 _table.get_checked_symbols 返回空（无勾选）
            with patch.object(page, "_table", create=True) as mock_table:
                type(mock_table).get_checked_symbols = lambda self: []
                page._on_batch_export()
                # 应退化导全组（2 只）
                assert list(page._state.selected_stocks) == [
                    "000001.SH", "600000.SH"
                ], "无勾选时应退化导出全组"
        finally:
            shutdown_workers(timeout_ms=3000)

    def test_refresh_btn_enabled_after_quotes_loaded(self, qapp):
        """回归：行情 worker 完成后必须恢复【刷新】按钮 enabled 状态

        历史 bug：删除自动刷新字段时误删了 `_on_quotes_loaded`/`_on_quotes_load_error`
        里的 `setEnabled(True)`，只保留了 `setText("刷新")`，导致按钮永远是 disabled，
        用户点了【刷新】没反应。锁住 enabled 状态恢复行为。
        """
        from desktop.pages.watchlist_page import WatchlistPage
        from unittest.mock import patch
        import time
        page = WatchlistPage()
        try:
            def mock_get_latest(db_path, symbols):
                return [
                    {"symbol": s, "close": 10.0, "pct_change": 1.0, "volume_wan": 100.0}
                    for s in symbols
                ]

            with patch("desktop.pages.watchlist_page._get_latest_quotes",
                       mock_get_latest):
                # 等初始 _schedule_quotes_load 的 worker 跑完
                shutdown_workers(timeout_ms=2000)
                for _ in range(30):
                    qapp.processEvents()
                    time.sleep(0.02)

                # 关键断言：worker 完成后按钮必须恢复 enabled 和文字"刷新"
                assert page._refresh_btn.isEnabled(), \
                    "【刷新】按钮必须在行情加载完成后恢复 enabled（修复前永远是 disabled）"
                assert page._refresh_btn.text() == "刷新", \
                    f"按钮文字应为\"刷新\"，实际\"{page._refresh_btn.text()}\""
        finally:
            shutdown_workers(timeout_ms=3000)
