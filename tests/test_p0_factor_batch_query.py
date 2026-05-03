"""
P0 批量查询回归测试：
1. FundamentalFactors 支持按 symbols 批量构建因子面板。
2. FactorPresenter 多股单因子排名复用批量面板，并遵循负向因子排序。
"""
import os
import sqlite3
import tempfile
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from strategy.fundamental_factors import FundamentalFactors
from web.factor_presenter import FactorPresenter


def _create_test_db() -> str:
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    db_path = tmp.name
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute(
        """
        CREATE TABLE profit_data (
            symbol TEXT,
            report_date TEXT,
            roe REAL,
            gross_profit_rate REAL,
            net_profit_ratio REAL,
            eps REAL,
            net_profit REAL,
            business_income REAL,
            total_share REAL,
            liqa_share REAL
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE balance_data (
            symbol TEXT,
            report_date TEXT,
            total_equity REAL,
            total_assets REAL,
            debt_ratio REAL,
            current_ratio REAL,
            quick_ratio REAL,
            equity_ratio REAL
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE cash_flow_data (
            symbol TEXT,
            report_date TEXT,
            cfo_to_np REAL,
            oper_cash_flow REAL
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE dupont_data (
            symbol TEXT,
            report_date TEXT,
            roe REAL,
            asset_turnover REAL
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE growth_data (
            symbol TEXT,
            report_date TEXT,
            profit_grow REAL,
            profit_grow_ratio REAL,
            asset_to_income REAL
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE valuation_data (
            symbol TEXT,
            trade_date TEXT,
            pe REAL,
            pe_ttm REAL,
            pb REAL,
            ps REAL,
            pcf REAL,
            market_cap REAL,
            total_shares REAL
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE daily_kline (
            symbol TEXT,
            date TEXT,
            close REAL
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE factor_metadata (
            factor_name TEXT PRIMARY KEY,
            factor_category TEXT,
            factor_direction TEXT,
            description TEXT
        )
        """
    )

    symbols = ["AAA", "BBB"]
    for symbol, pe in [("AAA", 10.0), ("BBB", 20.0)]:
        cur.execute(
            "INSERT INTO profit_data VALUES (?, '2023-12-31', 0.15, 0.35, 0.20, 1.2, 1000000, 5000000, 10000000, 8000000)",
            (symbol,),
        )
        cur.execute(
            "INSERT INTO balance_data VALUES (?, '2023-12-31', 2000000, 8000000, 0.6, 1.5, 1.2, 0.4)",
            (symbol,),
        )
        cur.execute(
            "INSERT INTO cash_flow_data VALUES (?, '2023-12-31', 1.1, 1200000)",
            (symbol,),
        )
        cur.execute(
            "INSERT INTO dupont_data VALUES (?, '2023-12-31', 0.15, 0.8)",
            (symbol,),
        )
        cur.execute(
            "INSERT INTO growth_data VALUES (?, '2023-12-31', 0.1, 0.1, 0.08)",
            (symbol,),
        )
        cur.execute(
            "INSERT INTO valuation_data VALUES (?, '2024-05-01', ?, ?, 1.5, 2.0, 3.0, 100000000, 10000000)",
            (symbol, pe, pe),
        )
        cur.execute(
            "INSERT INTO daily_kline VALUES (?, '2024-05-01', 12.0)",
            (symbol,),
        )

    cur.execute(
        "INSERT INTO factor_metadata VALUES ('pe', 'valuation', 'negative', '市盈率')"
    )
    conn.commit()
    conn.close()
    return db_path


def test_batch_factor_panel_and_ranking() -> None:
    db_path = _create_test_db()
    try:
        ff = FundamentalFactors(db_path=db_path)
        panel = ff.calculate_factor_panel(["AAA", "BBB"], "2024-05-01")
        assert not panel.empty
        assert "pe" in panel.columns
        assert panel.loc["AAA", "pe"] == 10.0
        assert panel.loc["BBB", "pe"] == 20.0
        ff.close()

        fp = FactorPresenter(db_path=db_path)
        ranking = fp.get_multi_stock_single_factor(["AAA", "BBB"], "pe", "2024-05-01")
        fp.close()
        assert not ranking.empty
        assert ranking.iloc[0]["股票代码"] == "AAA"
        assert ranking.iloc[1]["股票代码"] == "BBB"
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)


def main() -> None:
    test_batch_factor_panel_and_ranking()
    print("批量查询回归测试通过")


if __name__ == "__main__":
    main()
