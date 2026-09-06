"""
StockGroupSelector 分组选股组件测试 — 策略回测页按自选股分组选股

背景：原平铺式 StockCheckboxGroup 在策略回测页里体验差（标题截断、
全选孤立、11 只股票全靠滚动）。改为按自选股 group 字段组织的分组树：
一级分组（可整体三态勾选）、二级个股，配搜索过滤 + 折叠 + 全选/清空。

本组测试锁住：
1. 组头三态联动（勾选组头=全选组内，部分=半选）
2. 折叠不丢勾选状态
3. 搜索跨分组过滤（匹配 symbol/name）
4. 全选/清空/计数/信号
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

from PySide6.QtCore import Qt

from desktop.widgets.stock_selector import StockGroupSelector


SAMPLE_GROUPS = [
    ("银行", [("000001.SZ", "平安银行"), ("600000.SH", "浦发银行"),
              ("601398.SH", "工商银行")]),
    ("消费", [("600519.SH", "贵州茅台"), ("000858.SZ", "五粮液")]),
]


@pytest.fixture
def selector(qapp):
    sel = StockGroupSelector()
    sel.set_groups(SAMPLE_GROUPS)
    return sel


def _visible(widget) -> bool:
    """offscreen 下不 show()，用 isHidden 判断逻辑可见性"""
    return not widget.isHidden()


class TestGroupBuild:
    def test_groups_created(self, selector):
        assert set(selector._groups.keys()) == {"银行", "消费"}
        assert len(selector._groups["银行"]["stocks"]) == 3
        assert len(selector._groups["消费"]["stocks"]) == 2

    def test_total_count(self, selector):
        assert selector._total_stocks == 5

    def test_empty_groups_shows_empty_label(self, qapp):
        sel = StockGroupSelector()
        sel.set_groups([])
        assert sel._total_stocks == 0
        assert _visible(sel._empty_label)


class TestGroupHeaderTristate:
    def test_check_group_selects_all_in_group(self, selector):
        # 走真实 signal 路径：setCheckState 触发 stateChanged，signal 传 int
        # （修复前 state==Qt.Checked 因 enum!=int 恒 False，导致组内全不选）
        selector._groups["银行"]["header"].setCheckState(Qt.Checked)
        selected = set(selector.get_selected())
        assert selected == {"000001.SZ", "600000.SH", "601398.SH"}

    def test_uncheck_group_clears_all_in_group(self, selector):
        selector.set_selected(["000001.SZ", "600000.SH", "601398.SH",
                               "600519.SH"])
        selector._groups["银行"]["header"].setCheckState(Qt.Unchecked)
        selected = set(selector.get_selected())
        assert selected == {"600519.SH"}  # 银行全清，消费保留

    def test_header_state_changed_receives_int(self, selector):
        """锁住 PySide6 enum bug：stateChanged 传 int，须能正确识别为 Checked"""
        received = []
        selector._groups["银行"]["header"].stateChanged.connect(received.append)
        selector._groups["银行"]["header"].setCheckState(Qt.Checked)
        # signal 收到的应是 int（PySide6 6.x 行为）
        assert received and received[-1] == 2
        assert isinstance(received[-1], int)

    def test_partial_selection_sets_header_partially_checked(self, selector):
        selector.set_selected(["000001.SZ"])  # 银行组只选 1 只
        header = selector._groups["银行"]["header"]
        assert header.checkState() == Qt.PartiallyChecked

    def test_click_group_after_clear_reselects_all_in_group(self, qapp):
        """锁住 bug：清空后点组头应重新全选组内。

        组头是三态 QCheckBox，从 Unchecked(0) 首次点击会先落到
        PartiallyChecked(1)（用户点击的真实路径）。修复前回调只把
        state==Checked(2) 当"勾选"，导致 Partially 被误判为取消，
        清空后点组头无法重新多选。这里用 setCheckState(PartiallyChecked)
        走真实 signal 路径锁住该行为。
        """
        sel = StockGroupSelector()
        sel.set_groups(SAMPLE_GROUPS)
        sel._on_clear()
        assert sel.get_selected() == []
        # 模拟用户点击组头：首次点击从 Unchecked 落到 PartiallyChecked
        sel._groups["银行"]["header"].setCheckState(Qt.PartiallyChecked)
        selected = set(sel.get_selected())
        assert selected == {"000001.SZ", "600000.SH", "601398.SH"}
        # 组头应被 _update_all 刷新为"已全选"
        assert sel._groups["银行"]["header"].checkState() == Qt.Checked

    def test_all_selected_sets_header_checked(self, selector):
        selector.set_selected(["000001.SZ", "600000.SH", "601398.SH"])
        assert selector._groups["银行"]["header"].checkState() == Qt.Checked


class TestCollapse:
    def test_collapse_does_not_lose_selection(self, selector):
        selector.set_selected(["000001.SZ", "600519.SH"])
        before = sorted(selector.get_selected())
        selector._on_toggle_group("银行")  # 折叠银行组
        after = sorted(selector.get_selected())
        assert before == after

    def test_collapse_hides_container(self, selector):
        selector._on_toggle_group("银行")  # 折叠
        assert not _visible(selector._groups["银行"]["container"])
        # 组头仍在
        assert _visible(selector._groups["银行"]["header_widget"])

    def test_collapse_toggles_arrow_text(self, selector):
        assert selector._groups["银行"]["arrow"].text() == "▼"
        selector._on_toggle_group("银行")
        assert selector._groups["银行"]["arrow"].text() == "▶"
        selector._on_toggle_group("银行")
        assert selector._groups["银行"]["arrow"].text() == "▼"


class TestSearchFilter:
    def test_search_by_name_filters_groups(self, selector):
        selector._search.setText("茅台")
        assert not _visible(selector._groups["银行"]["header_widget"])
        assert _visible(selector._groups["消费"]["header_widget"])
        # 组内：茅台显示，五粮液隐藏
        assert _visible(selector._groups["消费"]["stocks"]["600519.SH"])
        assert not _visible(selector._groups["消费"]["stocks"]["000858.SZ"])

    def test_search_by_symbol_filters(self, selector):
        selector._search.setText("601")
        assert _visible(selector._groups["银行"]["header_widget"])  # 601398 命中
        assert not _visible(selector._groups["消费"]["header_widget"])

    def test_clear_search_restores_all(self, selector):
        selector._search.setText("茅台")
        selector._search.setText("")
        assert _visible(selector._groups["银行"]["header_widget"])
        assert _visible(selector._groups["消费"]["header_widget"])


class TestSelectAllClear:
    def test_select_all(self, selector):
        selector._on_select_all()
        assert len(selector.get_selected()) == 5

    def test_clear(self, selector):
        selector._on_select_all()
        selector._on_clear()
        assert selector.get_selected() == []


class TestCountAndSignal:
    def test_count_label_updates(self, selector):
        selector.set_selected(["000001.SZ", "600519.SH"])
        assert selector._count_label.text() == "已选 2/5 只"

    def test_selection_changed_emitted(self, qapp):
        sel = StockGroupSelector()
        sel.set_groups(SAMPLE_GROUPS)
        received = []
        sel.selection_changed.connect(received.append)
        sel.set_selected(["000001.SZ"])
        # set_selected 内部 _update_all 会 emit 一次
        assert received and received[-1] == ["000001.SZ"]

    def test_stock_checkbox_change_emits(self, qapp):
        sel = StockGroupSelector()
        sel.set_groups(SAMPLE_GROUPS)
        received = []
        sel.selection_changed.connect(received.append)
        sel._groups["银行"]["stocks"]["600000.SH"].setChecked(True)
        assert "600000.SH" in (received[-1] if received else [])


class TestGetSetSelected:
    def test_get_selected_returns_symbols_only(self, selector):
        selector.set_selected(["000001.SZ", "000858.SZ"])
        assert sorted(selector.get_selected()) == ["000001.SZ", "000858.SZ"]

    def test_set_selected_roundtrip(self, selector):
        selector.set_selected(["600519.SH"])
        assert selector.get_selected() == ["600519.SH"]
