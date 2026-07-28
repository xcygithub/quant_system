"""
P1 回归测试：
1. MultiFactorBacktest 的 IC 更新频率按调仓计数生效。
2. FinancialDataSource 的季度抓取模板可统一聚合多季度数据。
"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from data.financial_data_source import FinancialDataSource
from portfolio.multi_factor_backtest import MultiFactorBacktest


def test_ic_update_frequency_counter() -> None:
    """首次调仓和周期触发时应调用 IC 更新。"""
    backtest = MultiFactorBacktest(
        factor_weights={"roe": 1.0},
        use_ic_weighting=True,
        ic_update_freq=3
    )

    called = {"count": 0}

    def fake_update() -> None:
        called["count"] += 1

    backtest._update_ic_weights = fake_update

    for _ in range(7):
        backtest._maybe_update_ic_weights_for_rebalance()

    # 第1次 + 第3次 + 第6次
    assert called["count"] == 3


class _FakeResultSet:
    def __init__(self, rows, fields=None, error_code="0", error_msg=""):
        self._rows = rows
        self.fields = fields or ["code", "pubDate"]
        self.error_code = error_code
        self.error_msg = error_msg
        self._idx = -1

    def next(self):
        self._idx += 1
        return self._idx < len(self._rows)

    def get_row_data(self):
        return self._rows[self._idx]


def test_quarterly_fetch_template() -> None:
    """季度模板应能聚合多个季度并追加 symbol 列。"""
    source = FinancialDataSource.__new__(FinancialDataSource)
    source._logged_in = False
    source.bs = None

    def fake_query_func(code: str, year: str, quarter: str):
        if year == "2024" and quarter == "2":
            return _FakeResultSet([], error_code="1", error_msg="mock error")
        if year == "2024" and quarter == "1":
            return _FakeResultSet([["sh.600000", "2024-03-31"]], fields=["code", "pubDate"])
        if year == "2024" and quarter == "3":
            return _FakeResultSet([["sh.600000", "2024-09-30"]], fields=["code", "pubDate"])
        return _FakeResultSet([], fields=["code", "pubDate"])

    df = source._fetch_quarterly_data(
        symbol="600000.SH",
        start_year=2024,
        end_year=2024,
        api_name="mock_api",
        query_func=fake_query_func,
        data_label="mock_data"
    )

    assert not df.empty
    assert len(df) == 2
    assert set(df["pubDate"].tolist()) == {"2024-03-31", "2024-09-30"}
    assert all(df["symbol"] == "600000.SH")


def main() -> None:
    test_ic_update_frequency_counter()
    test_quarterly_fetch_template()
    print("P1 回归测试通过")


if __name__ == "__main__":
    main()
