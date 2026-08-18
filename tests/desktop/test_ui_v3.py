"""
v3.0 UI 优化组件测试：tokens / SectionCard / EmptyState / CheckableHeaderView
"""
import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QPushButton, QLabel


class TestDerivedFields:
    """行情详情页字段补齐"""

    def test_enrich_pct_change_and_amplitude(self, qapp):
        import pandas as pd
        from desktop.pages.watchlist_page import _enrich_derived_fields

        df = pd.DataFrame({
            "date": ["2024-01-01", "2024-01-02", "2024-01-03"],
            "open": [10.0, 10.5, 10.2],
            "high": [10.6, 10.8, 10.5],
            "low": [9.9, 10.4, 10.1],
            "close": [10.5, 10.2, 10.4],
            "volume": [1000, 1200, 1100],
            "amount": [10500, 12240, 11440],
            "pct_change": [0.0, 0.0, 0.0],
            "amplitude": [0.0, 0.0, 0.0],
            "change_amount": [0.0, 0.0, 0.0],
        })
        out = _enrich_derived_fields(df).sort_values("date").reset_index(drop=True)
        # 第一行无昨收，允许为 NaN；第二行起由 OHLC 计算
        assert abs(out.loc[1, "pct_change"] - ((10.2 - 10.5) / 10.5 * 100)) < 1e-6
        assert abs(out.loc[2, "pct_change"] - ((10.4 - 10.2) / 10.2 * 100)) < 1e-6
        assert abs(out.loc[1, "amplitude"] - ((10.8 - 10.4) / 10.5 * 100)) < 1e-6
        assert abs(out.loc[1, "change_amount"] - (10.2 - 10.5)) < 1e-6


class TestTokens:
    """设计令牌基本约束"""

    def test_spacing_grid(self):
        from desktop.styles import tokens
        # 4px 基栅
        assert tokens.SPACE_1 == 4
        assert tokens.SPACE_2 == 8
        assert tokens.SPACE_3 == 12
        assert tokens.SPACE_4 == 16
        assert tokens.SECTION_GAP == 16
        assert tokens.CONTROL_GAP == 8

    def test_control_height_unified(self):
        from desktop.styles import tokens
        assert tokens.CONTROL_HEIGHT == 32
        assert tokens.ROW_HEIGHT == 40

    def test_up_down_colors(self):
        from desktop.styles import tokens
        # A股惯例：涨红跌绿
        assert tokens.UP.upper() == "#E24B4A"
        assert tokens.DOWN.upper() == "#639922"

    def test_window_min_size(self):
        from desktop.styles import tokens
        assert tokens.WINDOW_MIN_WIDTH == 1080


class TestSectionCard:
    """白卡容器"""

    def test_with_title(self, qapp):
        from desktop.widgets.section_card import SectionCard
        card = SectionCard("筛选条件")
        assert card.objectName() == "sectionCard"
        titles = [w for w in card.findChildren(QLabel)
                  if w.objectName() == "sectionCardTitle"]
        assert len(titles) == 1
        assert titles[0].text() == "筛选条件"

    def test_without_title(self, qapp):
        from desktop.widgets.section_card import SectionCard
        card = SectionCard()
        titles = [w for w in card.findChildren(QLabel)
                  if w.objectName() == "sectionCardTitle"]
        assert len(titles) == 0
        assert card.content_layout is not None

    def test_content_layout_accepts_widgets(self, qapp):
        from desktop.widgets.section_card import SectionCard
        card = SectionCard("测试")
        btn = QPushButton("按钮")
        card.content_layout.addWidget(btn)
        assert btn.parent() is card.content_widget


class TestEmptyState:
    """空状态组件"""

    def test_basic_construction(self, qapp):
        from desktop.widgets.empty_state import EmptyState
        empty = EmptyState("📭", "暂无数据", "请添加")
        assert empty.objectName() == "emptyState"

    def test_action_button(self, qapp):
        from desktop.widgets.empty_state import EmptyState
        empty = EmptyState("📭", "暂无自选股")
        clicked = []
        empty.set_action("+ 添加股票", lambda: clicked.append(1))
        assert empty._action_btn is not None
        assert empty._action_btn.objectName() == "primaryBtn"
        assert empty._action_btn.text() == "+ 添加股票"
        empty._action_btn.click()
        assert clicked == [1]

    def test_set_desc_lazy(self, qapp):
        from desktop.widgets.empty_state import EmptyState
        empty = EmptyState("📭", "标题")
        empty.set_desc("补充描述")
        assert empty._desc_label is not None
        assert empty._desc_label.text() == "补充描述"


class TestCheckableHeaderView:
    """表头全选 Checkbox"""

    def _make_table(self, qapp):
        import pandas as pd
        from desktop.pages.watchlist_page import CheckableTableView
        df = pd.DataFrame({
            "代码": ["000001.SH", "600519.SH"],
            "名称": ["上证指数", "贵州茅台"],
            "最新价": [3946.0, 1343.0],
        })
        table = CheckableTableView()
        table.set_checkable_data(df)
        return table

    def test_header_exists(self, qapp):
        from desktop.pages.watchlist_page import CheckableHeaderView
        table = self._make_table(qapp)
        assert isinstance(table.horizontalHeader(), CheckableHeaderView)

    def test_select_all_syncs_header(self, qapp):
        table = self._make_table(qapp)
        table.select_all()
        assert table.horizontalHeader().check_state() == Qt.Checked
        table.deselect_all()
        assert table.horizontalHeader().check_state() == Qt.Unchecked

    def test_partial_state(self, qapp):
        table = self._make_table(qapp)
        table._proxy_model.toggle_check(0)
        table.sync_header_state()
        assert table.horizontalHeader().check_state() == Qt.PartiallyChecked

    def test_header_toggle_emits(self, qapp):
        table = self._make_table(qapp)
        received = []
        table.horizontalHeader().toggled.connect(lambda c: received.append(c))
        # 直接调用内部处理（模拟点击表头第 0 列）
        header = table.horizontalHeader()
        header._on_header_toggled = getattr(table, "_on_header_toggled")
        table._on_header_toggled(True)
        assert table.get_checked_count() == 2
        table._on_header_toggled(False)
        assert table.get_checked_count() == 0
